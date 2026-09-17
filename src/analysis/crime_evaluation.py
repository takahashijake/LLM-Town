"""Deterministic acceptance evaluation for theft, witnesses, and evidence."""

from __future__ import annotations

import json
from pathlib import Path

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.crime import CrimeError, CrimeSystem


def _build_engine(project_root: Path, work_dir: Path, *, load_state=False):
    return SimulationEngine(
        agents_path=project_root / "data/agents.json",
        locations_path=project_root / "data/locations.json",
        economy_path=project_root / "data/economy.json",
        materials_path=project_root / "data/materials.json",
        crime_path=project_root / "data/crime.json",
        load_state=load_state,
        llm_client=FakeLLMClient(),
        state_path=work_dir / "save_state.json",
        logs_dir=work_dir / ("resumed_logs" if load_state else "logs"),
    )


def _arrange(engine, *, lena_at_market=False):
    locations = {
        "agent_001": "library",
        "agent_002": "market",
        "agent_003": "market" if lena_at_market else "library",
        "agent_004": "market",
    }
    for agent in engine.agents:
        agent.location_id = locations[agent.id]


def _event_key(*requirements: tuple[str, bool]) -> str:
    for number in range(10_000):
        key = f"crime-evaluation-{number}"
        if all(
            CrimeSystem.witness_observes(key, witness_id) is expected
            for witness_id, expected in requirements
        ):
            return key
    raise RuntimeError("could not construct deterministic witness scenario")


def _quantities(engine):
    return {
        inventory_id: dict(inventory.quantities)
        for inventory_id, inventory in engine.materials.inventories.items()
    }


def _balances(engine):
    return {
        account_id: account.balance
        for account_id, account in engine.economy.accounts.items()
    }


def _attempt(engine, event_key, **overrides):
    values = {
        "actor_id": "agent_002",
        "source_inventory_id": "inventory:agent:agent_004",
        "good_id": "trade_materials",
        "quantity": 1,
        "day": 2,
        "hour": 12,
        "location_id": "market",
        "event_key": event_key,
        "agents": engine.agents,
    }
    values.update(overrides)
    return engine.crime.attempt_theft(**values)


def _authoritative_counts(engine):
    return {
        "balances": _balances(engine),
        "quantities": _quantities(engine),
        "ledger": len(engine.economy.ledger),
        "exchanges": len(engine.materials.exchanges),
        "transfers": len(engine.materials.inventory_transfers),
        "incidents": len(engine.crime.incidents),
        "opportunities": len(engine.crime.witness_opportunities),
        "evidence": len(engine.crime.evidence),
    }


def run_crime_evaluation(
    work_dir: str | Path,
    *,
    project_root: str | Path = ".",
) -> dict:
    project_root = Path(project_root).resolve()
    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    # Scenario A: Carlos is necessarily present with his property, but the
    # deterministic observation rule says he does not see Ethan take it.
    no_witness_engine = _build_engine(project_root, work_dir / "no_witness")
    _arrange(no_witness_engine)
    no_witness_key = _event_key(("agent_004", False))
    no_witness_incident = _attempt(no_witness_engine, no_witness_key)

    # Scenarios B/E/F share a world: Lena directly observes, later tells Maya,
    # and persistence must preserve both provenance levels without replay.
    witness_dir = work_dir / "witness"
    witness_engine = _build_engine(project_root, witness_dir)
    _arrange(witness_engine, lena_at_market=True)
    witness_key = _event_key(("agent_003", True), ("agent_004", False))
    currency_before = witness_engine.economy.total_currency()
    ledger_before = len(witness_engine.economy.ledger)
    exchange_before = len(witness_engine.materials.exchanges)
    source_before = witness_engine.materials.quantity(
        "inventory:agent:agent_004", "trade_materials"
    )
    destination_before = witness_engine.materials.quantity(
        "inventory:agent:agent_002", "trade_materials"
    )
    witness_incident = _attempt(witness_engine, witness_key)
    direct = next(
        record for record in witness_engine.crime.knowledge_for_agent("agent_003")
        if record.evidence_type == "eyewitness"
    )
    hearsay = witness_engine.crime.share_evidence(
        speaker_id="agent_003",
        listener_id="agent_001",
        evidence_id=direct.id,
        day=2,
        hour=18,
        event_key="evaluation:lena-tells-maya",
    )

    # Scenario C: stock rejection is atomic.
    failure_before = _authoritative_counts(witness_engine)
    failure_code = None
    try:
        _attempt(witness_engine, "evaluation:insufficient-stock", quantity=999)
    except CrimeError as error:
        failure_code = error.code
    failure_after = _authoritative_counts(witness_engine)

    # Scenario D: remote theft is rejected without changing material state.
    actor = next(agent for agent in witness_engine.agents if agent.id == "agent_002")
    actor.location_id = "library"
    location_failure_before = _authoritative_counts(witness_engine)
    location_failure_code = None
    try:
        _attempt(witness_engine, "evaluation:remote-theft")
    except CrimeError as error:
        location_failure_code = error.code
    location_failure_after = _authoritative_counts(witness_engine)
    actor.location_id = "market"

    crime_before_resume = witness_engine.crime.to_dict()
    materials_before_resume = witness_engine.materials.to_dict()
    economy_before_resume = witness_engine.economy.to_dict()
    witness_engine.state.save(witness_engine, 2, 18, day_complete=False)
    resumed = _build_engine(project_root, witness_dir, load_state=True)
    persistence_valid = (
        resumed.crime.to_dict() == crime_before_resume
        and resumed.materials.to_dict() == materials_before_resume
        and resumed.economy.to_dict() == economy_before_resume
    )
    replay_before = _authoritative_counts(resumed)
    replay_code = None
    try:
        _attempt(resumed, witness_key)
    except CrimeError as error:
        replay_code = error.code
    replay_after = _authoritative_counts(resumed)

    witness_diagnostics = resumed.crime.diagnostics()
    no_witness_diagnostics = no_witness_engine.crime.diagnostics()
    successful_transfer_valid = (
        source_before == 2
        and destination_before == 0
        and resumed.materials.quantity(
            "inventory:agent:agent_004", "trade_materials"
        ) == source_before - 1
        and resumed.materials.quantity(
            "inventory:agent:agent_002", "trade_materials"
        ) == destination_before + 1
        and resumed.economy.total_currency() == currency_before
        and len(resumed.economy.ledger) == ledger_before
        and len(resumed.materials.exchanges) == exchange_before
    )
    provenance_valid = (
        direct.provenance_type == "direct_observation"
        and direct.originating_observer_id == "agent_003"
        and direct.transmission_chain == ("agent_003",)
        and hearsay.provenance_type == "hearsay"
        and hearsay.source_evidence_id == direct.id
        and hearsay.originating_observer_id == "agent_003"
        and hearsay.transmission_chain == ("agent_003", "agent_001")
    )
    invariants = {
        "scenario_a_has_no_actual_witness": not no_witness_incident.eyewitness_ids,
        "scenario_b_has_valid_eyewitness": "agent_003" in witness_incident.eyewitness_ids,
        "successful_theft_moved_goods_only": successful_transfer_valid,
        "theft_has_no_legitimate_exchange": all(
            incident.unauthorized_transfer_id
            not in {item.inventory_transfer_id for item in engine.materials.exchanges}
            for engine in (no_witness_engine, resumed)
            for incident in engine.crime.incidents
        ),
        "insufficient_stock_was_atomic": (
            failure_code == "insufficient_stock" and failure_before == failure_after
        ),
        "location_mismatch_was_atomic": (
            location_failure_code == "actor_not_present"
            and location_failure_before == location_failure_after
        ),
        "evidence_provenance_valid": provenance_valid,
        "uninformed_agent_was_initially_uninformed": not any(
            item.holder_agent_id == "agent_001"
            and item.provenance_type != "hearsay"
            for item in witness_engine.crime.evidence
        ),
        "material_conserved": (
            no_witness_diagnostics["material_conserved"]
            and witness_diagnostics["material_conserved"]
        ),
        "currency_conserved": (
            no_witness_diagnostics["currency_conserved"]
            and witness_diagnostics["currency_conserved"]
        ),
        "incidents_reconcile_with_transfers": (
            no_witness_diagnostics["incidents_reconcile_with_materials"]
            and witness_diagnostics["incidents_reconcile_with_materials"]
        ),
        "evidence_records_are_valid": (
            no_witness_diagnostics["evidence_valid"]
            and witness_diagnostics["evidence_valid"]
        ),
        "persistence_preserved": persistence_valid,
        "resume_replay_was_blocked": (
            replay_code == "duplicate_event" and replay_before == replay_after
        ),
    }
    return {
        "passed": all(invariants.values()),
        "invariants": invariants,
        "counts": {
            "incidents_created": (
                no_witness_diagnostics["incident_count"]
                + witness_diagnostics["incident_count"]
            ),
            "unauthorized_transfers": (
                no_witness_diagnostics["unauthorized_transfer_count"]
                + witness_diagnostics["unauthorized_transfer_count"]
            ),
            "stolen_value": (
                no_witness_diagnostics["total_stolen_value"]
                + witness_diagnostics["total_stolen_value"]
            ),
            "actual_witnesses": (
                no_witness_diagnostics["actual_witness_count"]
                + witness_diagnostics["actual_witness_count"]
            ),
            "direct_evidence": (
                no_witness_diagnostics["direct_evidence_count"]
                + witness_diagnostics["direct_evidence_count"]
            ),
            "hearsay_records": witness_diagnostics["hearsay_evidence_count"],
            "rejected_attempts": witness_diagnostics["rejected_attempt_count"],
            "rejections_by_code": witness_diagnostics["rejections_by_code"],
        },
        "successful_theft": {
            "incident_id": witness_incident.id,
            "transfer_id": witness_incident.unauthorized_transfer_id,
            "actor_id": witness_incident.actor_id,
            "victim_id": witness_incident.victim_id,
            "good_id": witness_incident.good_id,
            "quantity": witness_incident.quantity,
            "location_id": witness_incident.location_id,
            "eyewitness_ids": list(witness_incident.eyewitness_ids),
            "money_changed": False,
            "legitimate_exchange_created": False,
        },
        "failed_attempts": {
            "insufficient_stock": failure_code,
            "location_mismatch": location_failure_code,
            "resume_replay": replay_code,
        },
    }


def write_crime_evaluation(document: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
