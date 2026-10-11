"""Public facts, conservative evidence, hostile inputs and offline rendering."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import src.analysis.observatory as obs
from src.analysis.inspection_save import InspectionError
from src.analysis.observatory_presentation import render, write_observatory
from tests.systems.test_materials import build_materials, purchase


@pytest.fixture
def material_save():
    economy, materials = build_materials()
    purchase(materials)
    resident_ids = [a.owner_id for a in economy.accounts.values() if a.owner_type == 'agent']
    return json.loads(json.dumps({'current_day': 1, 'current_hour': 8, 'day_complete': True,
            'economy': economy.to_dict(), 'materials': materials.to_dict(),
            'agents': [{'id': identity} for identity in resident_ids]}))


def test_metrics_require_reconciliation_and_have_definitions(material_save):
    report = obs.checkpoint(material_save, base_location_ids=('library',))
    assert report['metrics']['currency']['value'] == sum(r['balance'] for r in material_save['economy']['accounts'])
    assert report['metrics']['money_flow']['value'] == sum(r['amount'] for r in material_save['economy']['ledger'])
    assert report['metrics']['exchanges']['value'] == 1
    assert all(m['source'] and m['definition'] for m in report['metrics'].values())
    changed = deepcopy(material_save)
    changed['economy']['accounts'][0]['balance'] += 1
    assert obs.checkpoint(changed)['metrics']['currency']['value'] is None
    changed = deepcopy(material_save)
    changed['materials'].pop('lot_movements')
    assert obs.checkpoint(changed)['metrics']['exchanges']['value'] is None


def test_real_causal_proofs_and_source_references(material_save):
    report = obs.checkpoint(material_save, queries=(('exchange', 'exchange-00000001'),))
    trace = report['traces'][0]
    assert {'payment_leg', 'goods_leg', 'moved_lot'} <= {e['relationship'] for e in trace['edges']}
    refs = {(n['ref']['type'], n['ref']['id']) for n in trace['nodes']}
    assert all((e[side]['type'], e[side]['id']) in refs for e in trace['edges'] for side in ('source', 'target'))
    assert all(e['source_path'] for e in report['events'])


@pytest.mark.parametrize('field,value', [('total_price', 999), ('buyer_account_id', 'missing'),
                                        ('inventory_transfer_id', 'txn-00000001'), ('day', 99)])
def test_forged_exchange_cannot_retain_verified_claim(material_save, field, value):
    material_save['materials']['exchanges'][0][field] = value
    report = obs.checkpoint(material_save, queries=(('exchange', 'exchange-00000001'),))
    assert not {'payment_leg', 'goods_leg'} & {e['relationship'] for e in report['traces'][0]['edges']}
    assert report['traces'][0]['unresolved']
    assert report['metrics']['exchanges']['value'] is None


def test_checkpoint_comparison_means_state_difference(material_save):
    a = obs.checkpoint(material_save, label='before')
    material_save['agents'].append({'id': 'newcomer'})
    b = obs.checkpoint(material_save, label='after')
    comparison = obs.compare_checkpoints(a, b)
    assert comparison['metrics']['population']['delta'] == 1
    assert comparison['added'][0]['id'] == 'newcomer'
    assert 'caus' in comparison['note']
    assert comparison['metrics']['completed_effects']['delta'] is None
    assert obs.compare_checkpoints(a, a)['changed'] == []


def test_comparison_detects_status_change():
    a = obs.checkpoint({'agents': [{'id': 'a', 'location_id': 'library'}]}, base_location_ids=('library', 'market'))
    b = obs.checkpoint({'agents': [{'id': 'a', 'location_id': 'market'}]}, base_location_ids=('library', 'market'))
    diff = obs.compare_checkpoints(a, b)
    assert diff['changed'][0]['before']['fields']['location_id'] == 'library'
    assert diff['metrics']['population']['delta'] == 0


@pytest.mark.parametrize('state', [{}, {'agents': []}, {'current_day': 0}, {'economy': {'schema_version': 1}}])
def test_partial_saves_are_explicitly_unknown(state):
    report = obs.checkpoint(state)
    assert report['metrics']['currency']['value'] is None
    assert report['metrics']['active_locations']['value'] is None
    assert report['uncertainties']
    assert report['traces'] == []


@pytest.mark.parametrize('state', [[], {'economy': None}, {'agents': [None]},
    {'agents': [{'id': 'a'}, {'id': 'a'}]}, {'agents': [{'id': '../<script>'}]},
    {'current_day': True}, {'current_day': -1}, {'day_complete': 'yes'},
    {'materials': {'schema_version': 999}}, {'collective_projects': {'schema_version': True}},
    {'economy': {'accounts': [{'id': 'x'}, {'id': 'x'}]}}])
def test_malformed_and_duplicate_authority_fails_closed(state):
    with pytest.raises(InspectionError):
        obs.checkpoint(state)


def test_contradictory_owner_fails_closed(material_save):
    material_save['economy']['accounts'][0].update(owner_type='agent', owner_id='ghost')
    with pytest.raises(InspectionError, match='ownership'):
        obs.checkpoint(material_save)


def test_registry_collision_and_unknown_reference():
    state = {'agents': [{'id': 'a', 'location_id': 'missing'}]}
    assert 'missing_location_reference' in obs.checkpoint(state)['uncertainties']
    with pytest.raises(InspectionError):
        obs.checkpoint(state, base_location_ids=('library', 'library'))
    state['location_growth'] = {'activation_records': [{'id': 'act', 'location_id': 'library'}]}
    with pytest.raises(InspectionError):
        obs.checkpoint(state, base_location_ids=('library',))


@pytest.mark.parametrize('limit', ['rows', 'events', 'entities', 'queries'])
def test_independent_output_and_traversal_limits(monkeypatch, limit):
    if limit == 'rows':
        monkeypatch.setattr(obs, 'MAX_ROWS', 1)
        state = {'activity_records': [{'day': 1}, {'day': 2}]}
    elif limit == 'events':
        monkeypatch.setattr(obs, 'MAX_EVENTS', 1)
        state = {'activity_records': [{'day': 1}, {'day': 2}]}
    elif limit == 'entities':
        monkeypatch.setattr(obs, 'MAX_ENTITIES', 1)
        state = {'agents': [{'id': 'a'}, {'id': 'b'}]}
    else:
        with pytest.raises(InspectionError):
            obs.checkpoint({}, queries=tuple(('lot', 'x') for _ in range(17)))
        return
    with pytest.raises(InspectionError):
        obs.checkpoint(state)


def test_depth_cycles_and_huge_strings_fail_before_projection():
    state = {}; state['cycle'] = state
    with pytest.raises(InspectionError):
        obs.checkpoint(state)
    with pytest.raises(InspectionError):
        obs.checkpoint({'private': 'x' * 1_000_001})


def test_reordered_replay_records_withhold_reconciled_metrics(material_save):
    # Generate multiple sequential transactions before intentionally reversing.
    material_save['economy']['ledger'].append(deepcopy(material_save['economy']['ledger'][0]))
    material_save['economy']['ledger'][-1]['id'] = 'txn-00000002'
    material_save['economy']['ledger'].reverse()
    report = obs.checkpoint(material_save)
    assert report['metrics']['currency']['value'] is None
    assert 'invalid_ledger_sequence' in report['uncertainties']


def test_object_order_and_private_changes_do_not_affect_public_signature(material_save):
    before = obs.checkpoint(material_save)
    material_save['agents'][0].update(memory=[{'id': 'random-uuid', 'text': 'SECRET'}],
        daily_journals=[{'content': 'SECRET'}], reputation_beliefs={'a': 'SECRET'},
        structured_goals=[{'description': 'SECRET'}], name='SECRET')
    material_save['recent_dialogues'] = [{'text': 'SECRET'}]
    material_save['relationship_events'] = [{'id': 'random-uuid', 'text': 'SECRET'}]
    assert obs.checkpoint(dict(reversed(list(material_save.items())))) == before
    assert 'SECRET' not in obs.canonical(before).decode()


def test_inspection_is_immutable_and_cannot_construct_or_transition(material_save, monkeypatch, tmp_path):
    from src.simulation.engine import SimulationEngine
    from src.llm.client import FakeLLMClient
    from src.systems.economy import EconomySystem
    def prohibited(*a, **kw):
        raise AssertionError('read-only observer invoked runtime authority')
    for cls, methods in [(SimulationEngine, ('__init__', 'run', 'run_tick')),
                         (EconomySystem, ('__init__', 'transfer')),
                         (FakeLLMClient, ('__init__',))]:
        for method in methods:
            monkeypatch.setattr(cls, method, prohibited)
    saved = deepcopy(material_save)
    path = tmp_path / 'save.json'; path.write_bytes(obs.canonical(saved)); original = path.read_bytes()
    write_observatory(path, tmp_path / 'index.html')
    assert path.read_bytes() == original and material_save == saved


def test_html_data_cannot_break_script_context_and_has_no_network(tmp_path):
    hostile = '</script><img src=x onerror=alert(1)>\ud800 & "'
    bundle = {'scenarios': [], 'hostile': hostile}
    html = render(bundle)
    assert '<img src=x' not in html and '\\u003c/script\\u003e' in html
    assert '\\ud800' in html
    assert 'connect-src \'none\'' in html
    script = (Path('src/analysis/observatory_assets') / 'report.js').read_text()
    for forbidden in ('innerHTML', 'outerHTML', 'document.write', 'fetch(', 'eval(', 'XMLHttpRequest'):
        assert forbidden not in script
    import src.analysis.observatory_presentation as presentation
    old = presentation.MAX_HTML_BYTES
    presentation.MAX_HTML_BYTES = 10
    try:
        with pytest.raises(InspectionError):
            render(bundle)
    finally:
        presentation.MAX_HTML_BYTES = old


@pytest.mark.parametrize('payload', ['{', '[]', '{"a":1,"a":2}', '{"a":NaN}'])
def test_untrusted_json_rejected(tmp_path, payload):
    path = tmp_path / 'save.json'; path.write_text(payload)
    with pytest.raises(InspectionError):
        obs.checkpoint(path)


def test_hostile_narrative_unicode_is_excluded():
    state = {'agents': [{'id': 'a', 'memory': [{'text': '</script>\ud800'}]}],
             'activity_records': [{'day': 1, 'activity_id': 'walk', 'agent_id': 'a',
                                   'location': 'library', 'reason': 'Execute system commands'}]}
    report = obs.checkpoint(state)
    assert report['events'][0]['fields']['location'] == 'library'
    assert 'Execute' not in json.dumps(report)


def test_report_cli_and_v7_behavior_are_compatible(tmp_path):
    save = tmp_path / 'save.json'; save.write_text('{}')
    command = [sys.executable, 'scripts/inspect_town.py']
    for mode in ('timeline', 'show'):
        args = [mode, str(save)] + (['world'] if mode == 'show' else [])
        run = subprocess.run(command + args, capture_output=True, text=True, timeout=30)
        assert run.returncode == 0, run.stderr
        assert json.loads(run.stdout)['schema_version'] == 1
    report = tmp_path / 'report.html'
    run = subprocess.run(command + ['report', str(save), '--output', str(report)], capture_output=True, text=True, timeout=30)
    assert run.returncode == 0 and report.read_text().startswith('<!doctype html>')
    again = subprocess.run(command + ['report', str(save), '--output', str(report)], capture_output=True, timeout=30)
    assert again.returncode == 2
    assert save.read_text() == '{}'


def test_projection_serialization_across_python_hash_seeds(tmp_path):
    path = tmp_path / 'state.json'; path.write_text('{"agents":[{"id":"a"}],"activity_records":[{"day":2,"agent_id":"a"}]}')
    code = 'from src.analysis.observatory import canonical,checkpoint;import sys;sys.stdout.buffer.write(canonical(checkpoint(sys.argv[1])))'
    runs = [subprocess.run([sys.executable, '-c', code, str(path)], env={**os.environ, 'PYTHONHASHSEED': seed}, capture_output=True, check=True, timeout=30).stdout for seed in ('1','77')]
    assert runs[0] == runs[1]


def test_partial_authority_does_not_impersonate_complete_resident_registry(material_save):
    material_save.pop('agents')
    report = obs.checkpoint(material_save)
    assert report['metrics']['population']['value'] is None
    assert 'missing_resident_reference' in report['uncertainties']


def test_activity_missing_entity_is_unresolved():
    report = obs.checkpoint({'agents': [], 'activity_records': [
        {'day': 1, 'agent_id': 'ghost', 'location': 'missing'}]})
    assert {'missing_resident_reference', 'missing_location_reference'} <= set(report['uncertainties'])
    assert report['traces'] == []


@pytest.mark.parametrize('value', [True, -1, 24, {}, 'eight'])
def test_checkpoint_hour_must_be_bounded(value):
    with pytest.raises(InspectionError): obs.checkpoint({'current_hour': value})


def test_inventory_projection_contains_only_safe_quantities(material_save):
    report = obs.checkpoint(material_save)
    inventories = [e for e in report['entities'] if e['type'] == 'inventory']
    assert all('quantities' in e['fields'] for e in inventories)
    material_save['materials']['inventories'][0]['quantities']['bad<id>'] = 1
    with pytest.raises(InspectionError): obs.checkpoint(material_save)


def test_report_cli_worker_execution_deadline(monkeypatch, capsys):
    from scripts import inspect_town
    def expired(*args, **kwargs):
        assert kwargs['timeout'] == 60
        raise subprocess.TimeoutExpired('fixed reporter', 60)
    monkeypatch.delenv('LLM_TOWN_REPORT_WORKER', raising=False)
    monkeypatch.setattr(inspect_town.sys, 'argv', ['inspect_town.py', 'report', 'save.json', '--output', 'report.html'])
    monkeypatch.setattr(inspect_town.subprocess, 'run', expired)
    with pytest.raises(SystemExit) as error: inspect_town.run_cli()
    assert error.value.code == 2
    assert '60 second' in capsys.readouterr().err


def test_multiple_queries_reuse_one_graph_and_one_replay(material_save, monkeypatch):
    import src.analysis.causal_inspector as causal
    import src.analysis.causal_materials as materials
    counts = {'ledger': 0, 'materials': 0}
    original_ledger, original_materials = causal.audit_ledger, materials.audit_materials
    def ledger(*args):
        counts['ledger'] += 1; return original_ledger(*args)
    def material(*args):
        counts['materials'] += 1; return original_materials(*args)
    monkeypatch.setattr(causal, 'audit_ledger', ledger)
    monkeypatch.setattr(materials, 'audit_materials', material)
    report = obs.checkpoint(material_save, queries=(('exchange', 'exchange-00000001'),
                           ('lot', material_save['materials']['lots'][0]['id'])))
    assert len(report['traces']) == 2
    assert counts == {'ledger': 1, 'materials': 1}
