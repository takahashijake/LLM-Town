import pytest

from src.analysis.growth_audits import conservation_checks
from src.behavior.activity import Activity
from src.systems.economy import EconomySystem
from src.systems.materials import MaterialSystem
from tests.systems.test_commerce_growth import _ready_engine
from tests.systems.test_materials import build_materials, purchase


def test_procurement_production_and_sale_in_same_tick_replay_in_commit_order(tmp_path):
    engine = _ready_engine(tmp_path)
    engine.review_commerce_growth(84)
    record = engine.commerce_growth.activation_records[0]
    operator = next(agent for agent in engine.agents if agent.id == record.operator_agent_id)
    activity = Activity('steward_community_garden', 'Steward', record.location_id,
                        'registered operation', ['work', 'production'])
    first = engine.materials.process_activity(operator, activity, day=85, hour=8)
    second = engine.materials.process_activity(operator, activity, day=85, hour=8)
    assert first.good_id == 'meal_ingredients'
    assert second.recipe_id == record.recipe_id
    buyer = engine.agents[0]
    engine.materials.purchase(engine.materials.inventory_for_agent(buyer.id).id,
                              engine.economy.account_for_agent(buyer.id).id,
                              record.seller_id, 'prepared_meal', 1,
                              day=85, hour=8, event_key='same-tick-sale')
    assert all(conservation_checks(engine).values())
    restored = MaterialSystem.from_dict(engine.materials.to_dict(), economy=engine.economy)
    assert restored.to_dict() == engine.materials.to_dict()


@pytest.mark.parametrize('field', ['next_transfer_number', 'next_exchange_number',
                                  'next_consumption_number', 'next_production_number',
                                  'next_lot_number', 'next_movement_number'])
@pytest.mark.parametrize('mutation', ['rollback', 'jump', 'boolean', 'float'])
def test_material_counters_cannot_change_persisted_commit_sequences(field, mutation):
    economy, materials = build_materials()
    purchase(materials)
    state = materials.to_dict()
    value = state[field]
    if mutation == 'rollback' and value == 1:
        state[field] = 0
    else:
        state[field] = {'rollback': 1, 'jump': value + 20,
                        'boolean': True, 'float': float(value)}[mutation]
    with pytest.raises(ValueError):
        MaterialSystem.from_dict(state, economy=economy)


@pytest.mark.parametrize('mutation', ['rollback', 'jump', 'boolean', 'float'])
def test_ledger_counter_cannot_change_persisted_commit_sequence(mutation):
    economy, materials = build_materials()
    purchase(materials)
    state = economy.to_dict()
    value = state['next_transaction_number']
    state['next_transaction_number'] = {'rollback': 1, 'jump': value + 20,
                                         'boolean': True, 'float': float(value)}[mutation]
    with pytest.raises(ValueError):
        EconomySystem.from_dict(state)
