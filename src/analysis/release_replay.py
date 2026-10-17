"""Fresh-process continuation and observational costs of real release fixtures.

Private checkpoints and legacy RNG sidecars live only in temporary directories.
Timing is observational; conservation, reconstruction and replay are hard gates.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import json
import os
import platform
from pathlib import Path
import random
import resource
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

from src.analysis.benchmark import _git_metadata
from src.analysis.causal_inspector import trace
from src.analysis.collective_project_evaluation import authoritative_signature as behavior_signature
from src.analysis.growth_audits import authoritative_signature, authority_checks, conservation_checks
from src.analysis.observatory import checkpoint, fingerprint
from src.analysis.v6_freeze_evaluation import MultiBranchProvider, write_config
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.simulation.project_random_state import restore_project_random_state

SCENARIOS = {'legacy': (23, 30), 'procedural': (23, 180), 'collective': (11, 100)}


def signatures(town: SimulationEngine) -> dict[str, str]:
    """Compare existing growth and social authority scopes plus public projection."""
    return {'growth': fingerprint(authoritative_signature(town)),
            'behavior': behavior_signature(town),
            'public': fingerprint(checkpoint(town.state.path, label='release',
                base_location_ids=tuple(sorted(town.location_growth.base_location_ids))))}


def boundary_labels(town: SimulationEngine, day: int, complete: bool) -> list[str]:
    """Discover actual authority boundaries rather than pinning seed-specific days."""
    labels = []
    if complete and day in (1, 15):
        labels.append(f'day-{day}')
    if complete and any(r.status == 'activated' for r in town.institution_growth.formation_records):
        labels.append('institution')
    inventories = {a.inventory_id for a in town.commerce_growth.activation_records
                   if a.template_id.startswith('generated_') and a.status == 'activated'}
    if complete and any(r.buyer_inventory_id in inventories for r in town.materials.exchanges):
        labels.append('inventory-transfer')
    civic = town.collective_projects
    if complete and civic.projects and not civic.contributions:
        labels.append('project-formation')
    if complete and len(civic.contributions) == 1:
        labels.append('one-contribution')
    if civic.contributions and len(civic.contributions) == civic.policy.required_units and not civic.effects:
        labels.append('before-completion')
    if complete and civic.effects:
        labels.append('after-completion')
    return labels


def _build(root: Path, scenario: str, seed: int, provider, *, load: bool) -> SimulationEngine:
    return SimulationEngine('data/agents.json', 'data/locations.json',
        llm_client=FakeLLMClient(), state_path=root / 'world.json', logs_dir=root / 'logs',
        town_growth_path=root / 'config.json', simulation_seed=seed,
        growth_proposal_provider=provider, load_state=load)


def worker(root: Path, scenario: str, days: int, resume: Path | None = None) -> dict:
    """Trusted evaluator worker; never run against an untrusted checkpoint path."""
    seed = SCENARIOS[scenario][0]
    root.mkdir(parents=True, exist_ok=False)
    provider = MultiBranchProvider() if scenario == 'procedural' else None
    if scenario == 'procedural':
        config = json.loads(write_config(root).read_text())
    else:
        config = json.loads(Path('data/town_growth.json').read_text())
        config['collective_projects'] = {'enabled': scenario == 'collective'}
    (root / 'config.json').write_text(json.dumps(config))
    random.seed(seed)
    started = time.perf_counter()
    if resume:
        metadata = json.loads(resume.with_suffix('.meta').read_text())
        (root / 'world.json').write_bytes(resume.read_bytes())
        if provider:
            provider.calls = metadata['provider_calls']
        # Deliberately unrelated caller stream: restoration cannot inherit a live engine.
        random.seed(987654)
    town = _build(root, scenario, seed, provider, load=bool(resume))
    reconstruction_seconds = time.perf_counter() - started
    checks = {}
    if resume:
        checks['reconstruction'] = signatures(town) == metadata['signatures']
        # Legacy schemas intentionally lack persisted RNG. The runner records it
        # explicitly; this is harness continuation, not a legacy save guarantee.
        if scenario == 'collective':
            checks['persisted_rng'] = json.loads(json.dumps(random.getstate())) == metadata['rng']['state']
        restore_project_random_state(metadata['rng'])
    captured = {}
    save_seconds = 0.0
    save_count = 0
    original_save = town.state.save

    def capture(engine, day, hour, *, day_complete=False):
        nonlocal save_seconds, save_count
        start = time.perf_counter()
        original_save(engine, day, hour, day_complete=day_complete)
        save_seconds += time.perf_counter() - start
        save_count += 1
        if resume:
            return
        for label in boundary_labels(engine, day, day_complete):
            if label in captured:
                continue
            path = root / f'{label}.json'
            path.write_bytes(engine.state.path.read_bytes())
            meta = {'day': day, 'hour': hour, 'day_complete': day_complete,
                    'rng': {'version': 1, 'state': random.getstate()},
                    'provider_calls': provider.calls.copy() if provider else None,
                    'signatures': signatures(engine)}
            path.with_suffix('.meta').write_text(json.dumps(meta))
            captured[label] = {k: meta[k] for k in ('day', 'hour', 'day_complete')}

    town.state.save = capture
    previous_day = json.loads(resume.read_bytes())['current_day'] if resume else 0
    started = time.perf_counter()
    # With one hour, partial checkpoints finish that day before starting the tail.
    with open(os.devnull, 'w') as sink, redirect_stdout(sink):
        town.run(days - previous_day, [8])
    simulation_seconds = time.perf_counter() - started
    checks.update(conservation_checks(town))
    checks.update(authority_checks(town))
    started = time.perf_counter()
    final = signatures(town)
    inspection_seconds = time.perf_counter() - started
    started = time.perf_counter()
    formations = town.institution_growth.formation_records
    query = ('project', town.collective_projects.projects[0].id) if town.collective_projects.projects else (
        ('institution', formations[0].institution_id) if formations else ('account', next(iter(town.economy.accounts))))
    trace(town.state.path, type=query[0], identity=query[1], depth=3, limit=100)
    causal_seconds = time.perf_counter() - started
    saved = json.loads(town.state.path.read_bytes())
    counts = {'residents': len(town.agents), 'locations': len(town.locations),
              'institutions': len(town.institution_growth.formation_records),
              'events': len(town.event_ecology.occurrence_history),
              'transactions': len(town.economy.ledger), 'activities': len(town.activity_records),
              'lot_movements': len(saved['materials']['lot_movements'])}
    return {'scenario': scenario, 'seed': seed, 'days': days, 'hash_seed': os.environ.get('PYTHONHASHSEED'),
            'checks': checks, 'signatures': final, 'checkpoints': captured, 'counts': counts,
            'observations': {'simulation_seconds': simulation_seconds,
                'seconds_per_day': simulation_seconds / max(1, days - previous_day),
                'save_seconds': save_seconds, 'save_count': save_count,
                'reconstruction_seconds': reconstruction_seconds, 'signature_projection_seconds': inspection_seconds,
                'causal_inspection_seconds': causal_seconds,
                'save_bytes': town.state.path.stat().st_size,
                'process_peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}}


def evaluate_release_replay(*, long_horizon: bool = False,
                            scenarios: tuple[str, ...] = tuple(SCENARIOS)) -> dict:
    """Bounded matrix; private outputs are deleted even on a failing worker."""
    if not scenarios or any(name not in SCENARIOS for name in scenarios):
        raise ValueError('unknown release replay scenario')
    script = Path(__file__).resolve().parents[2] / 'scripts/evaluate_release_replay.py'
    results = []
    checks = {}
    with TemporaryDirectory(prefix='release-replay-') as directory:
        root = Path(directory)

        def run(name, days, label, hash_seed, resume=None):
            command = [sys.executable, str(script), '--worker', str(root / label),
                       '--scenario', name, '--days', str(days)]
            if resume:
                command += ['--resume', str(resume)]
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=900,
                                        env={**os.environ, 'PYTHONHASHSEED': str(hash_seed)})
            except subprocess.TimeoutExpired:
                checks[f'{name}:{label}:timeout'] = False
                return None
            # Never include uncontrolled worker logs/private exception values in public reports.
            if result.returncode:
                checks[f'{name}:{label}:worker_exit_{result.returncode}'] = False
                return None
            report = json.loads(result.stdout)
            results.append(report)
            checks[f'{name}:{label}:invariants'] = all(report['checks'].values())
            return report

        for name in scenarios:
            days = 390 if long_horizon else SCENARIOS[name][1]
            baseline = run(name, days, f'{name}-full', 1)
            if baseline is None:
                continue
            repeat = run(name, days, f'{name}-repeat', 77)
            checks[f'{name}:repeat_hash_seed'] = bool(repeat and repeat['signatures'] == baseline['signatures'])
            required = {'legacy': {'day-1', 'day-15'},
                        'procedural': {'institution', 'inventory-transfer'},
                        'collective': {'project-formation', 'one-contribution', 'before-completion', 'after-completion'}}[name]
            checks[f'{name}:boundaries_exercised'] = required <= baseline['checkpoints'].keys()
            for label in sorted(required & baseline['checkpoints'].keys()):
                resumed = run(name, days, f'{name}-{label}', 77,
                              root / f'{name}-full' / f'{label}.json')
                checks[f'{name}:{label}:continuation'] = bool(resumed and resumed['signatures'] == baseline['signatures'])
    return {'schema_version': 1, 'kind': 'release_replay', 'status': 'PASS' if all(checks.values()) else 'FAIL',
            'revision': _git_metadata(script.parents[1]),
            'environment': {'python': platform.python_version(), 'platform': platform.platform()},
            'checks': checks, 'runs': results,
            'rng_contract': 'V9 persisted state; legacy/V6 explicit harness RNG sidecar; engines remain process-isolated',
            'performance_contract': 'observations only; no noisy absolute timing gate'}
