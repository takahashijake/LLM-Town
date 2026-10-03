"""Deterministic V5 Phase 6 multi-site growth acceptance gate."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


HORIZON_DAYS = 260


def _engine(root: Path, name: str, *, load: bool = False) -> SimulationEngine:
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs", simulation_seed=11,
    )


def _run(engine: SimulationEngine, days: int) -> None:
    with redirect_stdout(StringIO()):
        engine.run(days, [8])


def _horizon(root: Path, name: str, splits: tuple[int, ...]) -> SimulationEngine:
    caller_state = random.getstate()
    random.seed(11)
    try:
        engine = _engine(root, name)
        for index, days in enumerate(splits):
            if index:
                engine = _engine(root, name, load=True)
            _run(engine, days)
        return engine
    finally:
        random.setstate(caller_state)


def _growth_memories(engine: SimulationEngine) -> list[str]:
    systems = {
        "town_growth", "location_growth", "institution_growth",
        "commerce_growth",
    }
    return sorted(
        memory.id for agent in engine.agents
        for memory in agent.memory + agent.memory_archive
        if memory.source_system in systems
    )


def _signature(engine: SimulationEngine) -> dict:
    migrations = [item for item in engine.town_growth.migration_records
                  if item.status == "activated"]
    locations = [item for item in engine.location_growth.activation_records
                 if item.status == "activated"]
    formations = [item for item in engine.institution_growth.formation_records
                  if item.status == "activated"]
    commerce = [item for item in engine.commerce_growth.activation_records
                if item.status == "activated"]
    employment_ids = {item.employment_id for item in formations}
    dynamic_inventory_ids = {item.inventory_id for item in commerce}
    return {
        "resident_ids": [item.id for item in engine.agents],
        "migration_ids": [item.id for item in migrations],
        "migration_templates": [item.template_id for item in migrations],
        "migration_residents": [item.agent_id for item in migrations],
        "active_locations": [item.id for item in engine.locations],
        "location_activation_ids": [item.id for item in locations],
        "location_templates": [item.template_id for item in locations],
        "event_occurrences": sorted(
            (item.location_id, item.template_id, item.occurrence_id)
            for item in engine.event_ecology.occurrence_history
        ),
        "institution_ids": [item.institution_id for item in formations],
        "formation_ids": [item.id for item in formations],
        "institution_templates": [item.template_id for item in formations],
        "employees": [item.employee_agent_id for item in formations],
        "employment_ids": [item.employment_id for item in formations],
        "work_activity_ids": [
            engine.economy.employments[item.employment_id].qualifying_activity_ids
            for item in formations
        ],
        "employer_account_ids": [item.employer_account_id for item in formations],
        "startup_transaction_ids": [item.startup_transaction_id for item in formations],
        "dynamic_work_records": sorted(
            item["id"] for item in engine.economy.work_events
            if item.get("employment_id") in employment_ids
        ),
        "wage_transactions": sorted(
            item.event_key for item in engine.economy.ledger
            if item.transaction_type == "wage"
            and dict(item.metadata).get("employment_id") in employment_ids
        ),
        "commerce_activation_ids": [item.id for item in commerce],
        "dynamic_sellers": sorted(
            item.id for item in engine.materials.sellers.values()
            if item.commerce_activation_id is not None
        ),
        "commerce_exchanges": sorted(
            item.event_key for item in engine.materials.exchanges
            if item.seller_id.startswith("seller:institution:")
            or item.buyer_inventory_id in dynamic_inventory_ids
        ),
        "balances": sorted(
            (key, account.balance) for key, account in engine.economy.accounts.items()
        ),
        "total_currency": engine.economy.total_currency(),
        "material_totals": sorted(engine.materials.total_quantities().items()),
        "memory_ids": _growth_memories(engine),
    }


def _mutated_load_rejected(
    root: Path, saved: dict, name: str, mutate,
) -> bool:
    data = deepcopy(saved)
    mutate(data)
    (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    try:
        _engine(root, name, load=True)
    except (KeyError, TypeError, ValueError):
        return True
    return False


def _find_memory_owner(data: dict, source_id: str, event_type: str) -> dict:
    for agent in data["agents"]:
        for key in ("memory", "memory_archive"):
            if any(
                item.get("source_id") == source_id
                and item.get("event_type") == event_type
                for item in agent.get(key, [])
            ):
                return agent
    raise AssertionError("expected authoritative memory is absent")


def evaluate_multi_site_growth() -> dict:
    scenarios: dict[str, bool] = {}
    invariants: dict[str, bool] = {}
    diagnostics: dict[str, object] = {"horizon_days": HORIZON_DAYS}
    with TemporaryDirectory() as directory:
        root = Path(directory)
        fresh = _horizon(root, "fresh", (HORIZON_DAYS,))
        resumed = _horizon(root, "resumed", (90, 80, 90))
        repeated = _horizon(root, "repeated", (HORIZON_DAYS,))
        signature = _signature(fresh)
        diagnostics["long_horizon_signature"] = signature
        scenarios["fresh_resume_repeat_authority_matches"] = (
            signature == _signature(resumed) == _signature(repeated)
        )

        migrations = [item for item in fresh.town_growth.migration_records
                      if item.status == "activated"]
        activations = [item for item in fresh.location_growth.activation_records
                       if item.status == "activated"]
        formations = [item for item in fresh.institution_growth.formation_records
                      if item.status == "activated"]
        commerce = [item for item in fresh.commerce_growth.activation_records
                    if item.status == "activated"]
        migration_templates = set(fresh.town_growth.templates)
        location_templates = set(fresh.location_growth.templates)
        institution_templates = set(fresh.institution_growth.templates)

        scenarios.update({
            "two_finite_migrations_activate": (
                len(migrations) == 2
                and {item.template_id for item in migrations} == migration_templates
            ),
            "migration_ids_and_residents_are_independent": (
                len({item.id for item in migrations}) == 2
                and len({item.agent_id for item in migrations}) == 2
            ),
            "migration_template_order_is_stable_id_order": (
                [item.template_id for item in migrations]
                == sorted(migration_templates)
            ),
            "migrants_have_exact_account_and_inventory": all(
                fresh.economy.account_for_agent(item.agent_id).id
                == f"account:agent:{item.agent_id}"
                and fresh.materials.inventory_for_agent(item.agent_id).id
                == f"inventory:agent:{item.agent_id}"
                for item in migrations
            ),
            "two_finite_places_activate": (
                len(activations) == 2
                and {item.template_id for item in activations} == location_templates
            ),
            "place_order_is_stable_id_order": (
                [item.template_id for item in activations]
                == sorted(location_templates)
            ),
            "both_dynamic_places_are_used": all(
                any(row.get("type") == "activity"
                    and row.get("location") == activation.location_id
                    for row in fresh.activity_records)
                for activation in activations
            ),
            "events_occur_at_both_dynamic_places": (
                {item.location_id for item in fresh.event_ecology.occurrence_history}
                == {item.location_id for item in activations}
            ),
            "event_bindings_are_exact": all(
                fresh.event_ecology.templates[item.template_id].location_template_id
                == next(
                    activation.template_id for activation in activations
                    if activation.location_id == item.location_id
                )
                for item in fresh.event_ecology.occurrence_history
            ),
            "two_institutions_form": (
                len(formations) == 2
                and {item.template_id for item in formations}
                == institution_templates
            ),
            "institutions_have_distinct_authority": all(
                len({getattr(item, field) for item in formations}) == 2
                for field in (
                    "id", "institution_id", "employee_agent_id",
                    "employer_account_id", "employment_id",
                )
            ),
            "institution_order_is_stable_id_order": (
                [item.template_id for item in formations]
                == sorted(institution_templates)
            ),
            "institution_location_and_event_evidence_is_isolated": all(
                formation.location_id
                == fresh.location_growth.templates[
                    fresh.institution_growth.templates[
                        formation.template_id
                    ].location_template_id
                ].location_id
                and all(
                    occurrence.location_id == formation.location_id
                    for occurrence in fresh.event_ecology.occurrence_history
                    if occurrence.template_id in fresh.institution_growth.templates[
                        formation.template_id
                    ].relevant_dynamic_event_template_ids
                )
                for formation in formations
            ),
            "both_dynamic_jobs_work_and_receive_wages": all(
                any(item.get("employment_id") == formation.employment_id
                    for item in fresh.economy.work_events)
                and any(
                    item.transaction_type == "wage"
                    and dict(item.metadata).get("employment_id")
                    == formation.employment_id
                    for item in fresh.economy.ledger
                )
                for formation in formations
            ),
            "employment_contracts_match_templates": all(
                (lambda employment, template: (
                    employment.agent_id == formation.employee_agent_id
                    and employment.role_template_id == template.role.role_template_id
                    and employment.qualifying_activity_ids
                    == (template.role.work_activity_id,)
                    and dict(employment.activity_locations).get(
                        template.role.work_activity_id
                    ) == formation.location_id
                ))(
                    fresh.economy.employments[formation.employment_id],
                    fresh.institution_growth.templates[formation.template_id],
                )
                for formation in formations
            ),
            "only_garden_commerce_activates": (
                len(commerce) == 1
                and commerce[0].template_id == "commerce_template_001"
                and commerce[0].institution_formation_id
                == next(item.id for item in formations
                        if item.template_id == "institution_template_001")
            ),
            "pavilion_institution_is_noncommercial": all(
                item.institution_id != next(
                    formation.institution_id for formation in formations
                    if formation.template_id == "institution_template_002"
                )
                for item in commerce
            ),
            "garden_procurement_production_and_sales_continue": bool(commerce) and all((
                any(item.buyer_inventory_id == commerce[0].inventory_id
                    and item.seller_id == commerce[0].upstream_seller_id
                    for item in fresh.materials.exchanges),
                any(item.recipe_id == commerce[0].recipe_id
                    for item in fresh.materials.production_records),
                any(item.seller_id == commerce[0].seller_id
                    for item in fresh.materials.exchanges),
            )),
            "static_market_remains_active": any(
                item.seller_id == "seller:market_stall"
                for item in fresh.materials.exchanges
            ),
        })

        invariants.update(fresh.location_growth.validate(
            fresh.locations, fresh.agents
        ))
        invariants.update(fresh.event_ecology.validate(
            locations=fresh.locations, location_growth=fresh.location_growth,
            activity_records=fresh.activity_records,
        ))
        invariants.update(fresh.institution_growth.validate(
            agents=fresh.agents, locations=fresh.locations,
            location_growth=fresh.location_growth,
            event_ecology=fresh.event_ecology, economy=fresh.economy,
        ))
        invariants.update({
            "currency_conserved": fresh.economy.conservation_holds(),
            "ledger_reconstructs": fresh.economy.ledger_reconstructs_balances(),
            "materials_conserved": fresh.materials.material_conservation_holds(),
            "material_history_reconstructs": (
                fresh.materials.material_history_reconstructs_inventories()
            ),
            "material_provenance_valid": fresh.materials.provenance_reconciles(),
            "production_provenance_valid": (
                fresh.materials.production_records_are_valid()
            ),
            "outcome_memory_isolated": all(
                fresh.outcome_memory.validate().values()
            ),
            "migration_templates_consumed_exactly": (
                fresh.town_growth.consumed_template_ids == migration_templates
            ),
            "location_templates_consumed_exactly": (
                fresh.location_growth.consumed_template_ids == location_templates
            ),
            "institution_templates_consumed_exactly": (
                fresh.institution_growth.consumed_template_ids
                == institution_templates
            ),
            "commerce_template_consumed_exactly": (
                fresh.commerce_growth.consumed_template_ids
                == {"commerce_template_001"}
            ),
            "daily_wages_are_unique": len([
                item.event_key for item in fresh.economy.ledger
                if item.transaction_type == "wage"
            ]) == len({
                item.event_key for item in fresh.economy.ledger
                if item.transaction_type == "wage"
            }),
        })

        saved = json.loads((root / "fresh.json").read_text(encoding="utf-8"))
        attacks = {
            "swapped_migration_templates_rejected": lambda data: (
                data["town_growth"]["migration_records"][0].update(
                    template_id="resident_template_002"
                ),
                data["town_growth"]["migration_records"][1].update(
                    template_id="resident_template_001"
                ),
            ),
            "duplicate_migration_resident_rejected": lambda data: data[
                "town_growth"
            ]["migration_records"][1].update(
                agent_id=data["town_growth"]["migration_records"][0]["agent_id"]
            ),
            "swapped_location_templates_rejected": lambda data: (
                data["location_growth"]["activation_records"][0].update(
                    template_id="location_template_002"
                ),
                data["location_growth"]["activation_records"][1].update(
                    template_id="location_template_001"
                ),
            ),
            "duplicate_activated_location_rejected": lambda data: data[
                "location_growth"
            ]["activation_records"][1].update(location_id="community_garden"),
            "pavilion_institution_on_garden_rejected": lambda data: data[
                "institution_growth"
            ]["formation_records"][1].update(
                location_id="community_garden",
                location_activation_id="location-activation:0001",
            ),
            "garden_institution_on_pavilion_rejected": lambda data: data[
                "institution_growth"
            ]["formation_records"][0].update(
                location_id="civic_pavilion",
                location_activation_id="location-activation:0002",
            ),
            "swapped_institution_employees_rejected": lambda data: (
                data["institution_growth"]["formation_records"][0].update(
                    employee_agent_id="agent_006"
                ),
                data["institution_growth"]["formation_records"][1].update(
                    employee_agent_id="agent_005"
                ),
            ),
            "two_employments_for_one_agent_rejected": lambda data: next(
                item for item in data["economy"]["employments"]
                if item["id"] == "employment:institution:0002"
            ).update(agent_id="agent_005"),
            "duplicate_institution_account_owner_rejected": lambda data: next(
                item for item in data["economy"]["accounts"]
                if item["id"] == "account:institution:0002"
            ).update(owner_id="institution:0001"),
            "missing_second_startup_rejected": lambda data: data["economy"].update(
                ledger=[item for item in data["economy"]["ledger"]
                        if item.get("event_key")
                        != "institution-startup:institution-formation:0002"]
            ),
            "marked_unused_migration_template_rejected": lambda data: data[
                "town_growth"
            ]["consumed_template_ids"].append("forged-template"),
            "unconsumed_location_template_rejected": lambda data: data[
                "location_growth"
            ].update(consumed_template_ids=["location_template_001"]),
            "rewound_migration_sequence_rejected": lambda data: data[
                "town_growth"
            ].update(next_migration_sequence=2),
            "rewound_location_sequence_rejected": lambda data: data[
                "location_growth"
            ].update(next_activation_sequence=2),
            "rewound_institution_sequence_rejected": lambda data: data[
                "institution_growth"
            ].update(next_sequence=2),
            "duplicate_institution_review_rejected": lambda data: data[
                "institution_growth"
            ]["review_history"].append(
                deepcopy(data["institution_growth"]["review_history"][-1])
            ),
            "wrong_second_role_rejected": lambda data: next(
                item for item in data["economy"]["employments"]
                if item["id"] == "employment:institution:0002"
            ).update(role_template_id="community_garden_steward"),
            "wrong_second_work_location_rejected": lambda data: next(
                item for item in data["economy"]["employments"]
                if item["id"] == "employment:institution:0002"
            )["activity_locations"].update(
                coordinate_civic_pavilion="community_garden"
            ),
            "garden_commerce_on_pavilion_rejected": lambda data: data[
                "commerce_growth"
            ]["activation_records"][0].update(
                institution_formation_id="institution-formation:0002",
                institution_id="institution:0002",
                operator_agent_id="agent_006",
                operator_employment_id="employment:institution:0002",
                institution_account_id="account:institution:0002",
                location_id="civic_pavilion",
                location_activation_id="location-activation:0002",
            ),
            "orphan_pavilion_inventory_rejected": lambda data: data[
                "materials"
            ]["inventories"].append({
                **deepcopy(next(item for item in data["materials"]["inventories"]
                              if item.get("commerce_activation_id"))),
                "id": "inventory:institution:forged",
                "owner_id": "institution:0002",
                "account_id": "account:institution:0002",
                "commerce_activation_id": "commerce-activation:forged",
            }),
            "forged_pavilion_seller_rejected": lambda data: data[
                "materials"
            ]["sellers"].append({
                **deepcopy(next(item for item in data["materials"]["sellers"]
                              if item.get("commerce_activation_id"))),
                "id": "seller:institution:forged",
                "institution_id": "institution:0002",
                "location_id": "civic_pavilion",
                "commerce_activation_id": "commerce-activation:forged",
            }),
        }

        def forge_private_memory(data: dict) -> None:
            owner = _find_memory_owner(
                data, "institution-formation:0002", "employment_started"
            )
            source = next(
                item for key in ("memory", "memory_archive")
                for item in owner.get(key, [])
                if item.get("source_id") == "institution-formation:0002"
                and item.get("event_type") == "employment_started"
            )
            forged = deepcopy(source)
            forged.update({
                "id": "memory:agent_001:institution_growth:"
                      "institution-formation:0002:employment_started",
                "owner_id": "agent_001",
            })
            data["agents"][0].setdefault("memory", []).append(forged)

        attacks["forged_second_employment_memory_rejected"] = forge_private_memory
        scenarios.update({
            name: _mutated_load_rejected(root, saved, name, mutate)
            for name, mutate in attacks.items()
        })

        before = (
            len(fresh.town_growth.migration_records),
            fresh.town_growth.next_migration_sequence,
            len(fresh.location_growth.activation_records),
            fresh.location_growth.next_activation_sequence,
            len(fresh.institution_growth.formation_records),
            fresh.institution_growth.next_sequence,
            len(fresh.commerce_growth.activation_records),
            fresh.commerce_growth.next_sequence,
        )
        stabilized = _engine(root, "fresh", load=True)
        _run(stabilized, 30)
        after = (
            len(stabilized.town_growth.migration_records),
            stabilized.town_growth.next_migration_sequence,
            len(stabilized.location_growth.activation_records),
            stabilized.location_growth.next_activation_sequence,
            len(stabilized.institution_growth.formation_records),
            stabilized.institution_growth.next_sequence,
            len(stabilized.commerce_growth.activation_records),
            stabilized.commerce_growth.next_sequence,
        )
        scenarios["finite_growth_stabilizes_without_sequence_churn"] = before == after
        scenarios["bounded_review_histories_remain_bounded"] = all((
            len(stabilized.town_growth.review_history)
            <= stabilized.town_growth.REVIEW_HISTORY_LIMIT,
            len(stabilized.location_growth.review_history)
            <= stabilized.location_growth.REVIEW_HISTORY_LIMIT,
            len(stabilized.institution_growth.review_history)
            <= stabilized.institution_growth.policy.history_limit,
            len(stabilized.commerce_growth.review_history)
            <= stabilized.commerce_growth.policy.history_limit,
        ))

    failed_scenarios = sorted(
        name for name, passed in scenarios.items() if not passed
    )
    failed_invariants = sorted(
        name for name, passed in invariants.items() if not passed
    )
    diagnostics["failed_scenarios"] = failed_scenarios
    diagnostics["failed_invariants"] = failed_invariants
    return {
        "passed": not failed_scenarios and not failed_invariants,
        "scenario_count": len(scenarios),
        "scenarios_passed": len(scenarios) - len(failed_scenarios),
        "invariant_count": len(invariants),
        "invariants_passed": len(invariants) - len(failed_invariants),
        "scenarios": scenarios,
        "invariants": invariants,
        "diagnostics": diagnostics,
    }
