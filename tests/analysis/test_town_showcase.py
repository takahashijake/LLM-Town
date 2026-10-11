"""Real one-command simulation, fresh replay and hostile package boundaries."""
from copy import deepcopy
from hashlib import sha256
import json
import os
import subprocess
import sys

import pytest

from src.analysis.inspection_save import InspectionError
from src.analysis.observatory import canonical
from src.analysis.town_showcase import build_package, validate_package, verify_package


@pytest.fixture(scope='module')
def package(tmp_path_factory):
    root = tmp_path_factory.mktemp('observatory') / 'package'
    run = subprocess.run([sys.executable, 'scripts/showcase_town.py', '--output', str(root)],
        capture_output=True, text=True, timeout=600, env={**os.environ, 'PYTHONHASHSEED': '1'})
    assert run.returncode == 0, run.stderr
    return root, json.loads(run.stdout), json.loads((root / 'observatory.json').read_text())


@pytest.mark.integration
def test_showcase_contract_and_integrated_lifecycle(package):
    root, manifest, bundle = package
    assert manifest == validate_package(root)
    assert (root / 'index.html').read_text().startswith('<!doctype html>')
    assert not list(root.glob('*logs*')) and not list(root.glob('*uninterrupted*'))
    garden, commerce = bundle['scenarios']
    assert len(garden['checkpoints']) == 6 and len(commerce['checkpoints']) == 2
    initial, final = garden['checkpoints'][0], garden['checkpoints'][-1]
    assert initial['metrics']['population']['value'] == 4
    assert final['metrics']['population']['value'] == 6
    assert final['metrics']['active_locations']['value'] == 6
    assert final['metrics']['institutions']['value'] > 0
    assert final['metrics']['employment']['value'] > initial['metrics']['employment']['value']
    assert final['metrics']['contributions']['value'] == 4
    assert final['metrics']['completed_effects']['value'] == 1
    assert final['metrics']['workshops']['value'] == 6
    assert garden['checkpoints'][2]['metrics']['completed_effects']['value'] == 0
    assert len(set(garden['verification']['reconstruction_signatures'].values())) == 1
    assert all(garden['verification']['checks'].values())
    assert all(commerce['verification']['checks'].values())
    trace = final['traces'][0]
    assert {'verified_civic_work', 'project_progress', 'unlocked_learning_activity', 'enabled_workshop_execution'} <= {e['relationship'] for e in trace['edges']}
    assert {'produced_lot', 'consumed_input', 'payment_leg', 'goods_leg'} <= {e['relationship'] for t in commerce['checkpoints'][-1]['traces'] for e in t['edges']}


@pytest.mark.integration
def test_full_independent_replay_second_hash_seed(package):
    root, manifest, _ = package
    run = subprocess.run([sys.executable, 'scripts/showcase_town.py', '--verify', str(root)],
        capture_output=True, text=True, timeout=600, env={**os.environ, 'PYTHONHASHSEED': '77'})
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result['status'] == 'PASS' and result['fingerprint'] == manifest['fingerprint']


@pytest.mark.integration
def test_bounded_chronology_and_cross_reference_integrity(package):
    _, _, bundle = package
    for scenario in bundle['scenarios']:
        for cp in scenario['checkpoints']:
            resident_ids = {e['id'] for e in cp['entities'] if e['type'] == 'resident'}
            locations = {e['id'] for e in cp['entities'] if e['type'] == 'location'}
            assert not cp['uncertainties']
            order = [(e['day'] if e['day'] is not None else -1, e['hour'] if e['hour'] is not None else -1, e['source'], e['id']) for e in cp['events']]
            assert order == sorted(order)
            for event in cp['events']:
                if event['source'] == 'activities':
                    assert event['fields']['agent_id'] in resident_ids
                    assert event['fields']['location'] in locations


@pytest.mark.integration
def test_public_exports_exclude_sensitive_fields(package):
    root, manifest, _ = package
    forbidden = {'memory', 'memory_archive', 'reputation_beliefs', 'daily_journals', 'recent_dialogues', 'recent_actions', 'personality', 'raw_prompt', 'reason', 'description', 'name', 'content'}
    def check(value):
        if isinstance(value, dict):
            assert not forbidden & value.keys()
            for child in value.values(): check(child)
        elif isinstance(value, list):
            for child in value: check(child)
    for name in manifest['files']:
        if name.endswith('.json'):
            value = json.loads((root/name).read_text())
            # Scenario descriptions and finite policy/config prose are trusted input,
            # deliberately separate from public saved authority projections.
            if name == 'observatory.json':
                for scenario in value['scenarios']:
                    check(scenario['checkpoints'])
            else: check(value)


@pytest.mark.integration
@pytest.mark.parametrize('attack', ['path', 'symlink', 'size', 'digest', 'missing', 'schema', 'revision'])
def test_hostile_manifest_never_executes_or_reads_arbitrary_path(package, tmp_path, monkeypatch, attack):
    import src.analysis.town_showcase as showcase
    root, manifest, _ = package
    target = tmp_path / 'copied'; target.mkdir()
    for name in manifest['files']:
        (target / name).write_bytes((root/name).read_bytes())
    data = deepcopy(manifest)
    if attack == 'path': data['files']['../secret'] = data['files'].pop('index.html')
    if attack == 'symlink':
        (target/'index.html').unlink(); (target/'index.html').symlink_to(root/'index.html')
    if attack == 'size': data['files']['index.html']['bytes'] = 100_000_000
    if attack == 'digest': (target/'index.html').write_text('forged')
    if attack == 'missing': (target/'index.html').unlink()
    if attack == 'schema': data['schema_version'] = 99
    if attack == 'revision': data['revision'] = 'other'
    (target/'manifest.json').write_bytes(canonical(data))
    def prohibited(*a, **kw): raise AssertionError('executed scenario before validating input')
    monkeypatch.setattr(showcase, 'build_package', prohibited)
    with pytest.raises(InspectionError): verify_package(target)


@pytest.mark.integration
def test_coherent_manifest_forgery_cannot_pass_replay(package, tmp_path, monkeypatch):
    import src.analysis.town_showcase as showcase
    root, manifest, _ = package
    target = tmp_path/'copy'; target.mkdir()
    for name in manifest['files']: (target/name).write_bytes((root/name).read_bytes())
    forged = deepcopy(manifest); body=b'changed report\n'; (target/'walkthrough.txt').write_bytes(body)
    forged['files']['walkthrough.txt'] = {'sha256': sha256(body).hexdigest(), 'bytes': len(body)}
    (target/'manifest.json').write_bytes(canonical(forged))
    assert validate_package(target) == forged  # Internal consistency alone is not authenticity.
    monkeypatch.setattr(showcase, 'build_package', lambda _: manifest)
    with pytest.raises(InspectionError, match='differs'): verify_package(target)


def test_output_directory_never_overwrites_existing_files(tmp_path):
    (tmp_path/'important').write_text('keep')
    with pytest.raises(InspectionError, match='new directory'): build_package(tmp_path)
    assert (tmp_path/'important').read_text() == 'keep'


def test_empty_partial_and_duplicate_manifest(tmp_path):
    for payload in ['{}', '{"schema_version":1}', '{"schema_version":1,"schema_version":1}']:
        (tmp_path/'manifest.json').write_text(payload)
        with pytest.raises(InspectionError): validate_package(tmp_path)
