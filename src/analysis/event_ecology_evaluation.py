"""Deterministic V5 Phase 3 dynamic-event ecology acceptance evaluation."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.agents.goal import Goal
from src.agents.intent import AgentIntent
from src.behavior.goal_planner import StrategyCandidate
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.town.daily_event import DailyEvent


def _engine(root: Path, name: str, *, load: bool = False) -> SimulationEngine:
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs", simulation_seed=11,
    )


def _run_silently(engine: SimulationEngine, days: int) -> None:
    with redirect_stdout(StringIO()):
        engine.run(days, [8])


def _long_horizon(root: Path, name: str) -> tuple[SimulationEngine, dict]:
    caller_state = random.getstate()
    random.seed(11)
    try:
        engine = _engine(root, name)
        _run_silently(engine, 60)
        engine = _engine(root, name, load=True)
        _run_silently(engine, 120)
    finally:
        random.setstate(caller_state)
    occurrences = engine.event_ecology.occurrence_history
    occurrence_days = {item.day for item in occurrences}
    attendance = [row for row in engine.activity_records
                  if row.get("source_event_occurrence_id") in {
                      item.occurrence_id for item in occurrences
                  }]
    conversations = [memory for agent in engine.agents
                     for memory in agent.memory + agent.memory_archive
                     if memory.type == "conversation"
                     and memory.location == "community_garden"
                     and memory.day in occurrence_days]
    opening_memories = [memory for agent in engine.agents
                        for memory in agent.memory + agent.memory_archive
                        if memory.event_type == "location_opened"]
    signature = {
        "resident_ids": [agent.id for agent in engine.agents],
        "migration_ids": [item.id for item in engine.town_growth.migration_records],
        "active_location_ids": [item.id for item in engine.locations],
        "location_activation_ids": [item.id for item in engine.location_growth.activation_records],
        "dynamic_event_occurrence_ids": [item.occurrence_id for item in occurrences],
        "dynamic_event_template_ids": [item.template_id for item in occurrences],
        "event_occurrence_days": [item.day for item in occurrences],
        "event_locations": [item.location_id for item in occurrences],
        "event_source_kinds": [item.source_kind for item in occurrences],
        "dynamic_event_attendance_count": len(attendance),
        "dynamic_event_conversation_count": len(conversations),
        "opening_memory_ids": sorted(memory.id for memory in opening_memories),
        "current_v4_signature": sorted(
            (plan.id, plan.status, len(plan.evidence_records))
            for plan in engine.plan_system.goal_plans
        ),
        "dynamic_event_history_size": len(occurrences),
        "dynamic_event_replay_guard_size": len(
            engine.event_ecology.processed_occurrence_ids
        ),
    }
    return engine, signature


def _bind_event_plan(engine: SimulationEngine, location: str):
    actor = engine.agents[0]
    goal = Goal(
        id=f"event-ecology-goal-{location}", agent_name=actor.name,
        description=f"Observe current activity at {location}",
        category="increase_knowledge", priority=5, created_day=40,
        review_day=47, progress_target=3, target_locations=[location],
    )
    actor.goals.append(goal)
    engine.agent_intents.pop(actor.name, None)
    engine.intent_system.agent_intents = engine.agent_intents
    candidate = StrategyCandidate(
        "observe_relevant_activity", "investigate", 5.0,
        target_location=location, score=5.0,
    )
    with patch.object(engine.goal_planner, "select_strategy", return_value=candidate):
        plan = engine.plan_system.ensure_goal_plan(
            goal, actor, engine, engine.goal_planner, 40,
        )
    intent = AgentIntent(
        id=f"intent:{goal.id}:r0", agent_name=actor.name,
        intent_type="investigate", description=goal.description,
        created_day=40, expires_day=47, priority=5,
        target_location=location, parent_goal_id=goal.id,
        source_goal_plan_id=plan.id, source_goal_plan_revision=plan.revision,
        strategy=plan.strategy_name, strategy_score=5.0,
    )
    goal.current_intent_id = intent.id
    goal.current_strategy = plan.strategy_name
    engine.agent_intents[actor.name] = intent
    engine.intent_system.agent_intents = engine.agent_intents
    engine.intent_system._engine_for_goal_check = engine
    return actor, goal, intent, plan


def _proof_record(engine, actor, *, day: int):
    intent = engine.agent_intents[actor.name]
    dependency = engine.plan_system.goal_dependency_for_agent(
        actor.id, day=day, tick=8,
        current_daily_event=engine.current_daily_event,
        goal_plan_id=intent.source_goal_plan_id,
    )
    activity = engine.activity_planner.create_intent_activity(intent, dependency)
    engine.activity_system.log_activity_event(day, 8, actor, activity)
    return engine.activity_records[-1]


def _mutated_load_rejected(root: Path, base_data: dict, name: str, mutate) -> bool:
    data = deepcopy(base_data)
    mutate(data)
    path = root / f"{name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    try:
        _engine(root, name, load=True)
    except (KeyError, TypeError, ValueError):
        return True
    return False


def evaluate_event_ecology() -> dict:
    scenarios: dict[str, bool] = {}
    diagnostics: dict[str, object] = {}
    caller_state = random.getstate()
    try:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first, first_signature = _long_horizon(root, "long-a")
            second, second_signature = _long_horizon(root, "long-b")
            diagnostics["long_horizon_signature"] = first_signature
            occurrences = first.event_ecology.occurrence_history
            occurrence_ids = [item.occurrence_id for item in occurrences]
            occurrence_days = [item.day for item in occurrences]
            history_days = [row["day"] for row in first.daily_event_history]
            scenarios.update({
                "integrated_horizon_has_configured_migrations": (
                    first_signature["migration_ids"]
                    == ["migration:0001", "migration:0002"]
                ),
                "integrated_horizon_has_configured_location_activations": (
                    first_signature["location_activation_ids"]
                    == ["location-activation:0001", "location-activation:0002"]
                ),
                "dynamic_event_occurs_after_place_use": (
                    bool(occurrences) and min(occurrence_days) > 31
                ),
                "dynamic_events_use_activated_garden": (
                    bool(occurrences)
                    and set(first_signature["event_locations"])
                    == {"community_garden"}
                ),
                "ordinary_attendance_uses_dynamic_occurrence": (
                    first_signature["dynamic_event_attendance_count"] > 0
                ),
                "ordinary_conversation_occurs_during_dynamic_event": (
                    first_signature["dynamic_event_conversation_count"] > 0
                ),
                "one_authoritative_event_per_day": (
                    len(history_days) == len(set(history_days)) == 180
                ),
                "base_events_continue_after_dynamic_eligibility": any(
                    row["source_kind"] == "base"
                    and row["day"] > min(occurrence_days)
                    for row in first.daily_event_history
                ),
                "dynamic_events_do_not_replace_base_events": (
                    sum(row["source_kind"] == "base"
                        for row in first.daily_event_history)
                    > len(occurrences)
                ),
                "occurrence_identity_includes_day_template_location": all(
                    item.occurrence_id
                    == f"daily-event:{item.day}:{item.template_id}:{item.location_id}"
                    for item in occurrences
                ),
                "same_template_recurrences_have_distinct_identity": all(
                    len({item.occurrence_id for item in occurrences
                         if item.template_id == template_id})
                    == sum(item.template_id == template_id for item in occurrences)
                    for template_id in {item.template_id for item in occurrences}
                ),
                "seeded_save_resume_runs_match": first_signature == second_signature,
            })

            # Stop on the first organic dynamic-event day and persist a partial day.
            partial = _engine(root, "partial")
            random.seed(11)
            _run_silently(partial, 39)
            partial.simulation_loop.start_new_day(partial, 40)
            dynamic = partial.current_daily_event
            scenarios["controlled_day_selects_dynamic_event"] = (
                dynamic.source_kind == "dynamic"
                and dynamic.location_id == "community_garden"
            )
            history_size = len(partial.daily_event_history)
            partial.simulation_loop.start_new_day(partial, 40)
            scenarios["same_day_start_replay_is_idempotent"] = (
                partial.current_daily_event.occurrence_id == dynamic.occurrence_id
                and len(partial.daily_event_history) == history_size
                and len(partial.event_ecology.occurrence_history) == 1
            )
            before_boundaries = {
                "economy": partial.economy.to_dict(),
                "materials": partial.materials.to_dict(),
                "crime": partial.crime.to_dict(),
                "justice": partial.justice.to_dict(),
                "commitments": partial.commitment_system.to_dict(),
                "locations": partial.location_growth.to_dict(),
            }
            partial.state.save(partial, 40, 8, day_complete=False)
            resumed = _engine(root, "partial", load=True)
            scenarios["partial_day_resume_preserves_exact_occurrence"] = (
                resumed.current_daily_event.occurrence_id == dynamic.occurrence_id
                and len(resumed.event_ecology.occurrence_history) == 1
            )
            after_boundaries = {
                "economy": resumed.economy.to_dict(),
                "materials": resumed.materials.to_dict(),
                "crime": resumed.crime.to_dict(),
                "justice": resumed.justice.to_dict(),
                "commitments": resumed.commitment_system.to_dict(),
                "locations": resumed.location_growth.to_dict(),
            }
            scenarios["event_selection_grants_no_economic_legal_or_growth_authority"] = (
                before_boundaries == after_boundaries
            )

            actor, goal, _intent, plan = _bind_event_plan(resumed, "community_garden")
            opportunity = resumed.plan_system.goal_dependency_for_agent(
                actor.id, day=40, tick=8, current_daily_event=resumed.current_daily_event,
                goal_plan_id=plan.id,
            )
            scenarios["dynamic_event_satisfies_exact_v4_target"] = (
                opportunity.status == "satisfied"
                and opportunity.authority_reference == dynamic.occurrence_id
                and goal.progress == 0
            )
            proof = _proof_record(resumed, actor, day=40)
            resumed.intent_system.update_intent_after_activity(
                day=40, agent=actor, activity_record=proof,
            )
            scenarios["ordinary_strategy_activity_advances_once"] = goal.progress == 1

            wrong = _engine(root, "partial", load=True)
            wrong_actor, wrong_goal, _wrong_intent, wrong_plan = _bind_event_plan(
                wrong, "library"
            )
            wrong_opportunity = wrong.plan_system.goal_dependency_for_agent(
                wrong_actor.id, day=40, tick=8,
                current_daily_event=wrong.current_daily_event,
                goal_plan_id=wrong_plan.id,
            )
            scenarios["dynamic_event_cannot_satisfy_wrong_v4_target"] = (
                wrong_opportunity.status == "waiting" and wrong_goal.progress == 0
            )

            stale = _engine(root, "partial", load=True)
            stale_actor, stale_goal, _stale_intent, _stale_plan = _bind_event_plan(
                stale, "community_garden"
            )
            old_proof = _proof_record(stale, stale_actor, day=40)
            stale.current_daily_event = DailyEvent(
                dynamic.id, dynamic.name, dynamic.description, dynamic.location_id,
                list(dynamic.tags), dynamic.template_id,
                f"daily-event:54:{dynamic.template_id}:{dynamic.location_id}",
                54, "dynamic",
            )
            stale.intent_system.update_intent_after_activity(
                day=54, agent=stale_actor, activity_record=old_proof,
            )
            scenarios["yesterdays_occurrence_cannot_cross_credit"] = (
                stale_goal.progress == 0
            )

            saved = json.loads((root / "partial.json").read_text(encoding="utf-8"))
            scenarios.update({
                "unknown_event_schema_fails_closed": _mutated_load_rejected(
                    root, saved, "bad-schema",
                    lambda data: data["event_ecology"].update(schema_version=999),
                ),
                "unknown_event_template_fails_closed": _mutated_load_rejected(
                    root, saved, "bad-template",
                    lambda data: data["current_daily_event"].update(
                        id="unknown", template_id="unknown"
                    ),
                ),
                "unknown_event_source_fails_closed": _mutated_load_rejected(
                    root, saved, "bad-source",
                    lambda data: data["current_daily_event"].update(source_kind="model"),
                ),
                "unknown_event_tag_fails_closed": _mutated_load_rejected(
                    root, saved, "bad-tag",
                    lambda data: data["current_daily_event"].update(tags=["market"]),
                ),
                "inactive_event_location_fails_closed": _mutated_load_rejected(
                    root, saved, "bad-location",
                    lambda data: data["current_daily_event"].update(
                        location_id="civic_pavilion"
                    ),
                ),
                "wrong_occurrence_day_fails_closed": _mutated_load_rejected(
                    root, saved, "bad-day",
                    lambda data: data["current_daily_event"].update(day=39),
                ),
                "duplicate_occurrence_fails_closed": _mutated_load_rejected(
                    root, saved, "duplicate",
                    lambda data: data["event_ecology"]["occurrence_history"].append(
                        deepcopy(data["event_ecology"]["occurrence_history"][0])
                    ),
                ),
                "missing_occurrence_provenance_fails_closed": _mutated_load_rejected(
                    root, saved, "missing-proof",
                    lambda data: data["event_ecology"].update(
                        occurrence_history=[], processed_occurrence_ids=[]
                    ),
                ),
            })

            event_checks = first.event_ecology.validate(
                locations=first.locations,
                location_growth=first.location_growth,
                activity_records=first.activity_records,
            )
            invariants = {
                **event_checks,
                **first.location_growth.validate(first.locations, first.agents),
                "migration_invariants_hold": all(
                    record.status != "activated"
                    or any(agent.id == record.agent_id for agent in first.agents)
                    for record in first.town_growth.migration_records
                ),
                "event_occurrence_ids_unique": (
                    len(occurrence_ids) == len(set(occurrence_ids))
                ),
                "event_occurrence_days_match_identity": all(
                    item.occurrence_id.startswith(f"daily-event:{item.day}:")
                    for item in occurrences
                ),
                "event_sources_are_known": all(
                    item.source_kind == "dynamic" for item in occurrences
                ),
                "resident_current_locations_remain_valid": all(
                    agent.location_id in {item.id for item in first.locations}
                    for agent in first.agents
                ),
                "economy_conservation_holds": (
                    first.economy.conservation_holds()
                    and first.economy.ledger_reconstructs_balances()
                ),
                "material_conservation_and_provenance_hold": (
                    first.materials.material_conservation_holds()
                    and first.materials.provenance_reconciles()
                ),
                "commitment_invariants_hold": all(
                    first.commitment_system.validate_invariants().values()
                ),
                "v4_plan_invariants_hold": all(
                    first.plan_system.validate_invariants().values()
                ),
                "crime_history_valid": first.crime.evidence_is_valid(),
                "justice_history_valid": first.justice.history_is_valid(),
                "outcome_memory_provenance_valid": all(
                    first.outcome_memory.validate().values()
                ),
            }
    finally:
        random.setstate(caller_state)

    failed_scenarios = sorted(name for name, passed in scenarios.items() if not passed)
    failed_invariants = sorted(name for name, passed in invariants.items() if not passed)
    diagnostics.update({
        "failed_scenarios": failed_scenarios,
        "failed_invariants": failed_invariants,
    })
    return {
        "passed": not failed_scenarios and not failed_invariants,
        "scenario_count": len(scenarios),
        "scenarios_passed": sum(bool(value) for value in scenarios.values()),
        "invariant_count": len(invariants),
        "invariants_passed": sum(bool(value) for value in invariants.values()),
        "scenarios": scenarios,
        "invariants": invariants,
        "diagnostics": diagnostics,
    }
