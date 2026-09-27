"""Focused V4 Phase 3 dependency and authority-boundary coverage."""

from unittest.mock import patch

import pytest

from src.agents.goal import Goal
from src.behavior.goal_planner import StrategyCandidate
from src.behavior.goal_strategy_contracts import (
    DAILY_EVENT_AT_TARGET,
    GoalStrategyDependencyContract,
    strategy_contract,
)
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.plans import GoalDependencyState
from src.town.daily_event import DailyEvent


def engine_at(tmp_path, name="state", load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=tmp_path / f"{name}.json",
        logs_dir=tmp_path / f"{name}-logs",
    )


def bind(engine, strategy="observe_relevant_activity", location="library"):
    actor = engine.agents[0]
    goal = Goal(
        id=f"goal-{strategy}", agent_name=actor.name,
        description=f"Exercise {strategy}", category="increase_knowledge",
        priority=5, created_day=1, review_day=7, progress_target=3,
        target_locations=[location],
    )
    actor.goals = [goal]
    candidate = StrategyCandidate(
        strategy, "investigate", 5.0, target_location=location, score=5.0,
    )
    with patch.object(engine.goal_planner, "select_strategy", return_value=candidate):
        engine.update_agent_intents(1)
    return actor, goal, engine.agent_intents[actor.name], engine.plan_system.get_goal_plan(goal.id)


def proof_record(engine, actor, *, day=1, hour=8):
    intent = engine.agent_intents[actor.name]
    dependency = engine.plan_system.goal_dependency_for_agent(
        actor.id, day=day, tick=hour,
        current_daily_event=engine.current_daily_event,
        goal_plan_id=intent.source_goal_plan_id,
    )
    activity = engine.activity_planner.create_intent_activity(intent, dependency)
    engine.activity_system.log_activity_event(day, hour, actor, activity)
    return engine.activity_records[-1]


def test_dependency_contract_is_closed_and_inspectable():
    contract = strategy_contract("observe_relevant_activity")
    assert contract.dependency.kind == DAILY_EVENT_AT_TARGET
    assert contract.dependency.authority == "current_daily_event"
    assert contract.dependency.preparation_activity_id is None
    with pytest.raises(ValueError, match="unknown goal strategy dependency kind"):
        GoalStrategyDependencyContract("model_claim", "dialogue")
    with pytest.raises(ValueError, match="unknown goal strategy dependency kind"):
        GoalDependencyState("invented", "library", 0)


def test_absent_or_wrong_location_event_cannot_execute_strategy(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, plan = bind(engine)
    assert plan.dependency.status == "waiting"

    record = proof_record(engine, actor)
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record=record,
    )
    assert goal.progress == 0

    engine.current_daily_event = DailyEvent(
        "market_day", "Market Day", "A market opportunity.", "market", ["market"],
    )
    record = proof_record(engine, actor, hour=9)
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record=record,
    )
    assert goal.progress == 0
    assert plan.dependency.status == "waiting"
    assert intent.progress == 0


def test_authoritative_event_unlocks_but_does_not_itself_advance(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, _intent, plan = bind(engine)
    engine.current_daily_event = DailyEvent(
        "book_club", "Book Club", "A real gathering.", "library", ["learning"],
    )
    opportunity = engine.plan_system.goal_dependency_for_agent(
        actor.id, day=1, tick=8, current_daily_event=engine.current_daily_event,
        goal_plan_id=plan.id,
    )
    assert opportunity.status == "satisfied"
    assert goal.progress == 0

    record = proof_record(engine, actor)
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record=record,
    )
    assert goal.progress == 1
    assert len(plan.evidence_records) == 1
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record=record,
    )
    assert goal.progress == 1


def test_forged_text_and_stale_event_reference_fail_closed(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, plan = bind(engine)
    engine.current_daily_event = DailyEvent(
        "book_club", "Book Club", "A real gathering.", "library", ["learning"],
    )
    record = proof_record(engine, actor)
    record["reason"] = "I attended and observed it yesterday."
    record["source_goal_dependency_authority_ref"] = "invented_event"
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record=record,
    )
    accepted = engine.plan_system.observe_goal_evidence(
        goal, evidence_key="dialogue-claim", day=1, intent_id=intent.id,
        evidence_type="strategy_activity",
        details={"dialogue": "There is something at the library."},
    )
    assert not accepted and goal.progress == 0 and not plan.evidence_records


def test_waiting_dependency_persists_and_reconstructs_from_authority(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, _intent, plan = bind(engine)
    engine.plan_system.goal_dependency_for_agent(
        actor.id, day=1, tick=8, current_daily_event=None, goal_plan_id=plan.id,
    )
    engine.state.save(engine, 1, 8)
    resumed = engine_at(tmp_path, load=True)
    restored = resumed.plan_system.get_goal_plan(goal.id)
    assert restored.dependency.status == "waiting"
    assert restored.dependency.revision == restored.revision == 0
    resumed.current_daily_event = DailyEvent(
        "book_club", "Book Club", "A real gathering.", "library", ["learning"],
    )
    state = resumed.plan_system.refresh_goal_dependency(
        restored, day=1, tick=9,
        current_daily_event=resumed.current_daily_event,
    )
    assert state.status == "satisfied" and state.authority_reference == "book_club"
    assert resumed.agents[0].get_goal(goal.id).progress == 0


def test_adaptation_rebinds_dependency_and_rejects_old_proof(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, _intent, plan = bind(engine)
    engine.current_daily_event = DailyEvent(
        "book_club", "Book Club", "A real gathering.", "library", ["learning"],
    )
    old_record = proof_record(engine, actor)
    replacement = StrategyCandidate(
        "direct_participation", "investigate", 4.0,
        target_location="library", score=4.0,
    )
    assert engine.plan_system.adapt_goal_plan(
        plan, replacement, day=2, trigger="opportunity",
        preserved_progress=0, goal_planner=engine.goal_planner,
    )
    assert plan.revision == plan.dependency.revision == 1
    assert plan.dependency.status == "waiting"
    engine.intent_system.update_intent_after_activity(
        day=2, agent=actor, activity_record=old_record,
    )
    assert goal.progress == 0 and not plan.evidence_records


def test_due_commitment_can_preempt_satisfied_goal_dependency(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, plan = bind(engine)
    engine.current_daily_event = DailyEvent(
        "book_club", "Book Club", "A real gathering.", "library", ["learning"],
    )
    commitment = engine.commitment_system.create(
        proposer_id="agent_002", counterpart_id=actor.id,
        commitment_type="meet", day=1, due_day=1,
        metadata={"location": "cafe"}, status="proposed",
    )
    engine.commitment_system.transition(commitment.id, "accepted", day=1, reason="accepted")
    with patch("src.behavior.planner.random.random", return_value=0.5):
        engine.run_agent_activities(1, 8)
    record = next(item for item in engine.activity_records if item["agent"] == actor.name)
    assert record["source_commitment_id"] == commitment.id
    assert goal.progress == 0 and plan.active
    assert plan.dependency.status == "satisfied"
    assert intent.source_goal_plan_id == plan.id


def test_schema_three_load_does_not_fabricate_dependency(tmp_path):
    engine = engine_at(tmp_path)
    _actor, goal, _intent, _plan = bind(engine)
    old = engine.plan_system.to_dict()
    old["schema_version"] = 3
    for item in old["goal_plans"]:
        item.pop("dependency", None)
    restored = type(engine.plan_system).from_dict(
        old, commitment_system=engine.commitment_system,
        agents=engine.agents, outcome_memory=engine.outcome_memory,
    )
    assert restored.get_goal_plan(goal.id).dependency is None


def test_dependency_history_is_bounded(tmp_path):
    engine = engine_at(tmp_path)
    actor, _goal, _intent, plan = bind(engine)
    for index in range(50):
        event = (DailyEvent(f"e{index}", "Event", "Real.", "library", [])
                 if index % 2 else None)
        engine.plan_system.goal_dependency_for_agent(
            actor.id, day=index + 1, tick=8, current_daily_event=event,
            goal_plan_id=plan.id,
        )
    assert len(plan.dependency.transitions) == 20
