"""Deterministic V5 Phase 4 institution and employment acceptance gate."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory

from src.behavior.activity import Activity
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def _engine(root: Path, name: str, *, load: bool = False) -> SimulationEngine:
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs", simulation_seed=11,
    )


def _run(engine: SimulationEngine, days: int) -> None:
    with redirect_stdout(StringIO()):
        engine.run(days, [8])


def _long_horizon(root: Path, name: str) -> tuple[SimulationEngine, dict]:
    state = random.getstate()
    random.seed(11)
    try:
        engine = _engine(root, name)
        _run(engine, 60)
        engine = _engine(root, name, load=True)
        _run(engine, 20)
        engine = _engine(root, name, load=True)
        _run(engine, 160)
    finally:
        random.setstate(state)
    formations = [item for item in engine.institution_growth.formation_records
                  if item.status == "activated"]
    employment_ids = {item.employment_id for item in formations}
    work = [item for item in engine.economy.work_events
            if item.get("employment_id") in employment_ids]
    wages = [item for item in engine.economy.ledger
             if item.transaction_type == "wage"
             and dict(item.metadata).get("employment_id") in employment_ids]
    institution_memories = sorted(
        memory.id for agent in engine.agents
        for memory in agent.memory + agent.memory_archive
        if memory.source_system == "institution_growth"
    )
    occurrence_days = {item.day for item in engine.event_ecology.occurrence_history}
    dynamic_conversations = [
        memory.id for agent in engine.agents
        for memory in agent.memory + agent.memory_archive
        if memory.type == "conversation"
        and memory.location == "community_garden"
        and memory.day in occurrence_days
    ]
    signature = {
        "resident_ids": [item.id for item in engine.agents],
        "migration_ids": [item.id for item in engine.town_growth.migration_records],
        "active_location_ids": [item.id for item in engine.locations],
        "location_activation_ids": [item.id for item in engine.location_growth.activation_records],
        "dynamic_event_occurrence_ids": [item.occurrence_id
                                         for item in engine.event_ecology.occurrence_history],
        "institution_ids": [item.institution_id for item in formations],
        "formation_ids": [item.id for item in formations],
        "institution_template_ids": [item.template_id for item in formations],
        "employer_account_ids": [item.employer_account_id for item in formations],
        "employee_ids": [item.employee_agent_id for item in formations],
        "employment_ids": [item.employment_id for item in formations],
        "role_template_ids": [item.role_template_id for item in formations],
        "employment_start_days": [engine.economy.employments[item.employment_id].start_day
                                  for item in formations],
        "startup_event_keys": [item.event_key for item in engine.economy.ledger
                               if item.transaction_type == "institution_startup"],
        "startup_transaction_ids": [item.id for item in engine.economy.ledger
                                    if item.transaction_type == "institution_startup"],
        "balances": sorted((key, value.balance)
                           for key, value in engine.economy.accounts.items()),
        "dynamic_work_event_ids": [item["id"] for item in work],
        "dynamic_wage_transaction_ids": [item.id for item in wages],
        "institution_memory_ids": institution_memories,
        "dynamic_event_conversation_count": len(dynamic_conversations),
        "total_currency": engine.economy.total_currency(),
        "review_history_size": len(engine.institution_growth.review_history),
        "formation_history_size": len(engine.institution_growth.formation_records),
    }
    return engine, signature


def _mutated_load_rejected(root: Path, saved: dict, name: str, mutate) -> bool:
    data = deepcopy(saved)
    mutate(data)
    (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    try:
        _engine(root, name, load=True)
    except (KeyError, TypeError, ValueError):
        return True
    return False


def evaluate_institution_growth() -> dict:
    scenarios: dict[str, bool] = {}
    invariants: dict[str, bool] = {}
    diagnostics: dict[str, object] = {}
    caller_state = random.getstate()
    try:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first, signature = _long_horizon(root, "long-a")
            second, repeat = _long_horizon(root, "long-b")
            diagnostics["long_horizon_signature"] = signature
            formation = first.institution_growth.formation_records[0]
            template = first.institution_growth.template(formation.template_id)
            employment = first.economy.employments[formation.employment_id]
            startup = next(item for item in first.economy.ledger
                           if item.id == formation.startup_transaction_id)
            wages = [item for item in first.economy.ledger
                     if item.transaction_type == "wage"
                     and dict(item.metadata).get("employment_id") == employment.id]
            work = [item for item in first.economy.work_events
                    if item.get("employment_id") == employment.id]
            public_memories = [memory for agent in first.agents
                               for memory in agent.memory + agent.memory_archive
                               if memory.source_id == formation.id
                               and memory.event_type == "institution_established"]
            private_memories = [memory for agent in first.agents
                                for memory in agent.memory + agent.memory_archive
                                if memory.source_id == formation.id
                                and memory.event_type == "employment_started"]
            scenarios.update({
                "integrated_migration_exactly_once": signature["migration_ids"]
                == ["migration:0001"],
                "integrated_location_activation_exactly_once":
                signature["location_activation_ids"] == ["location-activation:0001"],
                "dynamic_events_precede_formation": bool(
                    first.event_ecology.occurrence_history
                    and max(item.day for item in first.event_ecology.occurrence_history
                            if item.day < formation.review_day) < formation.review_day
                ),
                "one_configured_institution_forms": signature["formation_ids"]
                == ["institution-formation:0001"],
                "evidence_selects_unemployed_migrant": formation.employee_agent_id
                == "agent_005",
                "employment_starts_following_day": employment.start_day
                == formation.activation_day + 1,
                "zero_baseline_employer_account": first.economy.initial_balances[
                    formation.employer_account_id
                ] == 0,
                "startup_uses_conserved_transfer": (
                    startup.source_account_id
                    == template.startup_funding_source_account_id
                    and startup.destination_account_id == formation.employer_account_id
                    and startup.amount == template.startup_grant
                    and startup.event_key == f"institution-startup:{formation.id}"
                ),
                "ordinary_dynamic_work_occurs": bool(work),
                "ordinary_dynamic_wages_are_paid": bool(wages),
                "dynamic_event_conversations_remain_ordinary": bool(
                    signature["dynamic_event_conversation_count"]
                ),
                "work_uses_exact_role_and_location": all(
                    item["activity_id"] == template.role.work_activity_id
                    and item["location_id"] == formation.location_id for item in work
                ),
                "public_memory_created_once_per_resident": len(public_memories)
                == len(first.agents),
                "private_employment_memory_created_once": len(private_memories) == 1
                and private_memories[0].owner_id == formation.employee_agent_id,
                "seeded_save_resume_runs_match": signature == repeat,
                "finite_capacity_settles": len(first.institution_growth.formation_records) == 1,
                "institution_creates_no_seller_or_business_inventory": (
                    formation.institution_id not in {
                        item.owner_id for item in first.materials.inventories.values()
                    }
                    and formation.institution_id not in {
                        item.id for item in first.materials.sellers.values()
                    }
                ),
            })

            employee = next(item for item in first.agents
                            if item.id == formation.employee_agent_id)
            before = len(first.economy.ledger)
            wrong = Activity(
                template.role.work_activity_id, template.role.work_activity_name,
                "market", "forged wrong-location work", ["work"],
            )
            wrong_result = first.economy.process_activity(
                employee, wrong, day=241, hour=8
            )
            scenarios["wrong_work_location_is_unpaid"] = (
                wrong_result is None and len(first.economy.ledger) == before
            )
            prestart = Activity(
                template.role.work_activity_id, template.role.work_activity_name,
                formation.location_id, "premature work", ["work"],
            )
            scenarios["prestart_work_is_unpaid"] = first.economy.process_activity(
                employee, prestart, day=employment.start_day - 1, hour=8
            ) is None
            paid_day = wages[0].day
            ledger_size = len(first.economy.ledger)
            scenarios["duplicate_daily_wage_is_rejected"] = (
                first.economy.process_activity(
                    employee, prestart, day=paid_day, hour=9
                ) is None and len(first.economy.ledger) == ledger_size
            )
            unrelated = next(item for item in first.agents
                             if item.id != employee.id)
            scenarios["unrelated_resident_cannot_claim_role_wage"] = (
                first.economy.process_activity(
                    unrelated, prestart, day=241, hour=8
                ) is None and len(first.economy.ledger) == ledger_size
            )
            invalid_activity = Activity(
                "invented_garden_work", "Invented work", formation.location_id,
                "forged activity", ["work"],
            )
            scenarios["unknown_work_activity_is_unpaid"] = (
                first.economy.process_activity(
                    employee, invalid_activity, day=241, hour=8
                ) is None and len(first.economy.ledger) == ledger_size
            )

            saved = json.loads((root / "long-a.json").read_text(encoding="utf-8"))
            scenarios.update({
                "unknown_institution_schema_fails_closed": _mutated_load_rejected(
                    root, saved, "bad-schema",
                    lambda data: data["institution_growth"].update(schema_version=999),
                ),
                "unknown_template_fails_closed": _mutated_load_rejected(
                    root, saved, "bad-template",
                    lambda data: data["institution_growth"]["formation_records"][0].update(
                        template_id="unknown"
                    ),
                ),
                "inactive_location_fails_closed": _mutated_load_rejected(
                    root, saved, "bad-location",
                    lambda data: data["institution_growth"]["formation_records"][0].update(
                        location_id="civic_pavilion"
                    ),
                ),
                "wrong_employer_owner_fails_closed": _mutated_load_rejected(
                    root, saved, "bad-owner",
                    lambda data: next(item for item in data["economy"]["accounts"]
                                      if item["id"] == formation.employer_account_id).update(
                        owner_id="forged"
                    ),
                ),
                "missing_startup_transfer_fails_closed": _mutated_load_rejected(
                    root, saved, "missing-startup",
                    lambda data: data["economy"]["ledger"].__setitem__(
                        slice(None), [item for item in data["economy"]["ledger"]
                                      if item["id"] != formation.startup_transaction_id]
                    ),
                ),
                "formation_without_employment_fails_closed": _mutated_load_rejected(
                    root, saved, "missing-employment",
                    lambda data: data["economy"]["employments"].__setitem__(
                        slice(None), [item for item in data["economy"]["employments"]
                                      if item["id"] != formation.employment_id]
                    ),
                ),
                "wrong_role_location_fails_closed": _mutated_load_rejected(
                    root, saved, "wrong-role-location",
                    lambda data: next(item for item in data["economy"]["employments"]
                                      if item["id"] == formation.employment_id).update(
                        activity_locations={template.role.work_activity_id: "market"}
                    ),
                ),
                "forged_memory_fails_closed": _mutated_load_rejected(
                    root, saved, "forged-memory",
                    lambda data: data["agents"][0]["memory"].append({
                        **deepcopy(data["agents"][0]["memory"][0]),
                        "id": "memory:agent_001:institution_growth:forged:employment_started",
                        "source_system": "institution_growth", "source_id": "forged",
                        "event_type": "employment_started", "causal": True,
                        "owner_id": "agent_001", "knowledge_basis": "participant",
                    }),
                ),
            })

            institution_checks = first.institution_growth.validate(
                agents=first.agents, locations=first.locations,
                location_growth=first.location_growth,
                event_ecology=first.event_ecology, economy=first.economy,
            )
            invariants = {
                **institution_checks,
                "currency_conserved": first.economy.conservation_holds(),
                "ledger_reconstructs": first.economy.ledger_reconstructs_balances(),
                "startup_transfer_unique": sum(
                    item.event_key == f"institution-startup:{formation.id}"
                    for item in first.economy.ledger
                ) == 1,
                "daily_dynamic_wages_unique": len({item.event_key for item in wages})
                == len(wages),
                "migration_invariants_valid": all(
                    item.status != "activated"
                    or any(agent.id == item.agent_id for agent in first.agents)
                    for item in first.town_growth.migration_records
                ),
                "location_growth_invariants_valid": all(
                    first.location_growth.validate(first.locations, first.agents).values()
                ),
                "event_ecology_invariants_valid": all(first.event_ecology.validate(
                    locations=first.locations, location_growth=first.location_growth,
                    activity_records=first.activity_records,
                ).values()),
                "material_conservation_valid": first.materials.material_conservation_holds(),
                "material_provenance_valid": first.materials.provenance_reconciles(),
                "commitments_valid": all(
                    first.commitment_system.validate_invariants().values()
                ),
                "v4_plans_valid": all(first.plan_system.validate_invariants().values()),
                "crime_history_valid": first.crime.evidence_is_valid(),
                "justice_history_valid": first.justice.history_is_valid(),
                "outcome_memory_provenance_valid": all(
                    first.outcome_memory.validate().values()
                ),
                "no_material_actor_for_institution": formation.institution_id not in
                first.materials.inventories,
            }
    finally:
        random.setstate(caller_state)
    failed_scenarios = sorted(key for key, value in scenarios.items() if not value)
    failed_invariants = sorted(key for key, value in invariants.items() if not value)
    diagnostics.update({
        "failed_scenarios": failed_scenarios,
        "failed_invariants": failed_invariants,
    })
    return {
        "passed": not failed_scenarios and not failed_invariants,
        "scenario_count": len(scenarios),
        "scenarios_passed": sum(bool(item) for item in scenarios.values()),
        "invariant_count": len(invariants),
        "invariants_passed": sum(bool(item) for item in invariants.values()),
        "scenarios": scenarios, "invariants": invariants,
        "diagnostics": diagnostics,
    }
