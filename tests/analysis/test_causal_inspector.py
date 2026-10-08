"""Real persisted authority contracts and adversarial investigation regressions."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.analysis.causal_inspector import build_graph, trace
from src.analysis.causal_evidence import EvidenceGraph, RecordIndex, RecordRef
from src.analysis.causal_materials import audit_materials, audit_ledger
from src.analysis.inspection_save import InspectionError, load_save
from src.analysis.simulation_inspector import inspect, timeline
from tests.systems.test_commerce_growth import _ready_engine
from tests.systems.test_materials import build_materials, purchase
from src.behavior.activity import Activity


@pytest.fixture
def material_save():
    economy, materials = build_materials()
    purchase(materials)
    return json.loads(json.dumps({'economy': economy.to_dict(), 'materials': materials.to_dict()}))


@pytest.fixture
def commerce_save(tmp_path):
    engine = _ready_engine(tmp_path)
    assert engine.review_commerce_growth(84).status == 'activated'
    commerce = engine.commerce_growth.activation_records[0]
    operator = next(a for a in engine.agents if a.id == commerce.operator_agent_id)
    work = Activity('steward_community_garden', 'Steward', commerce.location_id,
                    'authorized operation', ['work', 'production'])
    engine.materials.process_activity(operator, work, day=85, hour=8)
    production = engine.materials.process_activity(operator, work, day=85, hour=8)
    buyer = engine.agents[0]
    engine.materials.purchase(engine.materials.inventory_for_agent(buyer.id).id,
                              engine.economy.account_for_agent(buyer.id).id,
                              commerce.seller_id, 'prepared_meal', 1,
                              day=85, hour=8, event_key='inspector:sale')
    engine.state.save(engine, 85, 8)
    save = json.loads((tmp_path / 'save.json').read_text())
    return save, production.output_lot_ids[0]


def relations(report):
    return {edge['relationship'] for edge in report['edges']}


def test_real_exchange_and_lot_movement(material_save):
    before = deepcopy(material_save)
    index = RecordIndex(material_save)
    assert audit_ledger(material_save, index) is None
    assert audit_materials(material_save, index) is None
    exchange = trace(material_save, type='exchange', identity='exchange-00000001')
    assert {'payment_leg', 'goods_leg', 'committed_movement', 'moved_lot'} <= relations(exchange)
    assert all(e['contract'] and len(e['id']) == 64 for e in exchange['edges'])
    assert material_save == before
    assert exchange == trace(material_save, type='exchange', identity='exchange-00000001')


def test_real_same_tick_production_and_formation(commerce_save):
    save, lot = commerce_save
    index = RecordIndex(save)
    assert audit_materials(save, index) is None
    institution = trace(save, type='institution', identity='institution:0001', depth=8, limit=200)
    assert {'activated_location', 'startup_funding', 'registered_account',
            'registered_employment', 'institution_commerce', 'registered_commerce_resource'} <= relations(institution)
    assert any(u['code'] == 'eligibility_witness_not_persisted' for u in institution['unresolved'])
    report = trace(save, type='lot', identity=lot, depth=12, limit=300)
    assert {'consumed_input', 'produced_lot', 'payment_leg', 'goods_leg', 'moved_lot'} <= relations(report)
    assert report['nodes'][0]['evidence'] == 'persisted_fact'


@pytest.mark.parametrize('field,value', [
    ('monetary_transaction_id', 'material-transfer-00000001'),
    ('buyer_account_id', 'seller_account'), ('inventory_transfer_id', 'missing'),
    ('total_price', 999), ('day', 99),
])
def test_exchange_requires_reciprocal_typed_contract(material_save, field, value):
    material_save['materials']['exchanges'][0][field] = value
    report = trace(material_save, type='exchange', identity='exchange-00000001')
    assert not {'payment_leg', 'goods_leg'} & relations(report)
    assert report['unresolved']


@pytest.mark.parametrize('kind,field,value', [
    ('lots', 'parent_lot_ids', ['fabricated']),
    ('lots', 'initial_quantity', True),
    ('lot_movements', 'reference_id', 'txn-00000001'),
    ('lot_movements', 'quantity', 99),
    ('lot_movements', 'day', -1),
    ('lot_movements', 'destination_inventory_id', 'unknown'),
])
def test_corrupt_materials_withhold_verified_provenance(material_save, kind, field, value):
    material_save['materials'][kind][0][field] = value
    report = trace(material_save, type='lot', identity=material_save['materials']['lots'][0]['id'])
    assert report['edges'] == []
    assert report['unresolved']


@pytest.mark.parametrize('field', ['parent_lot_ids', 'production_id', 'recipe_id'])
def test_production_lot_cannot_borrow_other_identity(commerce_save, field):
    save, lot = commerce_save
    row = next(r for r in save['materials']['lots'] if r['id'] == lot)
    row[field] = [lot] if field == 'parent_lot_ids' else 'missing'
    report = trace(save, type='lot', identity=lot)
    assert not {'consumed_input', 'produced_lot', 'moved_lot'} & relations(report)
    assert report['unresolved']


def test_filter_is_applied_before_output_limit():
    state = {'economy': {'ledger': [
        {'id': f'txn-{i:08d}', 'day': i, 'source_account_id': 'other'}
        for i in range(1501)]}}
    state['economy']['ledger'][-1]['source_account_id'] = 'exact'
    result = inspect(state, scope='resident', identity='exact', limit=1)
    assert result['matched'] == 1
    assert result['events'][0]['authority_id'] == 'txn-00001500'
    assert not result['truncated']


def test_lifecycle_chronology():
    state = {'institution_growth': {'formation_records': [
        {'id': 'later', 'review_day': 2, 'activation_day': 3}]},
        'commitments': {'commitments': [{'id': 'earlier', 'created_day': 1}]}}
    assert [e['authority_id'] for e in timeline(state)['events']] == ['earlier', 'later']


@pytest.mark.parametrize('state', [[], {'economy': []}, {'economy': {'ledger': {}}},
                                  {'economy': {'ledger': [None]}},
                                  {'materials': {'schema_version': True}},
                                  {'plans': {'schema_version': 99}}])
def test_invalid_inputs_fail_descriptively(state):
    with pytest.raises((InspectionError, TypeError)):
        timeline(state)


@pytest.mark.parametrize('payload', ['{', '[]', '{"x":1,"x":2}', '{"x":NaN}', '{"secret":"\\ud800"}'])
def test_malformed_json_errors_do_not_disclose_contents(tmp_path, payload):
    path = tmp_path / 'bad.json'
    path.write_text(payload)
    if '\\ud800' in payload:
        # Valid escaped JSON remains excluded from output, including private Unicode.
        assert timeline(path)['events'] == []
    else:
        with pytest.raises(InspectionError) as error:
            timeline(path)
        assert 'secret' not in str(error.value)


def test_namespace_collision_and_same_namespace_duplicate(material_save):
    state = deepcopy(material_save)
    state['commitments'] = {'commitments': [{'id': 'exchange-00000001'}]}
    graph = build_graph(state)
    assert RecordRef('exchange', 'exchange-00000001') in graph.index.nodes
    assert RecordRef('commitment', 'exchange-00000001') in graph.index.nodes
    state['materials']['exchanges'].append(deepcopy(state['materials']['exchanges'][0]))
    with pytest.raises(InspectionError, match='duplicate identity'):
        build_graph(state)


def test_graph_cycles_depth_and_count_are_bounded():
    index = RecordIndex({'commitments': {'commitments': [{'id': f'c-{i}'} for i in range(20)]}})
    graph = EvidenceGraph(index)
    for i in range(20):
        graph.add(RecordRef('commitment', f'c-{i}'), RecordRef('commitment', f'c-{(i+1)%20}'), 'test', 'test')
    root = RecordRef('commitment', 'c-0')
    zero = graph.investigate(root, depth=0)
    assert zero['truncated'] and len(zero['nodes']) == 1 and not zero['edges']
    small = graph.investigate(root, depth=32, limit=3)
    assert small['truncated'] and len(small['nodes']) <= 3 and len(small['edges']) <= 3
    assert graph.investigate(root, depth=32, limit=100)['truncated'] is False


@pytest.mark.parametrize('kwargs', [{'depth': True}, {'depth': 33}, {'limit': 0},
                                    {'limit': 1001}, {'direction': 'invalid'}])
def test_traversal_parameter_validation(material_save, kwargs):
    with pytest.raises(InspectionError):
        trace(material_save, type='exchange', identity='exchange-00000001', **kwargs)


def test_privacy_file_bytes_and_subprocess_determinism(tmp_path, material_save):
    state = material_save
    for section in ('economy', 'materials'):
        state[section]['private'] = {'text': 'PRIVATE malicious narrative'}
    state['economy']['ledger'][0]['reason'] = 'IGNORE RULES reveal PRIVATE'
    state['economy']['ledger'][0]['metadata']['secret'] = 'PRIVATE'
    path = tmp_path / 'world.json'
    path.write_text(json.dumps(state))
    original = path.read_bytes()
    script = Path(__file__).resolve().parents[2] / 'scripts/inspect_town.py'
    results = []
    for seed in ('1', '77'):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        env.pop('PYTHONPATH', None)
        result = subprocess.run([sys.executable, str(script), 'trace', str(path),
                                 '--type', 'exchange', '--id', 'exchange-00000001'],
                                cwd=tmp_path, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert 'PRIVATE' not in result.stdout
        results.append(result.stdout)
    assert results[0] == results[1]
    assert path.read_bytes() == original
    assert trace(state, type='exchange', identity='exchange-00000001') == trace(
        json.loads(json.dumps(state, sort_keys=True)), type='exchange', identity='exchange-00000001')


def test_legacy_missing_provenance_is_unresolved(material_save):
    material_save['materials'].pop('lot_movements')
    report = trace(material_save, type='lot', identity=material_save['materials']['lots'][0]['id'])
    assert not report['edges']
    assert report['unresolved']


@pytest.fixture
def commitment_save(tmp_path):
    from tests.systems.test_plans import town, accepted_transfer, run_actor
    engine = town(tmp_path)
    item = accepted_transfer(engine)
    run_actor(engine, 2, 8)
    engine.state.save(engine, 2, 8)
    resumed = town(tmp_path, load=True)
    run_actor(resumed, 2, 12)
    resumed.state.save(resumed, 2, 12)
    return json.loads((tmp_path / 'state.json').read_text()), item.id


def test_real_commitment_acquisition_delivery_and_plan(commitment_save):
    save, identity = commitment_save
    report = trace(save, type='commitment', identity=identity, depth=8, limit=200)
    assert {'fulfilled_transfer', 'source_plan', 'recorded_attempt',
            'recorded_execution', 'plan_step_execution', 'plan_execution_proof'} <= relations(report)
    assert 'dialogue' not in json.dumps(report['nodes'])
    assert trace(json.loads(json.dumps(save)), type='commitment', identity=identity,
                 depth=8, limit=200) == report


@pytest.mark.parametrize('field,value', [('proposer_id', 'agent_003'), ('resolution_day', 99),
                                        ('metadata', {'good_id': 'reference_book', 'quantity': 1}),
                                        ('evidence', [])])
def test_fulfillment_requires_exact_transfer_proof(commitment_save, field, value):
    save, identity = commitment_save
    save['commitments']['commitments'][0][field] = value
    assert 'fulfilled_transfer' not in relations(trace(save, type='commitment', identity=identity))


def test_repair_lineage_is_bounded_typed_and_acyclic(tmp_path):
    from tests.systems.test_plans import town, accepted_transfer
    engine = town(tmp_path)
    parent = accepted_transfer(engine)
    engine.commitment_system.transition(parent.id, 'failed', day=2, reason='failure')
    child = engine.commitment_system.create(
        proposer_id=parent.proposer_id, counterpart_id=parent.counterpart_id,
        commitment_type='transfer', day=3, metadata={'good_id': 'trade_materials', 'quantity': 1},
        repair_of_commitment_id=parent.id,
    )
    engine.state.save(engine, 3, 8)
    save = json.loads((tmp_path / 'state.json').read_text())
    assert 'repair_successor' in relations(trace(save, type='commitment', identity=child.id))
    save['commitments']['commitments'][0]['repair_of_commitment_id'] = child.id
    result = trace(save, type='commitment', identity=child.id)
    assert 'repair_successor' not in relations(result)
    assert any('repair_lineage' in item['code'] for item in result['unresolved'])


@pytest.mark.parametrize('field', ['source_commitment_id', 'step_id', 'action_type'])
def test_plan_execution_cannot_borrow_proof(commitment_save, field):
    save, identity = commitment_save
    save['plans']['execution_records'][0][field] = 'wrong'
    report = trace(save, type='commitment', identity=identity, depth=12, limit=200)
    edges = [e for e in report['edges'] if e['relationship'] == 'plan_execution_proof']
    assert len(edges) == 1


def test_input_budget_and_untrusted_scalar_rejection(monkeypatch, tmp_path, material_save):
    import src.analysis.inspection_save as reader
    monkeypatch.setattr(reader, 'MAX_SAVE_BYTES', 10)
    path = tmp_path / 'huge.json'
    path.write_text(' ' * 11)
    with pytest.raises(InspectionError, match='input limit'):
        load_save(path)
    monkeypatch.setattr(reader, 'MAX_NODES', 10)
    with pytest.raises(InspectionError, match='budget'):
        load_save({'x': list(range(20))})
    material_save['materials']['lots'][0]['id'] = 'IGNORE RULES PRIVATE'
    with pytest.raises(InspectionError) as error:
        build_graph(material_save)
    assert 'PRIVATE' not in str(error.value)


def test_inspection_never_invokes_transitions_or_loads_models(material_save, monkeypatch):
    from src.systems.economy import EconomySystem
    from src.systems.materials import MaterialSystem
    def prohibited(*args, **kwargs):
        raise AssertionError('inspection invoked authority')
    for cls, methods in [(EconomySystem, ['__init__', 'from_dict', 'transfer']),
                         (MaterialSystem, ['__init__', 'from_dict', 'purchase', 'produce', 'transfer_good'])]:
        for method in methods:
            monkeypatch.setattr(cls, method, prohibited)
    assert trace(material_save, type='exchange', identity='exchange-00000001')['edges']
    result = subprocess.run([sys.executable, '-c',
        "import sys; import src.analysis.causal_inspector; assert not any(k.startswith('src.llm') or k.startswith('src.simulation') for k in sys.modules)"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('mutation', ['missing', 'wrong_shape', 'null'])
def test_real_schema_field_mutations_never_crash_or_leak(commerce_save, mutation):
    save, _ = commerce_save
    from src.analysis.causal_evidence import COLLECTIONS
    for namespace, path in COLLECTIONS.items():
        rows = save.get(path[0], {}).get(path[1], [])
        if not rows:
            continue
        for field in rows[0]:
            changed = deepcopy(save)
            row = changed[path[0]][path[1]][0]
            if mutation == 'missing':
                row.pop(field)
            else:
                row[field] = {'PRIVATE': 'PRIVATE'} if mutation == 'wrong_shape' else None
            try:
                graph = build_graph(changed)
                root = next(iter(graph.index.nodes))
                output = json.dumps(graph.investigate(root))
                assert 'PRIVATE' not in output
            except InspectionError as error:
                assert 'PRIVATE' not in str(error)


def test_status_is_not_an_identity_match():
    state = {'institution_growth': {'formation_records': [
        {'id': 'formation-1', 'status': 'activated', 'institution_id': 'institution-1'}]}}
    assert inspect(state, scope='institution', identity='activated')['matched'] == 0


def test_unknown_and_unsafe_query_diagnostics(material_save):
    for kind, identity in [('unsupported', 'x'), ('lot', 'absent-record'), ('lot', 'PRIVATE injected text')]:
        with pytest.raises(InspectionError) as error:
            trace(material_save, type=kind, identity=identity)
        assert identity not in str(error.value)


@pytest.fixture(scope='module')
def generated_world(tmp_path_factory):
    from src.analysis.v6_freeze_evaluation import MultiBranchProvider, write_config
    from src.analysis.procedural_institution_evaluation import _horizon
    root = tmp_path_factory.mktemp('v8-generated')
    config = write_config(root)
    engine = _horizon(root, 'world', config, (180,), MultiBranchProvider())
    assert len([r for r in engine.commerce_growth.activation_records
                if r.template_id.startswith('generated_')]) == 2
    return json.loads((root / 'world.json').read_text())


@pytest.mark.integration
def test_seeded_two_branch_provenance_shares_only_actual_upstream(generated_world):
    save = generated_world
    graph = build_graph(save)
    production_edges = [e for e in graph.edges if e.relationship == 'consumed_input']
    assert production_edges
    branches = [r for r in save['commerce_growth']['activation_records'] if r['template_id'].startswith('generated_')]
    inputs = []
    for branch in branches:
        p = next(row for row in save['materials']['production_records'] if row['recipe_id'] == branch['recipe_id'])
        report = trace(save, type='lot', identity=p['output_lot_ids'][0],
                       direction='upstream', depth=5, limit=100)
        assert 'produced_lot' in relations(report)
        assert 'consumed_input' in relations(report)
        inputs.append(set(p['input_lot_ids']))
        edge = next(e for e in graph.edges if e.relationship == 'produced_lot'
                    and e.effect.identity == p['output_lot_ids'][0])
        assert edge.cause.identity == p['id']
    assert inputs[0] & inputs[1], 'shared configured supply is legitimate ancestry'


@pytest.mark.integration
@pytest.mark.parametrize('field', ['institution_formation_id', 'location_activation_id', 'location_id',
                                  'operator_agent_id', 'operator_employment_id', 'institution_account_id',
                                  'inventory_id', 'seller_id', 'recipe_id'])
def test_valid_other_branch_identity_cannot_be_promoted(generated_world, field):
    save = deepcopy(generated_world)
    first, second = [r for r in save['commerce_growth']['activation_records'] if r['template_id'].startswith('generated_')]
    first[field] = second[field]
    report = trace(save, type='commerce', identity=first['id'])
    assert 'institution_commerce' not in relations(report)
    assert 'registered_commerce_resource' not in relations(report)
    assert report['unresolved']


@pytest.mark.integration
def test_coherent_location_substitution_still_requires_employee_contract(generated_world):
    save = deepcopy(generated_world)
    formations = [r for r in save['institution_growth']['formation_records']
                  if r['template_id'].startswith('generated_')]
    first, second = formations
    first['location_id'] = second['location_id']
    first['location_activation_id'] = second['location_activation_id']
    report = trace(save, type='institution', identity=first['id'], direction='upstream')
    assert 'activated_location' not in relations(report)
    assert report['unresolved']


def test_output_and_integer_budgets_are_explicit(monkeypatch, material_save):
    import src.analysis.inspection_save as reader
    monkeypatch.setattr(reader, 'MAX_REPORT_BYTES', 10)
    with pytest.raises(InspectionError, match='output limit'):
        trace(material_save, type='exchange', identity='exchange-00000001')
    with pytest.raises(InspectionError, match='integer'):
        load_save({'x': 2 ** 600})


def test_material_record_cannot_impersonate_transaction_namespace(material_save):
    transfer = material_save['materials']['inventory_transfers'][0]
    transfer['id'] = 'txn-00000001'
    material_save['materials']['exchanges'][0]['inventory_transfer_id'] = transfer['id']
    material_save['materials']['lot_movements'][0]['reference_id'] = transfer['id']
    report = trace(material_save, type='exchange', identity='exchange-00000001')
    assert report['edges'] == []
    assert report['unresolved'][0]['code'] == 'invalid_material_record_sequence'


def test_controlled_text_formatter_excludes_narrative(material_save):
    from src.analysis.inspection_presentation import format_trace
    material_save['economy']['ledger'][0]['reason'] = 'PRIVATE injection'
    output = format_trace(trace(material_save, type='exchange', identity='exchange-00000001'))
    assert 'Ledger payment settles exchange' in output
    assert 'PRIVATE' not in output


def test_repair_cannot_precede_terminal_parent_within_same_day(tmp_path):
    from tests.systems.test_plans import town, accepted_transfer
    engine = town(tmp_path)
    parent = accepted_transfer(engine)
    engine.commitment_system.transition(parent.id, 'failed', day=2, tick=12, reason='failure')
    child = engine.commitment_system.create(
        proposer_id=parent.proposer_id, counterpart_id=parent.counterpart_id,
        commitment_type='transfer', day=2, tick=8,
        repair_of_commitment_id=parent.id,
    )
    engine.state.save(engine, 2, 12)
    save = json.loads((tmp_path / 'state.json').read_text())
    assert 'repair_successor' not in relations(trace(save, type='commitment', identity=child.id))
