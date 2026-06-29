from src.simulation.engine import SimulationEngine
from src.llm.client import FakeLLMClient


def build_engine():
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )


def get_agent(engine, name):
    return next(agent for agent in engine.agents if agent.name == name)


def test_generate_conversations_preserves_core_side_effects(monkeypatch):
    engine = build_engine()

    maya = get_agent(engine, "Maya")
    ethan = get_agent(engine, "Ethan")

    # Force exactly one conversation pair at one location.
    ethan.location_id = maya.location_id

    old_score = engine.relationships.get_score(maya.name, ethan.name)

    conversation_logs = []
    event_logs = []

    monkeypatch.setattr(
        engine,
        "choose_conversation_pair",
        lambda agents_here: (maya, ethan),
    )
    monkeypatch.setattr(
        engine.conversation_policy,
        "choose_weighted_action",
        lambda weights: "compliment",
    )

    # The effects applier now uses engine.relationship_updater directly.
    # Patch this subsystem, not the old engine wrapper.
    monkeypatch.setattr(
        engine.relationship_updater,
        "get_relationship_change",
        lambda relationship_label: 0,
    )

    monkeypatch.setattr(
        engine.logger,
        "log_conversation",
        conversation_logs.append,
    )
    monkeypatch.setattr(
        engine.logger,
        "log_event",
        event_logs.append,
    )

    engine.generate_conversations(day=1, hour=8)

    assert engine.relationships.get_score(maya.name, ethan.name) == old_score + 1
    assert maya.relationships[ethan.name] == old_score + 1
    assert ethan.relationships[maya.name] == old_score + 1

    assert engine.recent_actions[-1] == "compliment"
    assert engine.recent_dialogues[-1] == "you handled that really well."

    assert len(engine.relationship_events) == 1
    relationship_event = engine.relationship_events[0]
    assert relationship_event.agent_a == "Maya"
    assert relationship_event.agent_b == "Ethan"
    assert relationship_event.action == "compliment"
    assert relationship_event.relationship_change == 1
    assert relationship_event.relationship_score == old_score + 1

    assert any(
        memory.type == "conversation"
        and memory.description == "You handled that really well."
        and "compliment" in memory.tags
        for memory in maya.memory
    )
    assert any(
        memory.type == "conversation"
        and memory.description == "You handled that really well."
        and "compliment" in memory.tags
        for memory in ethan.memory
    )

    assert conversation_logs
    conversation_record = conversation_logs[0]

    assert conversation_record["speaker"] == "Maya"
    assert conversation_record["listener"] == "Ethan"
    assert conversation_record["conversation"] == "You handled that really well."
    assert conversation_record["action"] == "compliment"
    assert conversation_record["suggested_action"] == "compliment"
    assert conversation_record["parsed_action"] == "compliment"
    assert conversation_record["relationship_change"] == 1
    assert conversation_record["relationship_score"] == old_score + 1
    assert "final_action_reason" in conversation_record
    assert "allowed_actions" in conversation_record
    assert "base_action_weights" in conversation_record
    assert "intent_adjusted_weights" in conversation_record

    assert event_logs
    assert event_logs[0]["type"] == "conversation"
    assert event_logs[0]["participants"] == ["Maya", "Ethan"]
