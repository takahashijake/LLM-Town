"""Deterministic V5 Phase 1 resident-migration acceptance evaluation."""

from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from src.analysis.v3_freeze_evaluation import evaluate_v3_freeze
from src.analysis.v4_freeze_evaluation import evaluate_v4_freeze
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.simulation.social_snapshot import ConversationTickSnapshot
from src.systems.town_growth import ResidentTemplate, TownGrowthSystem


def _engine(root: Path, name: str, *, load: bool = False) -> SimulationEngine:
    return SimulationEngine(
        "data/agents.json",
        "data/locations.json",
        load_state=load,
        llm_client=FakeLLMClient(),
        state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs",
        simulation_seed=11,
    )


def _sustain_activity(engine: SimulationEngine, first: int = 8, last: int = 14):
    for day in range(first, last + 1):
        for agent in engine.agents:
            engine.activity_records.append({
                "type": "activity",
                "day": day,
                "hour": 8,
                "agent_id": agent.id,
                "agent": agent.name,
            })


def _eligible_engine(root: Path, name: str) -> SimulationEngine:
    engine = _engine(root, name)
    _sustain_activity(engine)
    engine.review_town_growth(14)
    return engine


def _arrival_memories(engine: SimulationEngine):
    return [
        memory
        for agent in engine.agents
        for memory in agent.memory + agent.memory_archive
        if memory.event_type == "resident_arrival"
    ]


def _long_horizon(root: Path, name: str) -> tuple[SimulationEngine, dict]:
    engine = _engine(root, name)
    with redirect_stdout(StringIO()):
        engine.run(45, [8])
    resumed = _engine(root, name, load=True)
    with redirect_stdout(StringIO()):
        resumed.run(45, [8])
    newcomer_id = resumed.town_growth.migration_records[0].agent_id
    signature = {
        "agent_ids": [agent.id for agent in resumed.agents],
        "migration_ids": [item.id for item in resumed.town_growth.migration_records],
        "settlements": [
            item.event_key for item in resumed.economy.ledger
            if item.transaction_type == "migration_settlement"
        ],
        "newcomer_activity_count": sum(
            item.get("agent_id") == newcomer_id
            for item in resumed.activity_records
        ),
        "arrival_memory_ids": sorted(item.id for item in _arrival_memories(resumed)),
        "public_history": list(resumed.town_growth.public_history),
    }
    return resumed, signature


def evaluate_population_growth() -> dict:
    scenarios: dict[str, bool] = {}
    diagnostics: dict[str, object] = {}

    with TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = _engine(root, "baseline")
        scenarios["static_four_resident_baseline_before_eligibility"] = (
            len(baseline.agents) == 4
        )
        early = baseline.review_town_growth(1)
        scenarios["review_before_earliest_day_has_no_proposal"] = (
            early.status == "waiting" and not baseline.town_growth.migration_records
        )

        inactive = _engine(root, "inactive")
        inactive_review = inactive.review_town_growth(14)
        scenarios["insufficient_sustained_activity_prevents_migration"] = (
            inactive_review.reason == "insufficient_sustained_activity"
        )

        capacity = _engine(root, "capacity")
        capacity.town_growth.policy = replace(
            capacity.town_growth.policy, resident_capacity=4
        )
        scenarios["population_at_capacity_prevents_migration"] = (
            capacity.review_town_growth(14).reason == "resident_capacity_reached"
        )

        invalid_location = _engine(root, "invalid-location")
        _sustain_activity(invalid_location)
        invalid_location.town_growth.policy = replace(
            invalid_location.town_growth.policy,
            arrival_location_id="missing-place",
        )
        scenarios["invalid_arrival_location_fails_closed"] = (
            invalid_location.review_town_growth(14).reason
            == "invalid_arrival_location"
        )

        missing_account = _engine(root, "missing-account")
        _sustain_activity(missing_account)
        missing_account.town_growth.policy = replace(
            missing_account.town_growth.policy,
            settlement_source_account_id="missing-account",
        )
        scenarios["unknown_settlement_account_fails_closed"] = (
            missing_account.review_town_growth(14).reason
            == "unknown_settlement_account"
        )

        no_funds = _engine(root, "no-funds")
        _sustain_activity(no_funds)
        no_funds.town_growth.policy = replace(
            no_funds.town_growth.policy,
            settlement_grant=10_000,
        )
        scenarios["insufficient_settlement_funds_prevent_activation"] = (
            no_funds.review_town_growth(14).reason
            == "insufficient_settlement_funds"
        )

        try:
            ResidentTemplate.from_dict({"id": "malformed", "name": "No Needs"})
            malformed_rejected = False
        except ValueError:
            malformed_rejected = True
        scenarios["malformed_resident_template_fails_closed"] = malformed_rejected

        duplicate = _engine(root, "duplicate")
        duplicate.town_growth = TownGrowthSystem(
            duplicate.town_growth.policy,
            [ResidentTemplate.from_dict({
                "id": "duplicate-template",
                "name": duplicate.agents[0].name,
                "personality": "quiet",
                "goals": ["build close friendships"],
                "initial_needs": {
                    "social": 50, "wealth": 50, "knowledge": 50,
                },
            })],
            next_resident_sequence=1,
        )
        _sustain_activity(duplicate)
        scenarios["duplicate_name_is_rejected"] = (
            duplicate.review_town_growth(14).reason == "duplicate_resident_name"
        )

        eligible = _eligible_engine(root, "eligible")
        record = eligible.town_growth.migration_records[0]
        newcomer = next(item for item in eligible.agents if item.id == record.agent_id)
        template = eligible.town_growth.template(record.template_id)
        settlement = next(
            item for item in eligible.economy.ledger
            if item.transaction_type == "migration_settlement"
        )
        source_id = eligible.town_growth.policy.settlement_source_account_id
        source_initial = eligible.economy.initial_balances[source_id]
        inventory = eligible.materials.inventory_for_agent(newcomer.id)
        memories = _arrival_memories(eligible)
        scenarios.update({
            "existing_agent_id_is_never_reused": newcomer.id == "agent_005",
            "eligible_review_selects_expected_finite_template": (
                template.id == "resident_template_001" and newcomer.name == "Nora"
            ),
            "exactly_one_stable_migration_id_is_allocated": (
                [item.id for item in eligible.town_growth.migration_records]
                == ["migration:0001"]
            ),
            "activation_adds_exactly_one_resident": len(eligible.agents) == 5,
            "resident_account_baseline_begins_at_zero": (
                eligible.economy.initial_balances[
                    f"account:agent:{newcomer.id}"
                ] == 0
            ),
            "grant_is_real_conserved_ledger_transfer": (
                settlement.event_key == "migration-settlement:migration:0001"
                and eligible.economy.conservation_holds()
                and eligible.economy.ledger_reconstructs_balances()
            ),
            "source_account_loses_exact_grant": (
                eligible.economy.get_account(source_id).balance
                == source_initial - eligible.town_growth.policy.settlement_grant
            ),
            "new_resident_gains_exact_grant": (
                eligible.economy.account_for_agent(newcomer.id).balance
                == eligible.town_growth.policy.settlement_grant
            ),
            "new_empty_inventory_owns_no_goods": inventory.quantities == (),
            "material_totals_and_provenance_unchanged": (
                eligible.materials.total_quantities()
                == eligible.materials.initial_total_quantities()
                and eligible.materials.provenance_reconciles()
            ),
            "existing_employments_remain_unchanged": (
                len(eligible.economy.employments) == 4
            ),
            "new_resident_is_unemployed": (
                newcomer.occupation == "unemployed"
                and eligible.economy.employment_for_agent(newcomer.id) is None
            ),
            "new_resident_is_not_crime_or_justice_privileged": (
                newcomer.id not in eligible.justice.investigator_agent_ids
                and all(
                    newcomer.id not in rule.eligible_actor_ids
                    for rule in eligible.crime.theft_activity_rules.values()
                )
            ),
            "every_cached_registry_recognizes_resident": (
                newcomer.id in eligible.crime.agents
                and newcomer.id in eligible.justice.agents
                and newcomer.id in eligible.outcome_memory.agents
                and any(item.id == newcomer.id for item in eligible.plan_system.agents)
                and any(
                    item.id == newcomer.id
                    for item in eligible.commitment_system.agents
                )
            ),
        })
        eligible.review_town_growth(14)
        scenarios["replaying_review_creates_no_duplicate_resident"] = (
            len(eligible.agents) == 5
            and len(eligible.town_growth.migration_records) == 1
        )
        scenarios["replaying_activation_duplicates_nothing"] = (
            eligible.activate_pending_migration(14) is None
            and len([item for item in eligible.economy.ledger
                     if item.transaction_type == "migration_settlement"]) == 1
            and len(_arrival_memories(eligible)) == 5
        )

        before = _engine(root, "before")
        _sustain_activity(before)
        proposed = before.town_growth.review(
            day=14, agents=before.agents, locations=before.locations,
            activity_records=before.activity_records, economy=before.economy,
        )
        before.state.save(before, 14, 8)
        before_resumed = _engine(root, "before", load=True)
        before_resumed.review_town_growth(14)
        scenarios["save_before_activation_matches_uninterrupted_execution"] = (
            proposed.migration_id == "migration:0001"
            and len(before_resumed.agents) == 5
            and before_resumed.economy.account_for_agent("agent_005").balance == 75
        )

        eligible.state.save(eligible, 14, 8, day_complete=True)
        after = _engine(root, "eligible", load=True)
        after.review_town_growth(14)
        scenarios["save_after_activation_is_replay_safe"] = (
            len(after.agents) == 5
            and len(after.town_growth.migration_records) == 1
            and len([item for item in after.economy.ledger
                     if item.transaction_type == "migration_settlement"]) == 1
        )

        old_state = json.loads((root / "baseline.json").read_text()) \
            if (root / "baseline.json").exists() else None
        baseline.state.save(baseline, 3, 8)
        old_state = json.loads((root / "baseline.json").read_text())
        old_state.pop("town_growth", None)
        (root / "baseline.json").write_text(json.dumps(old_state))
        old = _engine(root, "baseline", load=True)
        scenarios["old_save_without_growth_state_loads_safely"] = (
            len(old.agents) == 4 and not old.town_growth.migration_records
            and old.town_growth.next_resident_sequence == 5
        )
        scenarios["new_resident_receives_arrival_memory_once"] = (
            len([item for item in newcomer.memory + newcomer.memory_archive
                 if item.event_type == "resident_arrival"]) == 1
        )
        scenarios["existing_residents_receive_authoritative_public_arrival"] = (
            len(memories) == 5
            and all(item.source_system == "town_growth" for item in memories)
            and all(
                item.knowledge_basis == "public_event"
                for item in memories if item.owner_id != newcomer.id
            )
        )

        eligible.simulation_loop.start_new_day(eligible, 15)
        eligible.run_agent_activities(15, 8)
        newcomer_record = next(
            item for item in eligible.activity_records
            if item.get("day") == 15 and item.get("agent_id") == newcomer.id
        )
        scenarios["new_resident_participates_in_ordinary_next_day_activity"] = (
            bool(newcomer_record.get("activity_id"))
        )
        eligible.agents[0].location_id = newcomer.location_id
        snapshot = ConversationTickSnapshot.capture(eligible, 15, 8)
        scheduled = eligible.conversation_scheduler.schedule(snapshot)
        scenarios["new_resident_can_enter_ordinary_conversation_selection"] = any(
            newcomer.id in item.participant_ids for item in scheduled
        )
        newcomer_plans = [
            item for item in eligible.plan_system.goal_plans
            if item.agent_id == newcomer.id
        ]
        scenarios["new_resident_receives_ordinary_v4_goal_plan"] = bool(
            newcomer_plans
            and all(item.id.startswith(f"plan:goal:{newcomer.id}:")
                    for item in newcomer_plans)
        )
        progress_before = [goal.progress for goal in newcomer.goals]
        forged = dict(newcomer_record)
        forged["agent_id"] = eligible.agents[0].id
        forged["agent"] = eligible.agents[0].name
        eligible.intent_system.update_intent_after_activity(
            day=15, agent=eligible.agents[0], activity_record=forged
        )
        scenarios["cross_resident_goal_evidence_is_rejected"] = (
            [goal.progress for goal in newcomer.goals] == progress_before
        )
        scenarios["economy_conservation_and_reconstruction_hold"] = (
            eligible.economy.conservation_holds()
            and eligible.economy.ledger_reconstructs_balances()
        )
        scenarios["material_conservation_and_provenance_hold"] = (
            eligible.materials.material_conservation_holds()
            and eligible.materials.provenance_reconciles()
        )
        scenarios["commitment_and_plan_invariants_remain_valid"] = (
            all(eligible.commitment_system.validate_invariants().values())
            and all(eligible.plan_system.validate_invariants().values())
        )
        scenarios["crime_justice_and_memory_validators_remain_valid"] = (
            eligible.crime.evidence_is_valid()
            and eligible.justice.history_is_valid()
            and all(eligible.outcome_memory.validate().values())
        )

        with redirect_stdout(StringIO()):
            v3 = evaluate_v3_freeze()
            v4 = evaluate_v4_freeze()
        scenarios["v3_and_v4_freeze_behavior_remains_valid"] = (
            v3["passed"] and v4["passed"]
        )

        horizon, first_signature = _long_horizon(root, "horizon-one")
        second_horizon, second_signature = _long_horizon(root, "horizon-two")
        horizon_record = horizon.town_growth.migration_records[0]
        scenarios["ninety_day_horizon_reaches_five_persistent_residents"] = (
            len(horizon.agents) == 5
            and horizon_record.status == "activated"
            and horizon_record.activation_day == 14
        )
        scenarios["ninety_day_horizon_has_no_duplicate_migration"] = (
            len(horizon.town_growth.migration_records) == 1
            and len(first_signature["settlements"]) == 1
        )
        scenarios["ninety_day_newcomer_participates_ordinary_runtime"] = (
            first_signature["newcomer_activity_count"] > 0
            and any(
                item.agent_id == horizon_record.agent_id
                for item in horizon.plan_system.goal_plans
            )
        )
        scenarios["repeated_seeded_evaluator_runs_are_equivalent"] = (
            first_signature == second_signature
        )

        invariants = {
            "population_identity_unique": len({item.id for item in horizon.agents})
            == len(horizon.agents),
            "population_names_unique": len({item.name for item in horizon.agents})
            == len(horizon.agents),
            "one_account_per_resident": all(
                horizon.economy.account_for_agent(item.id) for item in horizon.agents
            ),
            "one_inventory_per_resident": all(
                horizon.materials.inventory_for_agent(item.id)
                for item in horizon.agents
            ),
            "settlement_conserves_currency": horizon.economy.conservation_holds(),
            "ledger_reconstructs_balances": horizon.economy.ledger_reconstructs_balances(),
            "materials_conserved": horizon.materials.material_conservation_holds(),
            "material_provenance_valid": horizon.materials.provenance_reconciles(),
            "commitment_invariants_hold": all(
                horizon.commitment_system.validate_invariants().values()
            ),
            "plan_invariants_hold": all(
                horizon.plan_system.validate_invariants().values()
            ),
            "crime_history_valid": horizon.crime.evidence_is_valid(),
            "justice_history_valid": horizon.justice.history_is_valid(),
            "outcome_memory_provenance_valid": all(
                horizon.outcome_memory.validate().values()
            ),
            "growth_history_bounded": (
                len(horizon.town_growth.review_history)
                <= horizon.town_growth.REVIEW_HISTORY_LIMIT
                and len(horizon.town_growth.public_history)
                <= horizon.town_growth.PUBLIC_HISTORY_LIMIT
            ),
        }

        diagnostics["ninety_day_signature"] = first_signature
        diagnostics["failed_scenarios"] = [
            name for name, passed in scenarios.items() if not passed
        ]
        diagnostics["failed_invariants"] = [
            name for name, passed in invariants.items() if not passed
        ]

    return {
        "passed": all(scenarios.values()) and all(invariants.values()),
        "scenario_count": len(scenarios),
        "scenarios_passed": sum(scenarios.values()),
        "scenarios": scenarios,
        "invariant_count": len(invariants),
        "invariants_passed": sum(invariants.values()),
        "invariants": invariants,
        "diagnostics": diagnostics,
    }

