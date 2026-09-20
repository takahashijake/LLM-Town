import copy
from dataclasses import replace

import pytest

from src.agents.agent import Agent
from src.systems.economy import EconomicAccount, EconomySystem, Employment
from src.systems.materials import (
    GoodDefinition, Inventory, MaterialError, MaterialSystem, ProductionRecipe, Seller,
)


def build_system(raw=6, meals=0):
    economy = EconomySystem(
        accounts=[EconomicAccount("worker", "agent", "merchant", 100),
                  EconomicAccount("shop-account", "employer", "shop", 100)],
        employments=[Employment("merchant-job", "merchant", "merchant", "shop-account", 10,
                                ("restock",))],
    )
    recipe = ProductionRecipe("meal-recipe", (("raw", 2),), (("meal", 3),), "shop",
                              "restock", "market", ("merchant",), ("merchant-job",),
                              "meal", 5)
    system = MaterialSystem(
        economy=economy,
        goods=[GoodDefinition("raw", "ingredients", "input", 2),
               GoodDefinition("meal", "meal", "food", 8, True, "social", 2)],
        inventories=[Inventory("worker-inventory", "agent", "merchant", "worker"),
                     Inventory("shop", "business", "seller", "shop-account",
                               (("raw", raw), ("meal", meals)))],
        sellers=[Seller("seller", "shop", "shop-account", "market", "merchant-job")],
        production_recipes=[recipe],
    )
    return economy, system


def produce(system, event="production:event", **overrides):
    values = dict(recipe_id="meal-recipe", actor_id="merchant",
                  employment_id="merchant-job", inventory_id="shop", day=1, hour=8,
                  activity_id="restock", location_id="market", event_key=event)
    values.update(overrides)
    return system.produce(**values)


def test_recipe_validation_rejects_zero_inputs_unknown_goods_and_bad_quantities():
    economy, _ = build_system()
    base = dict(economy=economy,
                goods=[GoodDefinition("raw", "raw", "input", 1)],
                inventories=[Inventory("shop", "business", "seller", "shop-account")],
                sellers=[Seller("seller", "shop", "shop-account", "market", "merchant-job")])
    with pytest.raises(ValueError, match="requires material inputs"):
        MaterialSystem(**base, production_recipes=[ProductionRecipe("r", (), (("raw", 1),), "shop", "work")])
    with pytest.raises(ValueError, match="unknown good"):
        MaterialSystem(**base, production_recipes=[ProductionRecipe("r", (("missing", 1),), (("raw", 1),), "shop", "work")])
    with pytest.raises(ValueError, match="positive integer"):
        MaterialSystem(**base, production_recipes=[ProductionRecipe("r", (("raw", 0),), (("raw", 1),), "shop", "work")])


def test_production_is_atomic_idempotent_accounted_and_has_lineage():
    economy, system = build_system()
    currency = economy.total_currency()
    record = produce(system)
    assert system.quantity("shop", "raw") == 4
    assert system.quantity("shop", "meal") == 3
    assert record.input_lot_ids == ("lot:initial:shop:raw",)
    output = system.lots[record.output_lot_ids[0]]
    assert output.parent_lot_ids == record.input_lot_ids
    assert output.production_id == record.id
    assert economy.total_currency() == currency
    assert system.material_conservation_holds()
    assert system.material_history_reconstructs_inventories()
    assert system.provenance_reconciles()
    before = copy.deepcopy(system.to_dict())
    with pytest.raises(MaterialError, match="already applied"):
        produce(system)
    after = system.to_dict()
    assert {k: v for k, v in after.items() if k != "rejected_operations"} == {
        k: v for k, v in before.items() if k != "rejected_operations"
    }


def test_failed_production_and_target_guard_make_no_material_mutation():
    _, insufficient = build_system(raw=1)
    before = insufficient.to_dict()
    with pytest.raises(MaterialError) as error:
        produce(insufficient)
    assert error.value.code == "insufficient_inputs"
    assert insufficient._quantity_snapshot() == {
        key: dict(value.quantities) for key, value in insufficient.inventories.items()
    }
    assert insufficient.production_records == []
    assert insufficient.lot_movements == []
    _, stocked = build_system(meals=5)
    with pytest.raises(MaterialError) as error:
        produce(stocked)
    assert error.value.code == "target_stock_met"


def test_target_stock_is_pre_batch_threshold_not_hard_cap():
    _, system = build_system(meals=4)
    produce(system)
    assert system.quantity("shop", "meal") == 7


def test_production_and_lot_event_validators_detect_broken_references():
    _, system = build_system()
    record = produce(system)
    assert system.production_records_are_valid()
    assert system.lot_movements_reconcile_with_events()
    system.lot_movements[0] = replace(
        system.lot_movements[0], reference_id="missing-production"
    )
    assert not system.lot_movements_reconcile_with_events()
    system.production_records[0] = replace(record, actor_id="unauthorized")
    assert not system.production_records_are_valid()


def test_oldest_lot_transfer_splits_and_consumption_preserves_history_round_trip():
    _, system = build_system(raw=6)
    first = produce(system, "p1")
    # Move initial output away so a second batch is permitted, then produce it.
    system.transfer_good("shop", "worker-inventory", "meal", 3, day=1, hour=9,
                         reason="first batch", authorization_type="test",
                         authorization_id="a", event_key="move:first")
    second = produce(system, "p2", day=2)
    system.transfer_good("shop", "worker-inventory", "meal", 2, day=2, hour=9,
                         reason="second batch", authorization_type="test",
                         authorization_id="b", event_key="move:second")
    held = system.lot_holdings["worker-inventory"]
    assert held[first.output_lot_ids[0]] == 3
    assert held[second.output_lot_ids[0]] == 2
    agent = Agent("merchant", "Merchant", "careful", "market",
                  needs={"social": 50, "wealth": 50, "knowledge": 50})
    system.consume(agent, "worker-inventory", "meal", 4, day=3, hour=8,
                   activity_id="eat", event_key="eat")
    assert first.output_lot_ids[0] not in system.lot_holdings["worker-inventory"]
    assert system.lot_holdings["worker-inventory"][second.output_lot_ids[0]] == 1
    assert any(m.movement_type == "consumption" and m.lot_id == first.output_lot_ids[0]
               for m in system.lot_movements)
    restored = MaterialSystem.from_dict(system.to_dict(), economy=system.economy)
    assert restored.to_dict() == system.to_dict()


def test_preferred_lot_supports_exact_stolen_batch_restitution():
    _, system = build_system()
    batch = produce(system)
    theft = system.transfer_good("shop", "worker-inventory", "meal", 2, day=1, hour=9,
                                 reason="theft", authorization_type="unauthorized_theft",
                                 authorization_id="crime-1", event_key="theft")
    stolen = system.lot_ids_moved_by_transfer(theft.id)
    returned = system.transfer_good("worker-inventory", "shop", "meal", 1, day=2, hour=8,
                                    reason="restitution", authorization_type="justice_restitution",
                                    authorization_id="adj-1", event_key="return",
                                    preferred_lot_ids=stolen)
    assert system.lot_ids_moved_by_transfer(returned.id) == (batch.output_lot_ids[0],)
    assert system.provenance_reconciles()


def test_schema_v1_state_migrates_current_holdings_deterministically():
    _, system = build_system()
    system.transfer_good("shop", "worker-inventory", "raw", 1, day=1, hour=8,
                         reason="legacy movement", authorization_type="test",
                         authorization_id="legacy", event_key="legacy:move")
    legacy = system.to_dict()
    legacy["schema_version"] = 1
    for key in ("production_recipes", "production_records", "lots", "lot_holdings",
                "lot_movements", "next_production_number", "next_lot_number",
                "next_movement_number"):
        legacy.pop(key, None)
    first = MaterialSystem.from_dict(copy.deepcopy(legacy), economy=system.economy)
    second = MaterialSystem.from_dict(copy.deepcopy(legacy), economy=system.economy)
    assert first.to_dict() == second.to_dict()
    assert first.provenance_reconciles()
    assert all(lot.origin_type == "schema_v1_migration" for lot in first.lots.values())
