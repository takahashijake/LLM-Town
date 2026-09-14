from src.agents.goal import Goal
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
