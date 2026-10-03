"""Focused Phase 5 commerce authority and runtime registration tests."""

from copy import deepcopy

import pytest

from src.behavior.activity import Activity
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.event_ecology import DynamicEventOccurrenceRecord
from src.systems.materials import MaterialError, MaterialSystem, Seller


def _engine(tmp_path):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", llm_client=FakeLLMClient(),
        state_path=tmp_path / "save.json", logs_dir=tmp_path / "logs",
        simulation_seed=11,
    )


def _activity(engine, *, days, agents, location, activity_id="ordinary_use"):
    for day in days:
        for agent in agents:
            engine.activity_records.append({
                "type": "activity", "day": day, "hour": 8,
                "agent_id": agent.id, "agent": agent.name,
                "location": location, "activity_id": activity_id,
            })


def _ready_engine(tmp_path):
    engine = _engine(tmp_path)
    _activity(engine, days=range(8, 15), agents=engine.agents,
              location="town_square")
    assert engine.review_town_growth(14).status == "activated"
    _activity(engine, days=range(22, 29), agents=engine.agents,
              location="town_square")
    assert engine.review_location_growth(28).status == "activated"
    _activity(engine, days=range(33, 40), agents=engine.agents[:3],
              location="community_garden")
    _activity(engine, days=range(49, 71), agents=engine.agents[2:],
              location="community_garden")
    occurrences = [
        DynamicEventOccurrenceRecord(
            f"daily-event:{day}:garden_learning_circle:community_garden",
            "garden_learning_circle", "community_garden", day,
        ) for day in (40, 56)
    ]
    engine.event_ecology.occurrence_history.extend(occurrences)
    engine.event_ecology.processed_occurrence_ids.update(
        item.occurrence_id for item in occurrences
    )
    assert engine.review_institution_growth(70).status == "activated"
    formation = engine.institution_growth.formation_records[0]
    employee = next(item for item in engine.agents
                    if item.id == formation.employee_agent_id)
    role = engine.institution_growth.template(formation.template_id).role
    for day in range(71, 84):
        work = Activity(
            role.work_activity_id, role.work_activity_name,
            formation.location_id, "authoritative test work", ["work"],
        )
        engine.economy.process_activity(employee, work, day=day, hour=8)
    _activity(engine, days=range(71, 84), agents=engine.agents[:3],
              location="community_garden")
    for offset, buyer in enumerate(engine.agents[:2]):
        inventory = engine.materials.inventory_for_agent(buyer.id)
        account = engine.economy.account_for_agent(buyer.id)
        engine.materials.purchase(
            inventory.id, account.id, "seller:market_stall", "prepared_meal", 1,
            day=80 + offset, hour=8, event_key=f"test-demand:{buyer.id}",
        )
    return engine


def _propose(engine):
    review = engine.commerce_growth.review(
        day=84, agents=engine.agents, locations=engine.locations,
        institution_growth=engine.institution_growth,
        location_growth=engine.location_growth, economy=engine.economy,
        materials=engine.materials, activity_records=engine.activity_records,
    )
    assert review.status == "proposed"
    return engine.commerce_growth.pending_activation()


def test_readiness_and_activation_register_exact_empty_authority(tmp_path):
    engine = _ready_engine(tmp_path)
    totals = engine.materials.total_quantities()
    review = engine.review_commerce_growth(84)
    record = engine.commerce_growth.activation_records[0]

    assert review.status == "activated"
    assert record.id == "commerce-activation:0001"
    assert record.institution_formation_id == "institution-formation:0001"
    inventory = engine.materials.get_inventory(record.inventory_id)
    assert inventory.owner_type == "institution"
    assert inventory.quantities == ()
    assert engine.materials.initial_quantities[record.inventory_id] == {}
    assert engine.materials.total_quantities() == totals
    assert engine.materials.sellers[record.seller_id].location_id == "community_garden"
    assert engine.materials.purchase_activity_rules[
        "buy_garden_meal"
    ].seller_id == record.seller_id
    recipe = engine.materials.production_recipes[record.recipe_id]
    assert recipe.eligible_actor_ids == (record.operator_agent_id,)
    assert recipe.eligible_employment_ids == (record.operator_employment_id,)
    assert len(engine.materials.goods) == 5
    engine.validate_commerce_authorities()


def test_registration_rejects_malformed_references_and_text_has_no_authority(tmp_path):
    engine = _ready_engine(tmp_path)
    record = _propose(engine)
    materials = MaterialSystem.from_dict(
        deepcopy(engine.materials.to_dict()), economy=engine.economy,
    )
    with pytest.raises(MaterialError, match="inventory"):
        materials.register_institution_inventory(
            inventory_id=record.inventory_id,
            institution_id="Community Garden Stewardship",
            account_id=record.institution_account_id,
            commerce_activation_id=record.id,
        )
    materials.register_institution_inventory(
        inventory_id=record.inventory_id, institution_id=record.institution_id,
        account_id=record.institution_account_id,
        commerce_activation_id=record.id,
    )
    forged = Seller(
        record.seller_id, record.inventory_id, record.institution_account_id,
        "market", "community garden steward", True,
        record.institution_id, record.id,
    )
    with pytest.raises(MaterialError, match="seller"):
        materials.register_seller(
            forged, location_ids={item.id for item in engine.locations},
        )


def test_procurement_moves_existing_lots_then_exact_operator_produces(tmp_path):
    engine = _ready_engine(tmp_path)
    engine.review_commerce_growth(84)
    record = engine.commerce_growth.activation_records[0]
    employee = next(item for item in engine.agents
                    if item.id == record.operator_agent_id)
    activity = Activity(
        "steward_community_garden", "Steward", "community_garden",
        "registered operation", ["work", "production"],
    )
    source_before = engine.materials.quantity(
        "inventory:business:market_stall", "meal_ingredients"
    )
    first = engine.materials.process_activity(employee, activity, day=85, hour=8)
    assert first.seller_id == "seller:market_stall"
    assert engine.materials.initial_quantities[record.inventory_id] == {}
    assert engine.materials.quantity(record.inventory_id, "meal_ingredients") == 2
    assert engine.materials.quantity(
        "inventory:business:market_stall", "meal_ingredients"
    ) == source_before - 2
    moved_lots = engine.materials.lot_ids_moved_by_transfer(first.inventory_transfer_id)
    assert moved_lots
    second = engine.materials.process_activity(employee, activity, day=86, hour=8)
    assert second.recipe_id == record.recipe_id
    assert second.input_lot_ids == moved_lots
    assert engine.materials.quantity(record.inventory_id, "prepared_meal") == 4
    assert engine.materials.provenance_reconciles()

    wrong = engine.agents[0]
    assert engine.materials.process_activity(wrong, activity, day=87, hour=8) is None
    wrong_place = Activity(
        activity.id, activity.name, "market", activity.reason, activity.tags,
    )
    assert engine.materials.process_activity(
        employee, wrong_place, day=87, hour=8
    ) is None


def test_activation_rollback_removes_every_partial_registry(tmp_path, monkeypatch):
    engine = _ready_engine(tmp_path)
    record = _propose(engine)
    before = deepcopy(engine.materials.to_dict())

    def fail(_recipe):
        raise RuntimeError("injected recipe failure")

    monkeypatch.setattr(engine.materials, "register_production_recipe", fail)
    assert engine.activate_pending_commerce(84) is None
    assert engine.materials.to_dict() == before
    assert engine.commerce_growth.activation_records[0].status == "rejected"
    assert record.inventory_id not in engine.materials.inventories
    assert record.seller_id not in engine.materials.sellers
    assert "buy_garden_meal" not in engine.materials.purchase_activity_rules
    assert record.recipe_id not in engine.materials.production_recipes
    assert engine.crime.materials is engine.materials
    assert engine.justice.materials is engine.materials
    assert engine.commitment_system.materials is engine.materials
    assert engine.plan_system.materials is engine.materials


def test_resident_purchase_is_atomic_location_bound_and_replay_safe(tmp_path):
    engine = _ready_engine(tmp_path)
    engine.review_commerce_growth(84)
    record = engine.commerce_growth.activation_records[0]
    employee = next(item for item in engine.agents
                    if item.id == record.operator_agent_id)
    operation = Activity(
        "steward_community_garden", "Steward", "community_garden",
        "registered operation", ["work", "production"],
    )
    engine.materials.process_activity(employee, operation, day=85, hour=8)
    engine.materials.process_activity(employee, operation, day=86, hour=8)
    buyer = engine.agents[0]
    buyer_inventory = engine.materials.inventory_for_agent(buyer.id)
    institution_before = engine.economy.get_account(
        record.institution_account_id
    ).balance
    buyer_before = engine.economy.account_for_agent(buyer.id).balance
    wrong = Activity(
        "buy_garden_meal", "Buy", "market", "wrong place", ["purchase"],
    )
    assert engine.materials.process_activity(buyer, wrong, day=87, hour=8) is None
    purchase = Activity(
        "buy_garden_meal", "Buy", "community_garden", "real route", ["purchase"],
    )
    exchange = engine.materials.process_activity(buyer, purchase, day=87, hour=8)
    assert exchange.seller_id == record.seller_id
    assert engine.materials.quantity(buyer_inventory.id, "prepared_meal") >= 1
    assert engine.economy.get_account(record.institution_account_id).balance == (
        institution_before + 8
    )
    assert engine.economy.account_for_agent(buyer.id).balance == buyer_before - 8
    ledger_size = len(engine.economy.ledger)
    stock = engine.materials.quantity(buyer_inventory.id, "prepared_meal")
    assert engine.materials.process_activity(buyer, purchase, day=87, hour=12) is None
    assert len(engine.economy.ledger) == ledger_size
    assert engine.materials.quantity(buyer_inventory.id, "prepared_meal") == stock
    with pytest.raises(MaterialError, match="registered route"):
        engine.materials.purchase(
            buyer_inventory.id, engine.economy.account_for_agent(buyer.id).id,
            record.seller_id, "meal_ingredients", 1, day=88, hour=8,
            event_key="forged:dynamic-input-sale",
        )


def test_save_resume_reconstructs_once_and_orphans_fail_closed(tmp_path):
    import json

    engine = _ready_engine(tmp_path)
    engine.review_commerce_growth(84)
    engine.state.save(engine, 84, 8, day_complete=True)
    resumed = SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=True,
        llm_client=FakeLLMClient(), state_path=tmp_path / "save.json",
        logs_dir=tmp_path / "reload-logs", simulation_seed=11,
    )
    resumed.validate_commerce_authorities()
    assert len(resumed.commerce_growth.activation_records) == 1
    assert len([item for item in resumed.materials.inventories.values()
                if item.commerce_activation_id]) == 1
    assert resumed.materials.initial_quantities["inventory:institution:0001"] == {}

    state = json.loads((tmp_path / "save.json").read_text())
    dynamic = next(item for item in state["materials"]["sellers"]
                   if item.get("commerce_activation_id"))
    dynamic["inventory_id"] = "inventory:business:market_stall"
    (tmp_path / "save.json").write_text(json.dumps(state))
    with pytest.raises(ValueError):
        SimulationEngine(
            "data/agents.json", "data/locations.json", load_state=True,
            llm_client=FakeLLMClient(), state_path=tmp_path / "save.json",
            logs_dir=tmp_path / "forged-logs", simulation_seed=11,
        )


def test_unknown_schema_and_serialized_ready_claim_fail_closed():
    from src.systems.commerce_growth import CommerceGrowthSystem

    system = CommerceGrowthSystem.from_config("data/town_growth.json")
    state = system.to_dict()
    state["schema_version"] = 999
    with pytest.raises(ValueError, match="schema"):
        CommerceGrowthSystem.from_config("data/town_growth.json", state)
    state = system.to_dict()
    state["ready"] = True
    with pytest.raises(ValueError, match="schema"):
        CommerceGrowthSystem.from_config("data/town_growth.json", state)
