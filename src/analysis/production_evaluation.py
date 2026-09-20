"""Deterministic acceptance evaluation for production and material provenance."""

from __future__ import annotations

import json
from pathlib import Path

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.materials import MaterialError


def run_production_evaluation(output_dir: str | Path = "outputs") -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "production_evaluation_state.json"
    def build(load_state=False):
        return SimulationEngine(
            agents_path="data/agents.json", locations_path="data/locations.json",
            llm_client=FakeLLMClient(), state_path=state_path,
            logs_dir=output_dir / "production_evaluation_logs", load_state=load_state,
        )
    engine = build()
    materials, economy = engine.materials, engine.economy
    market = "inventory:business:market_stall"
    currency_before = economy.total_currency()

    # A/B: target guard is atomic, then legitimate purchases deplete stock.
    before_failed = materials.to_dict()
    failure_code = None
    try:
        materials.produce(
            "recipe:market_prepared_meals", actor_id="agent_004",
            employment_id="employment:agent_004:merchant", inventory_id=market,
            day=1, hour=8, activity_id="restock_market", location_id="market",
            event_key="evaluation:production:blocked",
        )
    except MaterialError as error:
        failure_code = error.code
    failed_atomic = (
        materials._quantity_snapshot() == {
            item["id"]: item["quantities"] for item in before_failed["inventories"]
        }
        and not materials.production_records and not materials.lot_movements
    )

    for agent in engine.agents:
        inventory = materials.inventory_for_agent(agent.id)
        account = economy.account_for_agent(agent.id)
        for index in range(6):
            materials.purchase(inventory.id, account.id, "seller:market_stall",
                               "prepared_meal", 1, day=1, hour=9,
                               event_key=f"evaluation:deplete:{agent.id}:{index}")
    depleted = materials.quantity(market, "prepared_meal") == 0

    # Clear one buyer's older fungible holdings so the lifecycle trace below
    # unambiguously follows the newly produced batch.
    victim = engine.agents[0]
    victim_inventory = materials.inventory_for_agent(victim.id)
    materials.consume(victim, victim_inventory.id, "prepared_meal", 6,
                      day=1, hour=10, activity_id="eat_meal",
                      event_key="evaluation:consume-initial")

    # A/C: recorded transformation replenishes the empty market.
    production = materials.produce(
        "recipe:market_prepared_meals", actor_id="agent_004",
        employment_id="employment:agent_004:merchant", inventory_id=market,
        day=2, hour=8, activity_id="restock_market", location_id="market",
        event_key="evaluation:production:success",
    )
    output_lot = production.output_lot_ids[0]
    produced = materials.quantity(market, "prepared_meal") == 4

    # D/E: purchase -> theft -> exact-lot restitution -> consumption.
    thief = engine.agents[1]
    thief_inventory = materials.inventory_for_agent(thief.id)
    exchange = materials.purchase(
        victim_inventory.id, economy.account_for_agent(victim.id).id,
        "seller:market_stall", "prepared_meal", 1, day=2, hour=9,
        event_key="evaluation:buy-produced",
    )
    victim.location_id = thief.location_id = "market"
    incident = engine.crime.attempt_theft(
        actor_id=thief.id, source_inventory_id=victim_inventory.id,
        good_id="prepared_meal", quantity=1, day=2, hour=10,
        location_id="market", event_key="evaluation:theft", agents=engine.agents,
    )
    theft_id = incident.unauthorized_transfer_id
    stolen_lots = materials.lot_ids_moved_by_transfer(theft_id)
    restitution = materials.transfer_good(
        thief_inventory.id, victim_inventory.id, "prepared_meal", 1,
        day=2, hour=11, reason="Evaluation restitution",
        authorization_type="justice_restitution", authorization_id="evaluation-adjudication",
        event_key="evaluation:restitution", preferred_lot_ids=stolen_lots,
    )
    consumption = materials.consume(
        victim, victim_inventory.id, "prepared_meal", 1, day=2, hour=12,
        activity_id="eat_meal", event_key="evaluation:consume",
    )
    lineage_ok = (
        output_lot in materials.lot_ids_moved_by_transfer(exchange.inventory_transfer_id)
        and stolen_lots == (output_lot,)
        and materials.lot_ids_moved_by_transfer(restitution.id) == (output_lot,)
        and any(m.lot_id == output_lot and m.reference_id == consumption.id
                for m in materials.lot_movements)
    )

    # F: exact state survives resume and the production guard survives with it.
    engine.state.save(engine, 2, 12)
    saved_materials = materials.to_dict()
    resumed = build(load_state=True)
    exact_resume = resumed.materials.to_dict() == saved_materials
    replay_code = None
    try:
        resumed.materials.produce(
            "recipe:market_prepared_meals", actor_id="agent_004",
            employment_id="employment:agent_004:merchant", inventory_id=market,
            day=2, hour=8, activity_id="restock_market", location_id="market",
            event_key="evaluation:production:success",
        )
    except MaterialError as error:
        replay_code = error.code
    diagnostics = resumed.materials.diagnostics()
    checks = {
        "failed_production_atomic": failed_atomic and failure_code == "target_stock_met",
        "depletion_then_recorded_restock": depleted and produced,
        "production_record_and_lineage": len(production.output_lot_ids) == 1 and lineage_ok,
        "currency_only_changed_by_purchases": economy.total_currency() == currency_before,
        "accounting_holds": diagnostics["material_conserved_with_consumption"],
        "history_reconstructs": diagnostics["history_reconstructs_inventories"],
        "provenance_reconciles": diagnostics["provenance_reconciles"],
        "exact_save_resume": exact_resume,
        "production_replay_rejected": replay_code == "duplicate_event"
                                      and len(resumed.materials.production_records) == 1,
    }
    result = {
        "passed": all(checks.values()), "checks": checks,
        "failure_code": failure_code, "replay_code": replay_code,
        "production_id": production.id, "output_lot_id": output_lot,
        "diagnostics": diagnostics,
    }
    (output_dir / "production_evaluation.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    return result
