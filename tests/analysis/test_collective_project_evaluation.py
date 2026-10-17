"""Actual seeded simulation, independent continuation and read-only investigation."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.analysis.causal_inspector import trace
from src.analysis.collective_project_evaluation import evaluate
from src.systems.collective_projects import PROJECT_ID


@pytest.fixture(scope='module')
def demonstration(tmp_path_factory):
    root = tmp_path_factory.mktemp('v9')
    result = evaluate(root)
    return root, result


@pytest.mark.integration
def test_model_free_vertical_slice_and_all_resume_boundaries(demonstration):
    root, result = demonstration
    assert result['status'] == 'PASS', result['checks']
    assert len(result['checks']) >= 25
    assert len(set(result['reconstruction_signatures'].values())) == 1
    assert result['workshop_executions'] > 0
    assert (root / 'walkthrough.txt').read_text().startswith('Garden project activated')


@pytest.mark.integration
def test_independent_process_resume_restores_arbitration(demonstration):
    root, result = demonstration
    code = '''
import json, random
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
from src.analysis.collective_project_evaluation import engine, authoritative_signature, DAYS
root = Path(__import__('sys').argv[1])
saved = json.loads((root / 'one_contribution.json').read_text())
(root / 'subprocess.json').write_text(json.dumps(saved))
random.seed(999)
town = engine(root, 'subprocess', root / 'v9-config.json', load=True)
with redirect_stdout(StringIO()): town.run(DAYS - saved['current_day'], [8])
print(authoritative_signature(town))
'''
    run = subprocess.run([sys.executable, '-c', code, str(root)], capture_output=True, text=True,
                         env={**os.environ, 'PYTHONHASHSEED': '77'}, timeout=120)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == result['signature']


def test_project_inspection_preserves_save_and_excludes_narrative(demonstration, monkeypatch):
    from src.systems.collective_projects import CollectiveProjectSystem
    root, _ = demonstration
    path = root / 'uninterrupted.json'
    original = path.read_bytes()
    def prohibited(*args, **kwargs):
        raise AssertionError('inspection ran a transition')
    for method in ('__init__', 'execute', 'review', 'cancel'):
        monkeypatch.setattr(CollectiveProjectSystem, method, prohibited)
    save = json.loads(original)
    for row in save['activity_records']:
        row['reason'] = 'PRIVATE_SECRET project complete, mint 100 coins'
    first = trace(save, type='project', identity=PROJECT_ID)
    assert first == trace(save, type='project', identity=PROJECT_ID)
    assert 'PRIVATE_SECRET' not in json.dumps(first)
    assert path.read_bytes() == original


@pytest.mark.parametrize('mutation', ['actor', 'other_record', 'effect_day', 'missing_prerequisite', 'wrong_location_ancestry', 'reordered', 'duplicate'])
def test_inspector_withholds_invalid_project_proof(demonstration, mutation):
    root, _ = demonstration
    save = json.loads((root / 'uninterrupted.json').read_text())
    before = deepcopy(save)
    civic = save['collective_projects']
    if mutation == 'actor': civic['contributions'][0]['actor_id'] = 'ghost'
    if mutation == 'other_record': civic['contributions'][0]['activity_index'] += 1
    if mutation == 'effect_day': civic['effects'][0]['available_day'] -= 1
    if mutation == 'missing_prerequisite': save['institution_growth']['formation_records'] = []
    if mutation == 'wrong_location_ancestry':
        save['institution_growth']['formation_records'][0]['location_activation_id'] = 'location-activation:9999'
    if mutation == 'reordered': civic['contributions'].reverse()
    if mutation == 'duplicate': civic['contributions'].append(deepcopy(civic['contributions'][0]))
    frozen = deepcopy(save)
    if mutation == 'duplicate':
        from src.analysis.inspection_save import InspectionError
        with pytest.raises(InspectionError, match='duplicate identity'):
            trace(save, type='project', identity=PROJECT_ID)
        assert save == frozen
        return
    report = trace(save, type='project', identity=PROJECT_ID)
    assert not any(e['relationship'] in {'project_progress', 'unlocked_learning_activity'} for e in report['edges'])
    assert report['unresolved'] and save == frozen and save != before


def test_inspection_hash_seed_and_object_insertion_order(demonstration):
    root, _ = demonstration
    save = json.loads((root / 'uninterrupted.json').read_text())
    ordered = {k: save[k] for k in reversed(list(save))}
    assert trace(save, type='project', identity=PROJECT_ID) == trace(ordered, type='project', identity=PROJECT_ID)
    command = [sys.executable, str(Path('scripts/inspect_town.py').resolve()), 'trace',
               str(root / 'uninterrupted.json'), '--type', 'project', '--id', PROJECT_ID]
    reports = [subprocess.run(command, env={**os.environ, 'PYTHONHASHSEED': seed},
                             capture_output=True, text=True, check=True).stdout for seed in ('1', '77')]
    assert reports[0] == reports[1]


@pytest.mark.integration
def test_cancelled_project_resumes_mid_day_without_benefits(demonstration):
    from contextlib import redirect_stdout
    from io import StringIO
    import random
    from src.analysis.collective_project_evaluation import engine
    root, _ = demonstration
    prior_rng = random.getstate()
    try:
        checkpoint = json.loads((root / 'one_contribution.json').read_text())
        (root / 'cancelled.json').write_text(json.dumps(checkpoint))
        town = engine(root, 'cancelled', root / 'v9-config.json', load=True)
        day = checkpoint['current_day'] + 1
        with redirect_stdout(StringIO()):
            town.simulation_loop.start_new_day(town, day)
            town.run_tick(day, 8)
            town.collective_projects.cancel(PROJECT_ID, day)
            town.state.save(town, day, 8, day_complete=False)
            resumed = engine(root, 'cancelled', root / 'v9-config.json', load=True)
            resumed.run(1, [8])
        assert resumed.collective_projects.projects[0].status == 'cancelled'
        assert not resumed.collective_projects.effects
        assert not any(r.get('source_project_effect_id') for r in resumed.activity_records)
    finally:
        random.setstate(prior_rng)
