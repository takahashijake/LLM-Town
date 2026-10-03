"""Deterministic V5 Phase 2 authoritative-location acceptance evaluation."""

from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.location_growth import (
    DevelopmentReview,
    LocationActivationRecord,
    LocationGrowthSystem,
    LocationTemplate,
)


def _engine(root: Path, name: str, *, load: bool = False) -> SimulationEngine:
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs", simulation_seed=11,
    )


def _activity(engine: SimulationEngine, first: int, last: int) -> None:
    for day in range(first, last + 1):
        for agent in engine.agents:
            engine.activity_records.append({
                "type": "activity", "day": day, "hour": 8,
                "agent_id": agent.id, "agent": agent.name,
            })


def _long_horizon(root: Path, name: str) -> tuple[SimulationEngine, dict]:
    caller_state = random.getstate()
    random.seed(11)
    try:
        engine = _engine(root, name)
        with redirect_stdout(StringIO()):
            engine.run(60, [8])
        resumed = _engine(root, name, load=True)
        with redirect_stdout(StringIO()):
            resumed.run(60, [8])
    finally:
        random.setstate(caller_state)
    records = resumed.location_growth.activation_records
    activation = records[0] if records else None
    opening_memories = [
        memory for agent in resumed.agents
        for memory in agent.memory + agent.memory_archive
        if memory.event_type == "location_opened"
    ]
    conversations = [
        memory for agent in resumed.agents
        for memory in agent.memory + agent.memory_archive
        if memory.type == "conversation" and memory.location == "community_garden"
    ]
    signature = {
        "agent_ids": [agent.id for agent in resumed.agents],
        "location_ids": [location.id for location in resumed.locations],
        "migration_ids": [record.id for record in resumed.town_growth.migration_records],
        "activation_ids": [record.id for record in records],
        "activation_days": [record.activation_day for record in records],
        "consumed_templates": sorted(resumed.location_growth.consumed_template_ids),
        "public_history": list(resumed.location_growth.public_history),
        "opening_memory_ids": sorted(memory.id for memory in opening_memories),
        "garden_activity_count": sum(
            row.get("location") == "community_garden"
            for row in resumed.activity_records
        ),
        "garden_conversation_memory_count": len(conversations),
        "review_count": len(resumed.location_growth.review_history),
        "activation": activation.id if activation else None,
    }
    return resumed, signature


def _load_rejected(root: Path, name: str, mutate) -> bool:
    engine = _engine(root, name)
    with redirect_stdout(StringIO()):
        engine.run(35, [8])
    data = json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
    mutate(data)
    (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    try:
        _engine(root, name, load=True)
    except (KeyError, TypeError, ValueError):
        return True
    return False


def evaluate_location_growth() -> dict:
    scenarios: dict[str, bool] = {}
    diagnostics: dict[str, object] = {}
    with TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = _engine(root, "baseline")
        scenarios["starts_with_four_base_locations"] = (
            [item.id for item in baseline.locations]
            == ["town_square", "cafe", "library", "market"]
        )
        scenarios["time_alone_does_not_activate_a_place"] = (
            baseline.review_location_growth(28).reason == "insufficient_population"
            and not baseline.location_growth.activation_records
        )

        migrated = _engine(root, "migrated")
        _activity(migrated, 8, 14)
        migrated.review_town_growth(14)
        scenarios["migration_precedes_development"] = len(migrated.agents) == 5
        scenarios["population_without_sustained_activity_is_not_ready"] = (
            migrated.review_location_growth(28).reason
            == "insufficient_sustained_activity"
        )
        migrated = _engine(root, "eligible")
        _activity(migrated, 8, 14)
        migrated.review_town_growth(14)
        _activity(migrated, 22, 28)
        review = migrated.review_location_growth(28)
        activation = migrated.location_growth.activation_records[0]
        scenarios.update({
            "eligible_review_activates_one_configured_place": (
                review.status == "activated" and len(migrated.locations) == 5
            ),
            "stable_review_and_activation_ids": (
                review.event_key == "location-review:day:28"
                and activation.id == "location-activation:0001"
            ),
            "finite_template_identity_is_exact": (
                activation.template_id == "location_template_001"
                and activation.location_id == "community_garden"
            ),
            "template_consumed_exactly_once": (
                migrated.location_growth.consumed_template_ids
                == {"location_template_001"}
            ),
            "public_history_is_authoritative": (
                migrated.location_growth.public_history[0]["activation_id"]
                == activation.id
            ),
            "opening_memory_is_exactly_once_per_resident": sum(
                memory.event_type == "location_opened"
                for agent in migrated.agents
                for memory in agent.memory + agent.memory_archive
            ) == 5,
            "opening_grants_no_employment": len(migrated.economy.employments) == 4,
            "opening_grants_no_seller": len(migrated.materials.sellers) == 1,
            "opening_grants_no_inventory": all(
                inventory.owner_id != "community_garden"
                for inventory in migrated.materials.inventories.values()
            ),
        })
        migrated.review_location_growth(28)
        scenarios["review_replay_duplicates_nothing"] = (
            len(migrated.locations) == 5
            and len(migrated.location_growth.activation_records) == 1
            and len(migrated.location_growth.public_history) == 1
        )
        scenarios["activation_replay_duplicates_nothing"] = (
            migrated.activate_pending_location(28) is None
            and len(migrated.locations) == 5
        )
        migrated.location_growth.policy = replace(
            migrated.location_growth.policy, location_capacity=6
        )
        _activity(migrated, 29, 35)
        scenarios["development_cooldown_blocks_second_template"] = (
            migrated.review_location_growth(35).reason == "development_cooldown"
            and len(migrated.locations) == 5
        )

        capacity = _engine(root, "capacity")
        capacity.location_growth.policy = replace(
            capacity.location_growth.policy, location_capacity=4
        )
        scenarios["capacity_prevents_activation"] = (
            capacity.review_location_growth(28).reason
            == "location_capacity_or_templates_exhausted"
        )
        early = _engine(root, "early")
        scenarios["earliest_day_gate_fails_closed"] = (
            early.review_location_growth(1).reason == "before_earliest_development_day"
        )
        off_schedule = _engine(root, "schedule")
        scenarios["review_schedule_is_fixed"] = (
            off_schedule.review_location_growth(29).reason == "outside_review_schedule"
        )

        template = baseline.location_growth.template("location_template_001")
        try:
            LocationTemplate.from_dict({**{
                "id": template.id, "location_id": template.location_id,
                "name": template.name, "description": template.description,
                "affinities": ["executable_power"],
            }})
            bad_affinity = False
        except ValueError:
            bad_affinity = True
        scenarios["unknown_affinity_fails_closed"] = bad_affinity
        try:
            LocationGrowthSystem(
                baseline.location_growth.policy, [template, template], baseline.locations
            )
            duplicate_template = False
        except ValueError:
            duplicate_template = True
        scenarios["duplicate_template_identity_fails_closed"] = duplicate_template
        try:
            LocationGrowthSystem(
                baseline.location_growth.policy,
                [template, replace(template, id="location_template_other")],
                baseline.locations,
            )
            duplicate_location_id = False
        except ValueError:
            duplicate_location_id = True
        scenarios["duplicate_location_id_fails_closed"] = duplicate_location_id
        try:
            LocationGrowthSystem(
                baseline.location_growth.policy,
                [template, replace(
                    template, id="location_template_other",
                    location_id="other_place",
                )],
                baseline.locations,
            )
            duplicate_location_name = False
        except ValueError:
            duplicate_location_name = True
        scenarios["duplicate_location_name_fails_closed"] = duplicate_location_name
        try:
            LocationTemplate.from_dict({"id": "incomplete"})
            malformed = False
        except ValueError:
            malformed = True
        scenarios["malformed_template_fails_closed"] = malformed
        try:
            baseline.location_growth.template("unknown")
            unknown = False
        except ValueError:
            unknown = True
        scenarios["unknown_template_fails_closed"] = unknown
        try:
            DevelopmentReview("wrong", 28, "waiting", "test")
            wrong_review = False
        except ValueError:
            wrong_review = True
        scenarios["wrong_review_event_key_fails_closed"] = wrong_review
        try:
            LocationActivationRecord(
                "location-activation:0001", "location-review:day:29",
                template.id, template.location_id, 28,
            )
            wrong_record = False
        except ValueError:
            wrong_record = True
        scenarios["wrong_activation_record_fails_closed"] = wrong_record

        scenarios["unknown_persisted_template_fails_closed"] = _load_rejected(
            root, "unknown-template-save",
            lambda data: data["location_growth"]["activation_records"][0].update(
                {"template_id": "missing-template"}
            ),
        )
        scenarios["partial_record_without_consumption_fails_closed"] = _load_rejected(
            root, "partial-consumption",
            lambda data: data["location_growth"].update({"consumed_template_ids": []}),
        )
        scenarios["partial_authority_without_record_fails_closed"] = _load_rejected(
            root, "partial-record",
            lambda data: data["location_growth"].update({"activation_records": []}),
        )
        scenarios["unknown_resident_location_fails_closed"] = _load_rejected(
            root, "unknown-resident-location",
            lambda data: data["agents"][0].update({"location_id": "invented-place"}),
        )
        scenarios["forged_opening_provenance_fails_closed"] = _load_rejected(
            root, "forged-memory",
            lambda data: next(
                memory for agent in data["agents"]
                for memory in agent["memory"] + agent["memory_archive"]
                if memory.get("event_type") == "location_opened"
            ).update({"source_id": "location-activation:9999"}),
        )
        scenarios["stale_serialized_readiness_has_no_authority"] = _load_rejected(
            root, "stale-ready",
            lambda data: data["location_growth"].update({"ready": True}),
        )

        old = _engine(root, "old-save")
        old.state.save(old, 1, 8, day_complete=True)
        old_data = json.loads((root / "old-save.json").read_text(encoding="utf-8"))
        old_data.pop("location_growth", None)
        (root / "old-save.json").write_text(json.dumps(old_data), encoding="utf-8")
        old_loaded = _engine(root, "old-save", load=True)
        scenarios["old_save_without_location_growth_loads_base_town"] = (
            len(old_loaded.locations) == 4
        )

        first, first_signature = _long_horizon(root, "long-a")
        second, second_signature = _long_horizon(root, "long-b")
        diagnostics["long_horizon_signature"] = first_signature
        scenarios.update({
            "integrated_horizon_has_configured_migrations": (
                first_signature["migration_ids"]
                == ["migration:0001", "migration:0002"]
            ),
            "integrated_horizon_has_configured_location_activations": (
                first_signature["activation_ids"]
                == ["location-activation:0001", "location-activation:0002"]
            ),
            "save_resume_reconstructs_location_once": (
                first_signature["location_ids"].count("community_garden") == 1
            ),
            "ordinary_runtime_uses_new_location": (
                first_signature["garden_activity_count"] > 0
            ),
            "ordinary_conversation_occurs_at_new_location": (
                first_signature["garden_conversation_memory_count"] > 0
            ),
            "public_opening_memory_remains_exactly_once": (
                len(first_signature["opening_memory_ids"])
                == len(set(first_signature["opening_memory_ids"])) == 11
            ),
            "seeded_runs_have_equivalent_authority": first_signature == second_signature,
            "finite_capacity_settles_without_repeated_attempts": (
                len(first.location_growth.activation_records)
                == len(first.location_growth.templates)
                and first_signature["review_count"] <= 28
            ),
        })

        subsystem_checks = {
            **first.location_growth.validate(first.locations, first.agents),
            "migration_invariants_hold": (
                len({x.id for x in first.town_growth.migration_records})
                == len(first.town_growth.migration_records)
                and all(
                    x.status != "activated"
                    or any(agent.id == x.agent_id for agent in first.agents)
                    for x in first.town_growth.migration_records
                )
            ),
            "economy_conservation_holds": (
                first.economy.conservation_holds()
                and first.economy.ledger_reconstructs_balances()
            ),
            "material_invariants_hold": (
                first.materials.material_conservation_holds()
                and first.materials.provenance_reconciles()
            ),
            "commitment_invariants_hold": all(
                first.commitment_system.validate_invariants().values()
            ),
            "plan_invariants_hold": all(first.plan_system.validate_invariants().values()),
            "crime_history_valid": first.crime.evidence_is_valid(),
            "justice_history_valid": first.justice.history_is_valid(),
            "outcome_memory_provenance_valid": all(first.outcome_memory.validate().values()),
            "activation_memory_count_matches_population": (
                len(first_signature["opening_memory_ids"]) == sum(
                    (len(first.agents) - len(first.town_growth.migration_records))
                    + sum(
                        migration.activation_day <= activation.activation_day
                        for migration in first.town_growth.migration_records
                        if migration.status == "activated"
                    )
                    for activation in first.location_growth.activation_records
                    if activation.status == "activated"
                )
            ),
            "migration_identity_unchanged_by_location_growth": (
                [(item.template_id, item.agent_id)
                 for item in first.town_growth.migration_records]
                == [
                    ("resident_template_001", "agent_005"),
                    ("resident_template_002", "agent_006"),
                ]
            ),
        }

    failed_scenarios = sorted(name for name, value in scenarios.items() if not value)
    failed_invariants = sorted(name for name, value in subsystem_checks.items() if not value)
    diagnostics.update({
        "failed_scenarios": failed_scenarios,
        "failed_invariants": failed_invariants,
    })
    return {
        "passed": not failed_scenarios and not failed_invariants,
        "scenario_count": len(scenarios),
        "scenarios_passed": sum(bool(value) for value in scenarios.values()),
        "invariant_count": len(subsystem_checks),
        "invariants_passed": sum(bool(value) for value in subsystem_checks.values()),
        "scenarios": scenarios,
        "invariants": subsystem_checks,
        "diagnostics": diagnostics,
    }
