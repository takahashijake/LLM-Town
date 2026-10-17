"""Trusted scenario orchestration and bounded, privacy-controlled package export."""
from __future__ import annotations

from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import random
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

from src.analysis.inspection_save import InspectionError, load_save
from src.analysis.observatory import canonical, checkpoint, compare_checkpoints, fingerprint
from src.analysis.observatory_presentation import render

ROOT = Path(__file__).resolve().parents[2]
MAX_PACKAGE_BYTES = 32 * 1024 * 1024
MAX_FILES = 64
SCENARIOS = ('garden', 'commerce')


def revision() -> str:
    return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True,
                          capture_output=True, text=True, timeout=10).stdout.strip()


def _run(script: str, output: Path, timeout: int = 300) -> float:
    """Only repository-selected evaluators run; never execute loaded package data."""
    started = time.perf_counter()
    result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), '--output', str(output)],
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            timeout=timeout)
    if result.returncode:
        raise InspectionError('trusted scenario evaluator failed; run its standalone command for diagnostics')
    return time.perf_counter() - started


def _initial(root: Path, config: Path) -> Path:
    # Deliberately separate from inspection; this is a real simulation initialization.
    from src.analysis.collective_project_evaluation import engine, SEED
    if Path.cwd().resolve() != ROOT:
        raise InspectionError('showcase generation must run from the repository root')
    caller = random.getstate()
    try:
        random.seed(SEED)
        with redirect_stdout(StringIO()):
            town = engine(root, 'initial', config)
            town.state.save(town, 0, 0, day_complete=True)
        return root / 'initial.json'
    finally:
        random.setstate(caller)


def project_scenarios(garden: Path, commerce: Path, *, source_revision: str) -> dict:
    """Reuse evaluator outputs, then export only allowlisted observations."""
    bases = tuple(r['id'] for r in json.loads((ROOT / 'data/locations.json').read_text()))
    report = load_save(garden / 'report.json')
    if report['status'] != 'PASS' or not all(report['checks'].values()):
        raise InspectionError('garden evaluation has failing release checks')
    garden_states = []
    for label, filename in [('initial', 'initial'), ('formation', 'formation'),
                            ('one_contribution', 'one_contribution'),
                            ('before_completion', 'before_completion'),
                            ('after_completion', 'after_completion'), ('final', 'uninterrupted')]:
        save = load_save(garden / f'{filename}.json')
        queries = tuple(('project', r['id']) for r in save.get('collective_projects', {}).get('projects', []))
        if label == 'final':
            queries += tuple(('institution', r['institution_id']) for r in save['institution_growth']['formation_records'])
            production = save['materials']['production_records']
            if production:
                queries += (('lot', production[-1]['output_lot_ids'][0]),)
        garden_states.append(checkpoint(save, label=label, base_location_ids=bases, queries=queries))
    v8 = load_save(commerce / 'showcase.json')
    if not all(v8['branch_checks'].values()) or not v8['reconstruction_equal']:
        raise InspectionError('commerce evaluation has failing release checks')
    commerce_states = []
    for label, filename in [('commerce_before', 'before'), ('commerce_final', 'after')]:
        save = load_save(commerce / f'{filename}.json')
        queries = tuple(('institution', r['institution_id']) for r in save['commerce_growth']['activation_records'])
        recipes = {r['recipe_id'] for r in save['commerce_growth']['activation_records']}
        first_outputs = {}
        for row in save['materials']['production_records']:
            if row['recipe_id'] in recipes and row['recipe_id'] not in first_outputs:
                first_outputs[row['recipe_id']] = row['output_lot_ids'][0]
        queries += tuple(('lot', first_outputs[recipe]) for recipe in sorted(first_outputs))
        commerce_states.append(checkpoint(save, label=label, base_location_ids=bases, queries=queries))
    # Config and repository inputs bind the replay claim. No machine paths/times.
    input_files = sorted(p for p in (ROOT / 'data').glob('*.json') if p.name != 'save_state.json')
    inputs = {p.name: sha256(p.read_bytes()).hexdigest() for p in input_files}
    payload = {'schema_version': 1, 'kind': 'town_observatory', 'revision': source_revision,
        'inputs': inputs, 'scenarios': [
            {'id': 'garden', 'title': 'Canonical town · Garden learning',
             'description': 'Seed 11, 100 days at 08:00. Real migration, public locations, events, institution employment, material activity and multi-day civic work. No commitments or legal events are invented.',
             'seed': report['seed'], 'days': report['days'],
             'config': load_save(garden / 'v9-config.json'), 'checkpoints': garden_states,
             'verification': {k: report[k] for k in ('status', 'checks', 'signature', 'reconstruction_signatures', 'workshop_executions')}},
            {'id': 'commerce', 'title': 'Separate fixture · Two commerce branches',
             'description': 'Existing V8 seed-23, 180-day scenario with bounded deterministic proposal provider. Separate from the garden world; verifies procurement, production and sales across two branches.',
             'seed': v8['seed'], 'days': v8['days'], 'checkpoints': commerce_states,
             'verification': {'status': 'PASS', 'checks': v8['branch_checks'],
                              'reconstruction_equal': v8['reconstruction_equal'],
                              'institution_signatures': v8['institution_signatures'], 'lot_signatures': v8['lot_signatures']}},
        ]}
    payload['fingerprint'] = fingerprint(payload)
    return payload


def _exports(bundle: dict) -> dict[str, bytes]:
    files = {'observatory.json': canonical(bundle)}
    for scenario in bundle['scenarios']:
        states = scenario['checkpoints']
        for state in states:
            files[f"{scenario['id']}-{state['label']}.json"] = canonical(state)
        files[f"{scenario['id']}-timeline.json"] = canonical(states[-1]['events'])
        files[f"{scenario['id']}-traces.json"] = canonical(states[-1]['traces'])
        files[f"{scenario['id']}-comparison.json"] = canonical(compare_checkpoints(states[0], states[-1]))
    files['index.html'] = render(bundle).encode('utf-8')
    garden = bundle['scenarios'][0]
    final = garden['checkpoints'][-1]
    project_trace = final['traces'][0]
    contribution_days = sorted(e['day'] for e in final['events'] if e['source'] == 'contributions')
    lines = ['LLM-Town V10 Town Observatory — review candidate', '',
             'Open index.html directly in a browser. It needs no server, fetch, model or network.',
             'Select a scenario and checkpoint, then explore timeline, entities, verified traces and differences.',
             f"Canonical seed {garden['seed']}: {garden['days']} days at 08:00.",
             f'Verified contribution days: {contribution_days}.',
             f"Final verified workshop executions: {final['metrics']['workshops']['value']}.",
             'One-contribution checkpoint has no completed-project effect.',
             'Four independent V9 checkpoint continuations match full authoritative systems.',
             'Commerce is a separately labeled V8 fixture, with independent 90+90 reconstruction.',
             'Same-tick order and shared IDs establish associations only. Only contract-checked edges prove dependencies.',
             f"Project trace unresolved codes: {sorted({u['code'] for u in project_trace['unresolved']})}.",
             'Public snapshots are projections, not resumable engine saves. Private narrative stays in temporary storage.',
             'Independent replay: python scripts/showcase_town.py --verify /path/to/package',
             f"Revision: {bundle['revision']}", f"Public fingerprint: {bundle['fingerprint']}", '']
    files['walkthrough.txt'] = '\n'.join(lines).encode('utf-8')
    if len(files) >= MAX_FILES or sum(len(v) for v in files.values()) > MAX_PACKAGE_BYTES:
        raise InspectionError('showcase exceeds package output budget')
    return files


def build_package(output: Path) -> dict:
    """Generate into a new directory; refuse overwrite and clean failures."""
    output = Path(output)
    if output.exists():
        raise InspectionError('showcase output must be a new directory')
    started = time.perf_counter()
    with TemporaryDirectory(prefix='llm-town-v10-') as temp:
        work = Path(temp)
        garden, commerce = work / 'garden', work / 'commerce'
        generation = {'garden_seconds': _run('evaluate_v9_collective_projects.py', garden),
                      'commerce_seconds': _run('showcase_v8.py', commerce)}
        # Input paths in the reused evaluator are relative to repository root.
        # CLI enforces cwd; direct API callers must use the same trusted root.
        _initial(garden, garden / 'v9-config.json')
        projection_start = time.perf_counter()
        bundle = project_scenarios(garden, commerce, source_revision=revision())
        projection_seconds = time.perf_counter() - projection_start
        presentation_start = time.perf_counter()
        files = _exports(bundle)
        presentation_seconds = time.perf_counter() - presentation_start
        manifest = {'schema_version': 1, 'kind': 'town_showcase_manifest',
                    'revision': bundle['revision'], 'fingerprint': bundle['fingerprint'],
                    'scenarios': list(SCENARIOS), 'files': {name: {'sha256': sha256(value).hexdigest(), 'bytes': len(value)}
                                                         for name, value in sorted(files.items())},
                    'policy': 'Public reports only; no private save, logs, prompts or executable replay instructions.'}
        files['manifest.json'] = canonical(manifest)
        measurements = {**generation, 'projection_seconds': projection_seconds,
                        'presentation_seconds': presentation_seconds, 'elapsed_seconds': time.perf_counter() - started,
                        'public_bytes': sum(len(v) for v in files.values()),
                        'note': 'Performance measurements are excluded from reproducibility fingerprints.'}
        files['benchmark.json'] = canonical(measurements)
        if sum(len(v) for v in files.values()) > MAX_PACKAGE_BYTES:
            raise InspectionError('showcase exceeds package output budget')
        output.mkdir(parents=True, exist_ok=False)
        try:
            for name, value in files.items():
                (output / name).write_bytes(value)
        except BaseException:
            # Remove only files this call created, never recursively delete user paths.
            for name in files:
                (output / name).unlink(missing_ok=True)
            output.rmdir()
            raise
        return manifest


def validate_package(root: Path) -> dict:
    """Treat manifests as untrusted: strict file allowlist, bounded reads, no commands."""
    root = Path(root)
    path = root / 'manifest.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
        raise InspectionError('invalid showcase manifest')
    manifest = load_save(path)
    if type(manifest.get('schema_version')) is not int or manifest.get('schema_version') != 1 or manifest.get('kind') != 'town_showcase_manifest' or manifest.get('scenarios') != list(SCENARIOS):
        raise InspectionError('unsupported showcase manifest')
    expected = {'observatory.json', 'index.html', 'walkthrough.txt'}
    expected |= {f'{scenario}-{kind}.json' for scenario in SCENARIOS for kind in ('timeline', 'traces', 'comparison')}
    expected |= {f'garden-{label}.json' for label in ('initial', 'formation', 'one_contribution', 'before_completion', 'after_completion', 'final')}
    expected |= {'commerce-commerce_before.json', 'commerce-commerce_final.json'}
    entries = manifest.get('files')
    if not isinstance(entries, dict) or set(entries) != expected:
        raise InspectionError('invalid showcase file allowlist')
    total = 0
    for name, entry in entries.items():
        if not isinstance(entry, dict) or type(entry.get('bytes')) is not int or not 0 <= entry['bytes'] <= MAX_PACKAGE_BYTES:
            raise InspectionError('invalid showcase file size')
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise InspectionError('invalid showcase file')
        with path.open('rb') as handle:
            payload = handle.read(entry['bytes'] + 1)
        total += len(payload)
        if total > MAX_PACKAGE_BYTES or len(payload) != entry['bytes'] or sha256(payload).hexdigest() != entry.get('sha256'):
            raise InspectionError('showcase file fingerprint mismatch')
    return manifest


def verify_package(root: Path) -> dict:
    """Fresh process scenarios and independent resumed runs verify authority."""
    expected = validate_package(root)
    if expected.get('revision') != revision():
        raise InspectionError('independent replay requires the recorded repository revision')
    with TemporaryDirectory(prefix='llm-town-v10-replay-') as temp:
        actual = build_package(Path(temp) / 'replay')
    if expected != actual:
        raise InspectionError('independent replay differs from the public package')
    return {'schema_version': 1, 'kind': 'showcase_verification', 'status': 'PASS',
            'revision': actual['revision'], 'fingerprint': actual['fingerprint'],
            'note': 'Fresh simulation and all independent evaluator continuations matched.'}
