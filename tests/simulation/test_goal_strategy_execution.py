"""Adversarial coverage for V4 strategy-specific execution proof."""

from unittest.mock import patch

import pytest

from src.agents.goal import Goal
from src.behavior.goal_planner import StrategyCandidate
from src.behavior.goal_strategy_contracts import strategy_contract
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.town.daily_event import DailyEvent


def engine_at(tmp_path, name="state", load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=tmp_path / f"{name}.json",
        logs_dir=tmp_path / f"{name}-logs",
    )


def bind_strategy(engine, strategy, *, target=None, location=None, goal_id=None):
    actor = engine.agents[0]
    contract = strategy_contract(strategy)
    category = (
        "repair_relationship" if strategy in {
            "direct_cooperation", "apologize_directly", "offer_help",
        } else "investigate" if strategy.startswith("ask_")
        or strategy in {"seek_information_at_location", "observe_relevant_activity"}
        else "socialize"
    )
    goal = Goal(
        id=goal_id or f"goal-{strategy}", agent_name=actor.name,
        description=f"Exercise {strategy}", category=category, priority=5,
        created_day=1, review_day=7, progress_target=5,
        target_agents=[target] if target else [],
        target_locations=[location] if location else [],
    )
    actor.goals = [goal]
    candidate = StrategyCandidate(
        strategy, category if category != "socialize" else "socialize", 5.0,
        target_agent=target, target_location=location,
        required_action=contract.required_social_action, score=5.0,
    )
    with patch.object(engine.goal_planner, "select_strategy", return_value=candidate):
        engine.update_agent_intents(1)
    return actor, goal, engine.agent_intents[actor.name], engine.plan_system.get_goal_plan(goal.id)


def social_proof(engine, actor, listener, action, key):
    return engine.update_intents_after_conversation(
        day=1, location_id="cafe", speaker=actor, listener=listener,
        action=action, relationship_change=1, new_score=1,
        conversation_tags=[action], evidence_key=key,
    )


def activity_record(engine, actor, day=1, hour=8):
    intent = engine.agent_intents[actor.name]
    dependency = engine.plan_system.goal_dependency_for_agent(
        actor.id, day=day, tick=hour,
        current_daily_event=engine.current_daily_event,
        goal_plan_id=intent.source_goal_plan_id,
    )
    activity = engine.activity_planner.create_intent_activity(intent, dependency)
    engine.activity_system.log_activity_event(day, hour, actor, activity)
    return engine.activity_records[-1]


@pytest.mark.parametrize(("strategy", "action", "wrong_action"), (
    ("direct_cooperation", "cooperate", "chat"),
    ("apologize_directly", "apologize", "offer_help"),
    ("offer_help", "offer_help", "cooperate"),
))
def test_social_strategy_requires_exact_action(
    tmp_path, strategy, action, wrong_action,
):
    engine = engine_at(tmp_path, strategy)
    actor, target = engine.agents[:2]
    actor, goal, _intent, plan = bind_strategy(
        engine, strategy, target=target.name,
    )

    social_proof(engine, actor, target, wrong_action, f"wrong-{strategy}")
    assert goal.progress == 0 and not plan.evidence_records
    social_proof(engine, actor, target, action, f"exact-{strategy}")
    assert goal.progress == 1
    assert plan.evidence_records[0]["action"] == action


def test_low_risk_chat_requires_chat_and_has_explicit_generic_target_rule(tmp_path):
    engine = engine_at(tmp_path)
    actor, listener = engine.agents[:2]
    actor, goal, _intent, plan = bind_strategy(engine, "low_risk_chat")

    social_proof(engine, actor, listener, "compliment", "not-chat")
    assert goal.progress == 0
    social_proof(engine, actor, listener, "chat", "chat")
    assert goal.progress == 1 and plan.target_agent is None


@pytest.mark.parametrize("strategy", (
    "ask_target_directly", "ask_informed_agent", "ask_reliable_partner",
))
def test_ask_strategy_requires_exact_selected_target(tmp_path, strategy):
    engine = engine_at(tmp_path, strategy)
    actor, selected, wrong = engine.agents[:3]
    actor, goal, _intent, plan = bind_strategy(
        engine, strategy, target=selected.name,
    )

    social_proof(engine, actor, wrong, "ask_for_help", "wrong-target")
    social_proof(engine, actor, selected, "share_rumor", "wrong-action")
    assert goal.progress == 0 and not plan.evidence_records
    social_proof(engine, actor, selected, "ask_for_help", "exact")
    assert goal.progress == 1
    assert plan.evidence_records[0]["target_agent"] == selected.name


@pytest.mark.parametrize("strategy", (
    "seek_information_at_location", "observe_relevant_activity",
    "direct_participation",
))
def test_location_strategy_requires_its_authoritative_activity(tmp_path, strategy):
    engine = engine_at(tmp_path, strategy)
    actor, goal, intent, plan = bind_strategy(
        engine, strategy, location="library",
    )
    if strategy in {"observe_relevant_activity", "direct_participation"}:
        engine.current_daily_event = DailyEvent(
            "book_club", "Book Club", "A real library gathering.",
            "library", ["learning", "social"],
        )
    generic = {
        "type": "activity", "day": 1, "hour": 8, "agent": actor.name,
        "activity_id": "learn", "activity_name": "Look for information",
        "location": "library", "tags": ["knowledge", "learning"],
    }
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record=generic,
    )
    assert goal.progress == 0

    record = activity_record(engine, actor)
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record=record,
    )
    assert goal.progress == 1
    assert plan.evidence_records[0]["strategy"] == strategy
    assert record["source_intent_id"] == intent.id


def test_location_proof_cannot_cross_strategy_or_source(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, _intent, plan = bind_strategy(
        engine, "observe_relevant_activity", location="library",
    )
    record = activity_record(engine, actor)
    record["activity_id"] = "goal_seek_information"
    record["source_goal_strategy"] = "seek_information_at_location"
    record["tags"] = ["goal_strategy", "seek_information"]
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record=record,
    )
    assert goal.progress == 0

    record = activity_record(engine, actor, hour=9)
    record["source_goal_id"] = "another-goal"
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record=record,
    )
    record["source_goal_id"] = goal.id
    record["source_goal_plan_id"] = "plan:goal:other:other"
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record=record,
    )
    record["source_goal_plan_id"] = plan.id
    record["agent"] = engine.agents[1].name
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record=record,
    )
    assert goal.progress == 0 and not plan.evidence_records


def test_stale_revision_activity_and_social_proof_are_rejected(tmp_path):
    engine = engine_at(tmp_path)
    actor, target = engine.agents[:2]
    actor, goal, old_intent, plan = bind_strategy(
        engine, "direct_cooperation", target=target.name,
    )
    replacement = StrategyCandidate(
        "apologize_directly", "repair_relationship", 4.0,
        target_agent=target.name, required_action="apologize", score=4.0,
    )
    assert engine.plan_system.adapt_goal_plan(
        plan, replacement, day=2, trigger="relationship", preserved_progress=0,
        goal_planner=engine.goal_planner,
    )
    social_proof(engine, actor, target, "cooperate", "delayed-r0")
    assert goal.progress == 0

    engine.intent_system.agent_intents.pop(actor.name, None)
    goal.current_intent_id = None
    engine.update_agent_intents(2)
    current = engine.agent_intents[actor.name]
    assert current.source_goal_plan_revision == 1
    social_proof(engine, actor, target, "apologize", "current-r1")
    assert goal.progress == 1
    assert plan.evidence_records[0]["source_goal_plan_revision"] == 1
    assert old_intent.id != current.id


def test_stale_revision_activity_record_is_rejected(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, _old_intent, plan = bind_strategy(
        engine, "seek_information_at_location", location="library",
    )
    stale_record = activity_record(engine, actor)
    replacement = StrategyCandidate(
        "observe_relevant_activity", "investigate", 4.0,
        target_location="library", score=4.0,
    )
    assert engine.plan_system.adapt_goal_plan(
        plan, replacement, day=2, trigger="hard_constraint",
        preserved_progress=0, goal_planner=engine.goal_planner,
    )

    engine.intent_system.update_intent_after_activity(
        day=2, agent=actor, activity_record=stale_record,
    )
    assert goal.progress == 0 and not plan.evidence_records


def test_exact_proof_replay_and_save_resume_are_idempotent(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, _intent, plan = bind_strategy(
        engine, "seek_information_at_location", location="library",
    )
    record = activity_record(engine, actor)
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record=record,
    )
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record=record,
    )
    assert goal.progress == 1 and len(plan.evidence_records) == 1

    engine.state.save(engine, 1, 8)
    resumed = engine_at(tmp_path, load=True)
    resumed_actor = resumed.agents[0]
    resumed.intent_system.update_intent_after_activity(
        day=1, agent=resumed_actor, activity_record=resumed.activity_records[-1],
    )
    resumed_goal = resumed_actor.get_goal(goal.id)
    resumed_plan = resumed.plan_system.get_goal_plan(goal.id)
    assert resumed_goal.progress == 1 and len(resumed_plan.evidence_records) == 1


def test_terminal_plan_and_generated_claim_cannot_create_proof(tmp_path):
    engine = engine_at(tmp_path)
    actor, target = engine.agents[:2]
    actor, goal, intent, plan = bind_strategy(
        engine, "direct_cooperation", target=target.name,
    )
    assert not engine.plan_system.observe_goal_evidence(
        goal, evidence_key="generated-text", day=1, intent_id=intent.id,
        evidence_type="social_action", details={"dialogue": "I cooperated."},
    )
    goal.status = "blocked"
    engine.plan_system.synchronize_goal_plan(goal, day=2)
    social_proof(engine, actor, target, "cooperate", "after-terminal")
    assert goal.progress == 0 and plan.status == "blocked"
    assert not plan.evidence_records


def test_due_commitment_preemption_does_not_cross_credit_goal_strategy(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, _intent, plan = bind_strategy(
        engine, "direct_participation", location="cafe",
    )
    item = engine.commitment_system.create(
        proposer_id="agent_002", counterpart_id=actor.id,
        commitment_type="meet", day=1, due_day=1,
        metadata={"location": "cafe"}, status="proposed",
    )
    engine.commitment_system.transition(item.id, "accepted", day=1, reason="accepted")
    with patch("src.behavior.planner.random.random", return_value=0.0):
        engine.run_agent_activities(1, 8)
    assert engine.activity_records[-4]["source_commitment_id"] == item.id
    assert goal.progress == 0 and not plan.evidence_records
    assert not goal.processed_evidence_keys
