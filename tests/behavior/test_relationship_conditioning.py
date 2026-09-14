from src.agents.goal import Goal
from src.simulation.engine import SimulationEngine
from src.llm.client import FakeLLMClient


def build_engine(tmp_path):
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        llm_client=FakeLLMClient(),
        state_path=tmp_path / "state.json",
        logs_dir=tmp_path / "logs",
    )


def knowledge_goal(agent_name: str) -> Goal:
    return Goal(
        id=f"goal-{agent_name}", agent_name=agent_name,
        description="Obtain useful information", category="increase_knowledge",
        priority=5, created_day=1, review_day=7, progress_target=3,
        target_locations=["library"],
    )


def test_private_history_changes_strategy_and_help_target(tmp_path):
    neutral_engine = build_engine(tmp_path / "neutral")
    seeker = neutral_engine.agents[0]
    neutral = neutral_engine.goal_planner.select_strategy(
        knowledge_goal(seeker.name), seeker, neutral_engine
    )

    history_engine = build_engine(tmp_path / "history")
    seeker, helper, hostile = history_engine.agents[:3]
    for day in (1, 2):
        history_engine.relationship_updater.apply_structured_relationship_update(
            day=day, hour=8, speaker=helper, listener=seeker,
            action="offer_help", outcome="completed",
        )
        history_engine.relationship_updater.apply_structured_relationship_update(
            day=day, hour=12, speaker=hostile, listener=seeker,
            action="argue", outcome="completed",
        )
    conditioned = history_engine.goal_planner.select_strategy(
        knowledge_goal(seeker.name), seeker, history_engine
    )

    assert neutral.name == "seek_information_at_location"
    assert conditioned.name == "ask_informed_agent"
    assert conditioned.target_agent == helper.name
    assert conditioned.relationship_influenced is True
    assert "supports" in conditioned.relationship_reason
    assert conditioned.relevant_social_memories


def test_trusted_helper_gets_more_help_seeking_weight_than_hostile_peer(tmp_path):
    engine = build_engine(tmp_path)
    seeker, helper, hostile = engine.agents[:3]
    for day in (1, 2, 3):
        engine.relationship_updater.apply_structured_relationship_update(
            day=day, hour=8, speaker=helper, listener=seeker,
            action="offer_help", outcome="completed",
        )
        engine.relationship_updater.apply_structured_relationship_update(
            day=day, hour=12, speaker=hostile, listener=seeker,
            action="argue", outcome="completed",
        )

    allowed = engine.actions.get_allowed_actions_for_relationship(0)
    base = engine.social_policy.get_action_weights(allowed, "neutral")
    trusted, trusted_delta, _ = (
        engine.social_policy.adjust_action_weights_for_relationship_state(
            base, seeker.get_relationship_state(helper.name)
        )
    )
    distrusted, distrusted_delta, _ = (
        engine.social_policy.adjust_action_weights_for_relationship_state(
            base, seeker.get_relationship_state(hostile.name)
        )
    )

    assert trusted["ask_for_help"] > distrusted["ask_for_help"]
    assert trusted_delta["ask_for_help"] > 0
    assert distrusted_delta["ask_for_help"] < 0


def test_relationship_history_changes_listener_target_weight(tmp_path):
    engine = build_engine(tmp_path)
    seeker, helper, hostile = engine.agents[:3]
    for day in (1, 2, 3):
        engine.relationship_updater.apply_structured_relationship_update(
            day=day, hour=8, speaker=helper, listener=seeker,
            action="cooperate", outcome="completed",
        )
        engine.relationship_updater.apply_structured_relationship_update(
            day=day, hour=12, speaker=hostile, listener=seeker,
            action="insult", outcome="completed",
        )

    weights = engine.conversation_selector.get_listener_weights(
        seeker, [helper, hostile]
    )

    assert weights[0] > weights[1]


def test_failed_counterpart_strategy_adapts_to_known_helper(tmp_path):
    engine = build_engine(tmp_path)
    seeker, first_target, alternate = engine.agents[:3]
    updater = engine.relationship_updater
    for day in (1, 2):
        updater.apply_structured_relationship_update(
            day=day, hour=8, speaker=first_target, listener=seeker,
            action="offer_help", outcome="completed",
        )
    goal = knowledge_goal(seeker.name)
    first = engine.goal_planner.select_strategy(goal, seeker, engine)
    assert first.target_agent == first_target.name
    intent = engine.intent_planner.create_intent_from_goal(goal, first, 1)
    goal.current_strategy = first.name
    goal.strategy_started_day = 1

    for day in (2, 3, 4):
        updater.apply_structured_relationship_update(
            day=day, hour=12, speaker=seeker, listener=first_target,
            action="ask_for_help", outcome="refused",
        )
    for day in (2, 3):
        updater.apply_structured_relationship_update(
            day=day, hour=18, speaker=alternate, listener=seeker,
            action="offer_help", outcome="completed",
        )

    replacement, trigger = engine.goal_planner.should_adapt(
        goal, intent, seeker, engine, current_day=4
    )

    assert trigger == "relationship"
    assert replacement.target_agent == alternate.name
    assert "offered me help" in replacement.relevant_social_memories[0]
