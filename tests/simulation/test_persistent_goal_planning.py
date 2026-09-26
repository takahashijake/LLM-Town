import json
from unittest.mock import patch

from src.agents.goal import Goal
from src.behavior.goal_planner import StrategyCandidate
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.reputation import ReputationBelief, ReputationEvidence


def build_engine(tmp_path):
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        llm_client=FakeLLMClient(),
        state_path=tmp_path / "state.json",
        logs_dir=tmp_path / "logs",
    )


def strong_hostility(target_name: str) -> ReputationBelief:
    return ReputationBelief(
        target_agent=target_name,
        dimension="hostility",
        evidence=[
            ReputationEvidence(
                evidence_id=f"hostile-{index}",
                value=1,
                confidence=1,
                source_type="direct_interaction",
                source_agent=target_name,
                day=2,
            )
            for index in range(3)
        ],
    )


def test_direct_reputation_evidence_supersedes_tactic_but_preserves_goal(tmp_path):
    engine = build_engine(tmp_path)
    maya, ethan = engine.agents[:2]
    goal = Goal(
        id="goal-repair-ethan",
        agent_name=maya.name,
        description=f"Repair the relationship with {ethan.name}",
        category="repair_relationship",
        priority=5,
        created_day=1,
        review_day=7,
        progress=1,
        progress_target=4,
        target_agents=[ethan.name],
    )
    maya.goals = [goal]

    engine.update_agent_intents(1)
    first = engine.agent_intents[maya.name]
    assert first.strategy == "direct_cooperation"

    maya.reputation_beliefs[ethan.name] = {
        "hostility": strong_hostility(ethan.name)
    }
    engine.update_agent_intents(2)

    replacement = engine.agent_intents[maya.name]
    assert replacement.parent_goal_id == goal.id
    assert replacement.strategy == "low_risk_chat"
    assert replacement.id != first.id
    assert first.status == "superseded"
    assert first.terminal_trigger == "reputation"
    assert goal.status == "active"
    assert goal.progress == 1
    assert goal.adaptation_count == 1


def test_unavailable_investigation_target_uses_alternate_route(tmp_path):
    engine = build_engine(tmp_path)
    maya, ethan = engine.agents[:2]
    goal = Goal(
        id="goal-investigate-supplier",
        agent_name=maya.name,
        description="Investigate the supplier issue",
        category="investigate",
        priority=5,
        created_day=1,
        review_day=7,
        progress=1,
        progress_target=3,
        target_agents=[ethan.name],
        target_locations=["library"],
    )
    maya.goals = [goal]
    engine.update_agent_intents(1)
    first = engine.agent_intents[maya.name]
    assert first.strategy == "ask_target_directly"

    engine.agents = [agent for agent in engine.agents if agent.name != ethan.name]
    engine.update_agent_intents(2)

    replacement = engine.agent_intents[maya.name]
    assert first.status == "superseded"
    assert first.terminal_trigger == "hard_constraint"
    assert replacement.strategy != "ask_target_directly"
    assert replacement.parent_goal_id == goal.id
    assert goal.status == "active"
    assert goal.progress == 1


def test_failed_intent_does_not_fail_goal_and_next_tactic_can_adapt(tmp_path):
    engine = build_engine(tmp_path)
    maya, ethan = engine.agents[:2]
    goal = Goal(
        id="goal-friendship-survives",
        agent_name=maya.name,
        description=f"Build a stronger friendship with {ethan.name}",
        category="build_friendship",
        priority=5,
        created_day=1,
        review_day=7,
        progress_target=4,
        target_agents=[ethan.name],
    )
    maya.goals = [goal]
    engine.update_agent_intents(1)
    failed = engine.agent_intents[maya.name]

    engine.update_intents_after_conversation(
        day=1,
        location_id="cafe",
        speaker=maya,
        listener=ethan,
        action="argue",
        relationship_change=-3,
        new_score=-3,
        conversation_tags=["conversation", "argue"],
    )
    engine.relationships.change_score(maya.name, ethan.name, -3)
    assert failed.status == "failed"
    assert goal.status == "active"

    engine.update_agent_intents(2)
    replacement = engine.agent_intents[maya.name]
    assert replacement.parent_goal_id == goal.id
    assert replacement.strategy != failed.strategy
    assert goal.status == "active"
    assert goal.adaptation_count == 1
    assert goal.evidence[-2]["trigger"] == "relationship"


def test_multiple_intents_accumulate_progress_and_achieve_goal(tmp_path):
    engine = build_engine(tmp_path)
    maya = engine.agents[0]
    goal = Goal(
        id="goal-records",
        agent_name=maya.name,
        description="Collect legitimate records about the supplier issue",
        category="investigate",
        priority=5,
        created_day=1,
        review_day=7,
        progress_target=3,
        target_locations=["library"],
    )
    maya.goals = [goal]

    for day in (1, 2, 3):
        engine.update_agent_intents(day)
        engine.intent_system.update_intent_after_activity(
            day=day,
            agent=maya,
            location_id="library",
            activity_name="Check supplier records",
        )

    linked = [item for item in engine.intent_history if item.parent_goal_id == goal.id]
    assert len(linked) == 2
    assert [item.progress for item in linked] == [2, 1]
    assert all(item.status == "succeeded" for item in linked)
    assert goal.progress == 3
    assert goal.status == "achieved"
    assert goal.completion_day == 3
    assert goal.current_intent_id is None

    engine.state.save(engine, 3, 22, day_complete=True)
    restored = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=True,
        llm_client=FakeLLMClient(),
        state_path=tmp_path / "state.json",
        logs_dir=tmp_path / "restored-logs",
    )
    restored_goal = restored.agents[0].get_goal(goal.id)
    assert restored_goal is not None
    assert restored_goal.status == "achieved"
    assert restored_goal.progress == 3
    assert len([item for item in restored.intent_history if item.parent_goal_id == goal.id]) == 2


def test_legacy_string_goals_load_as_stable_structured_goals(tmp_path):
    engine = build_engine(tmp_path)
    maya = engine.agents[0]
    assert isinstance(maya.goals[0], Goal)
    assert maya.goals[0] == "learn town secrets"

    engine.state.save(engine, 1, 8)
    saved = engine.state.load()
    assert saved["agents"][0]["goals"][0] == "learn town secrets"
    assert saved["agents"][0]["structured_goals"][0]["category"] == "investigate"

    restored = engine.persistence.load_agents_from_state(saved)[0]
    assert isinstance(restored.goals[0], Goal)
    assert restored.goals[0].id == maya.goals[0].id


def test_weak_hearsay_does_not_cause_daily_planner_churn(tmp_path):
    engine = build_engine(tmp_path)
    maya, ethan = engine.agents[:2]
    goal = Goal(
        id="goal-stable-friendship",
        agent_name=maya.name,
        description=f"Build friendship with {ethan.name}",
        category="build_friendship",
        priority=5,
        created_day=1,
        review_day=7,
        target_agents=[ethan.name],
        progress_target=4,
    )
    maya.goals = [goal]
    engine.update_agent_intents(1)
    first = engine.agent_intents[maya.name]
    maya.reputation_beliefs[ethan.name] = {
        "hostility": ReputationBelief(
            target_agent=ethan.name,
            dimension="hostility",
            evidence=[ReputationEvidence(
                evidence_id="weak-rumor",
                value=1,
                confidence=0.35,
                source_type="hearsay",
                source_agent="Carlos",
                day=2,
            )],
        )
    }

    engine.update_agent_intents(2)
    engine.update_agent_intents(3)

    assert engine.agent_intents[maya.name] is first
    assert goal.adaptation_count == 0
    assert not engine.intent_history


def test_goal_becomes_blocked_only_when_no_feasible_route_exists(tmp_path):
    engine = build_engine(tmp_path)
    maya = engine.agents[0]
    goal = Goal(
        id="goal-missing-person",
        agent_name=maya.name,
        description="Repair the relationship with a departed resident",
        category="repair_relationship",
        priority=5,
        created_day=1,
        review_day=2,
        target_agents=["Departed Resident"],
    )
    maya.goals = [goal]

    engine.update_agent_intents(1)

    assert goal.status == "blocked"
    assert all(
        intent.parent_goal_id != goal.id
        for intent in engine.agent_intents.values()
    )
    assert goal.evidence[-1]["type"] == "blocked"
    assert engine.plan_system.goal_planning_records == [{
        "source_goal_id": goal.id,
        "agent_id": maya.id,
        "day": 1,
        "eligible": False,
        "reason": "no_feasible_strategy",
    }]


def test_repair_progress_cannot_complete_while_relationship_is_still_negative(tmp_path):
    engine = build_engine(tmp_path)
    maya, ethan = engine.agents[:2]
    engine.relationships.change_score(maya.name, ethan.name, -3)
    goal = Goal(
        id="goal-not-repaired-yet",
        agent_name=maya.name,
        description=f"Repair the relationship with {ethan.name}",
        category="repair_relationship",
        priority=5,
        created_day=1,
        review_day=7,
        progress=3,
        progress_target=3,
        target_agents=[ethan.name],
    )

    complete, _reason = engine.goal_planner.goal_is_complete(
        goal, maya, engine
    )

    assert complete is False


def test_successor_intent_continues_strategy_after_expiration(tmp_path):
    engine = build_engine(tmp_path)
    maya = engine.agents[0]
    goal = Goal(
        id="goal-multi-day", agent_name=maya.name,
        description="Build useful knowledge about town activity",
        category="increase_knowledge", priority=5, created_day=1,
        review_day=7, progress_target=4, target_locations=["library"],
    )
    maya.goals = [goal]
    engine.update_agent_intents(1)
    first = engine.agent_intents[maya.name]
    plan = engine.plan_system.get_goal_plan(goal.id)
    first.expires_day = 1

    engine.update_agent_intents(2)
    successor = engine.agent_intents[maya.name]

    assert first.status == "expired"
    assert successor.id != first.id
    assert successor.strategy == first.strategy == plan.strategy_name
    assert successor.source_goal_plan_id == first.source_goal_plan_id == plan.id
    assert successor.source_goal_plan_revision == plan.revision == 0


def test_paused_goal_terminalizes_tactic_and_plan_does_not_execute(tmp_path):
    engine = build_engine(tmp_path)
    maya = engine.agents[0]
    goal = Goal(
        id="goal-paused", agent_name=maya.name,
        description="Learn later", category="increase_knowledge",
        priority=5, created_day=1, review_day=7,
        target_locations=["library"],
    )
    maya.goals = [goal]
    engine.update_agent_intents(1)
    intent = engine.agent_intents[maya.name]
    plan = engine.plan_system.get_goal_plan(goal.id)
    goal.status = "paused"

    engine.update_agent_intents(2)

    assert intent.status == "superseded"
    assert intent.terminal_trigger == "goal_paused"
    assert maya.name not in engine.agent_intents
    assert plan.status == "paused"


def test_authoritative_activity_evidence_is_mirrored_once_and_completes_plan(tmp_path):
    engine = build_engine(tmp_path)
    maya = engine.agents[0]
    goal = Goal(
        id="goal-evidence", agent_name=maya.name,
        description="Learn at the library", category="increase_knowledge",
        priority=5, created_day=1, review_day=7, progress_target=1,
        target_locations=["library"],
    )
    maya.goals = [goal]
    engine.update_agent_intents(1)
    intent = engine.agent_intents[maya.name]
    plan = engine.plan_system.get_goal_plan(goal.id)

    engine.intent_system.update_intent_after_activity(
        day=1, agent=maya, location_id="library",
        activity_name="Inspect town records",
    )
    before = (goal.progress, list(plan.processed_evidence_keys),
              list(plan.evidence_records))
    engine.intent_system.agent_intents[maya.name] = intent
    intent.status = "active"
    engine.intent_system.update_intent_after_activity(
        day=1, agent=maya, location_id="library",
        activity_name="Inspect town records",
    )

    assert (goal.progress, plan.processed_evidence_keys,
            plan.evidence_records) == before
    assert goal.status == "achieved"
    assert plan.status == "completed"
    assert plan.evidence_records[0]["intent_id"] == intent.id


def test_plan_cannot_accept_unproven_social_text_but_existing_path_can(tmp_path):
    engine = build_engine(tmp_path)
    maya, ethan = engine.agents[:2]
    goal = Goal(
        id="goal-social-proof", agent_name=maya.name,
        description=f"Build friendship with {ethan.name}",
        category="build_friendship", priority=5, created_day=1,
        review_day=7, progress_target=4, target_agents=[ethan.name],
    )
    maya.goals = [goal]
    engine.update_agent_intents(1)
    intent = engine.agent_intents[maya.name]
    plan = engine.plan_system.get_goal_plan(goal.id)

    accepted = engine.plan_system.observe_goal_evidence(
        goal, evidence_key="model-said-we-cooperated", day=1,
        intent_id=intent.id, evidence_type="social_action",
        details={"dialogue": "We are friends now."},
    )
    assert accepted is False
    assert goal.progress == 0 and plan.evidence_records == []

    engine.update_intents_after_conversation(
        day=1, location_id="cafe", speaker=maya, listener=ethan,
        action="cooperate", relationship_change=1, new_score=1,
        conversation_tags=["cooperate"],
        evidence_key="conversation:authoritative:turn:0",
    )
    assert goal.progress == 1
    assert plan.processed_evidence_keys == ["conversation:authoritative:turn:0"]


def test_goal_plan_adaptation_history_and_budget_are_bounded(tmp_path):
    engine = build_engine(tmp_path)
    maya = engine.agents[0]
    goal = Goal(
        id="goal-adaptation-budget", agent_name=maya.name,
        description="Learn at the library", category="increase_knowledge",
        priority=5, created_day=1, review_day=7, progress=1,
        target_locations=["library"],
    )
    maya.goals = [goal]
    plan = engine.plan_system.ensure_goal_plan(
        goal, maya, engine, engine.goal_planner, 1,
    )
    alternatives = ["observe_relevant_activity", "seek_information_at_location"]
    for day in (2, 3, 4):
        candidate = StrategyCandidate(
            alternatives[day % 2], "investigate", 4.0,
            target_location="library", score=4.0,
        )
        assert engine.plan_system.adapt_goal_plan(
            plan, candidate, day=day, trigger="hard_constraint",
            preserved_progress=goal.progress, goal_planner=engine.goal_planner,
        )
    rejected = engine.plan_system.adapt_goal_plan(
        plan,
        StrategyCandidate(
            "seek_information_at_location", "investigate", 4.0,
            target_location="library", score=4.0,
        ),
        day=5, trigger="hard_constraint", preserved_progress=goal.progress,
        goal_planner=engine.goal_planner,
    )

    assert rejected is False
    assert plan.status == "blocked"
    assert plan.terminal_reason == "adaptation_budget_exhausted"
    assert plan.revision == engine.plan_system.MAX_GOAL_ADAPTATIONS
    assert all(row["preserved_progress"] == 1
               for row in plan.transitions if row["type"] == "adapted")


def test_unsupported_required_action_fails_closed(tmp_path):
    engine = build_engine(tmp_path)
    maya = engine.agents[0]
    goal = Goal(
        id="goal-unsupported-action", agent_name=maya.name,
        description="Socialize", category="socialize", priority=5,
        created_day=1, review_day=7, target_locations=["cafe"],
    )
    maya.goals = [goal]
    plan = engine.plan_system.ensure_goal_plan(
        goal, maya, engine, engine.goal_planner, 1,
    )
    candidate = StrategyCandidate(
        "low_risk_chat", "socialize", 4.0,
        required_action="invent_authoritative_action", score=4.0,
    )

    assert engine.plan_system.adapt_goal_plan(
        plan, candidate, day=2, trigger="hard_constraint",
        preserved_progress=0, goal_planner=engine.goal_planner,
    ) is False
    assert plan.status == "blocked"
    assert plan.no_plan_reason == "unsupported_required_action"


def test_goal_plan_save_resume_preserves_progress_and_private_mechanics(tmp_path):
    engine = build_engine(tmp_path)
    maya = engine.agents[0]
    goal = Goal(
        id="goal-resume", agent_name=maya.name,
        description="Learn across days", category="increase_knowledge",
        priority=5, created_day=1, review_day=7, progress_target=3,
        target_locations=["library"],
    )
    maya.goals = [goal]
    engine.update_agent_intents(1)
    engine.intent_system.update_intent_after_activity(
        day=1, agent=maya, location_id="library",
        activity_name="Inspect records",
    )
    expected = engine.plan_system.to_dict()
    plan_id = engine.plan_system.get_goal_plan(goal.id).id
    other_context = engine.prepare_conversation_context(
        "cafe", engine.agents[1], maya, 1,
    )["context"]
    assert plan_id not in json.dumps(other_context)

    engine.state.save(engine, 1, 8)
    restored = SimulationEngine(
        agents_path="data/agents.json", locations_path="data/locations.json",
        load_state=True, llm_client=FakeLLMClient(),
        state_path=tmp_path / "state.json", logs_dir=tmp_path / "restored-logs",
    )
    assert restored.plan_system.to_dict() == expected
    assert restored.agents[0].get_goal(goal.id).progress == 1


def test_due_commitment_retains_priority_when_goal_plan_exists(tmp_path):
    engine = build_engine(tmp_path)
    engine.update_agent_intents(1)
    item = engine.commitment_system.create(
        proposer_id="agent_002", counterpart_id="agent_001",
        commitment_type="meet", day=1, due_day=1,
        metadata={"location": "cafe"}, status="proposed",
    )
    engine.commitment_system.transition(item.id, "accepted", day=1, reason="accepted")

    with patch("src.behavior.planner.random.random", return_value=0.0):
        engine.activity_system.run_agent_activities(
            [engine.agents[0]], [place.id for place in engine.locations],
            1, 8, None, engine.agent_intents,
        )

    assert engine.plan_system.goal_plans
    assert engine.plan_system.plans
    assert engine.activity_records[-1]["source_commitment_id"] == item.id
    assert engine.commitment_system.get(item.id).status == "fulfilled"
