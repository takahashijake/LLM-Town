from types import SimpleNamespace

from src.agents.intent import AgentIntent
from src.agents.relationships import RelationshipManager
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.simulation.state import SimulationState


def build_engine():
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )


def test_repair_relationship_intent_succeeds_after_positive_target_conversation():
    engine = build_engine()

    speaker = engine.agents[0]
    listener = engine.agents[1]

    intent = AgentIntent(
        agent_name=speaker.name,
        intent_type="repair_relationship",
        description=f"{speaker.name} wants to repair their relationship with {listener.name}.",
        created_day=1,
        expires_day=3,
        priority=5,
        target_agent=listener.name,
        progress_goal=1,
    )

    engine.agent_intents = {
        speaker.name: intent,
    }
    engine.intent_history = []

    result = engine.update_intents_after_conversation(
        day=1,
        location_id="cafe",
        speaker=speaker,
        listener=listener,
        action="apologize",
        relationship_change=1,
        new_score=0,
        conversation_tags=["neutral", "apologize"],
    )

    assert result is not None
    assert result["status"] == "succeeded"
    assert speaker.name not in engine.agent_intents
    assert len(engine.intent_history) == 1
    assert engine.intent_history[0].status == "succeeded"
    assert engine.intent_history[0].completed_day == 1


def test_investigate_intent_progresses_from_rumor_conversation():
    engine = build_engine()

    speaker = engine.agents[0]
    listener = engine.agents[1]

    intent = AgentIntent(
        agent_name=speaker.name,
        intent_type="investigate",
        description=f"{speaker.name} wants to gather information.",
        created_day=1,
        expires_day=2,
        priority=3,
        target_location="library",
        progress_goal=2,
    )

    engine.agent_intents = {
        speaker.name: intent,
    }
    engine.intent_history = []

    result = engine.update_intents_after_conversation(
        day=1,
        location_id="market",
        speaker=speaker,
        listener=listener,
        action="share_rumor",
        relationship_change=0,
        new_score=0,
        conversation_tags=["rumor", "market", "neutral", "share_rumor"],
    )

    assert result is not None
    assert result["status"] == "active"
    assert result["progress"] == 1
    assert speaker.name in engine.agent_intents
    assert engine.agent_intents[speaker.name].progress == 1
    assert engine.intent_history == []


def test_build_friendship_intent_fails_after_negative_target_interaction():
    engine = build_engine()

    speaker = engine.agents[0]
    listener = engine.agents[1]

    intent = AgentIntent(
        agent_name=speaker.name,
        intent_type="build_friendship",
        description=f"{speaker.name} wants to strengthen their bond with {listener.name}.",
        created_day=1,
        expires_day=3,
        priority=4,
        target_agent=listener.name,
        progress_goal=2,
    )

    engine.agent_intents = {
        speaker.name: intent,
    }
    engine.intent_history = []

    result = engine.update_intents_after_conversation(
        day=1,
        location_id="cafe",
        speaker=speaker,
        listener=listener,
        action="argue",
        relationship_change=-1,
        new_score=-1,
        conversation_tags=["neutral", "argue"],
    )

    assert result is not None
    assert result["status"] == "failed"
    assert speaker.name not in engine.agent_intents
    assert len(engine.intent_history) == 1
    assert engine.intent_history[0].status == "failed"


def test_expired_intent_moves_to_history_when_intents_update():
    engine = build_engine()

    agent = engine.agents[0]

    expired_intent = AgentIntent(
        agent_name=agent.name,
        intent_type="socialize",
        description=f"{agent.name} wants to spend time with residents.",
        created_day=1,
        expires_day=1,
        priority=2,
        target_location="cafe",
        progress_goal=2,
    )

    engine.agent_intents = {
        agent.name: expired_intent,
    }
    engine.intent_history = []
    engine.sync_intent_system_refs()

    engine.update_agent_intents(current_day=2)

    assert any(
        intent.id == expired_intent.id and intent.status == "expired"
        for intent in engine.intent_history
    )


def test_state_saves_intent_history(tmp_path):
    state = SimulationState(path=str(tmp_path / "save_state.json"))

    completed_intent = AgentIntent(
        agent_name="Maya",
        intent_type="investigate",
        description="Maya wants to gather information.",
        created_day=1,
        expires_day=2,
        priority=3,
        target_location="library",
        status="succeeded",
        progress=2,
        progress_goal=2,
        completed_day=1,
        completion_reason="Intent reached its progress goal.",
    )

    fake_engine = SimpleNamespace(
        agents=[],
        relationships=RelationshipManager(),
        relationship_events=[],
        agent_intents={},
        intent_history=[completed_intent],
        town_arcs=[],
    )

    state.save(fake_engine, current_day=1, current_hour=22)
    loaded = state.load()

    assert loaded["intent_history"][0]["agent_name"] == "Maya"
    assert loaded["intent_history"][0]["status"] == "succeeded"
    assert loaded["intent_history"][0]["progress"] == 2