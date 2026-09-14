from src.agents.agent import Agent
from src.agents.intent import AgentIntent
from src.agents.memory import Memory
from src.simulation.conversation_recorder import ConversationRecorder


class FakeLogger:
    def __init__(self):
        self.conversations = []
        self.events = []

    def log_conversation(self, record):
        self.conversations.append(record)

    def log_event(self, record):
        self.events.append(record)


def build_agent(name: str) -> Agent:
    return Agent(
        id=f"agent_{name.lower()}",
        name=name,
        personality="curious",
        location_id="library",
        occupation="resident",
        goals=[],
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
    )


def test_create_conversation_memory_uses_conversation_fields():
    recorder = ConversationRecorder(logger=FakeLogger())
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    memory = recorder.create_conversation_memory(
        day=2,
        hour=12,
        location_id="library",
        speaker=speaker,
        listener=listener,
        conversation="The town feels busy today.",
        relationship_change=1,
        tags=["conversation", "chat", "neutral"],
    )

    assert isinstance(memory, Memory)
    assert memory.day == 2
    assert memory.hour == 12
    assert memory.type == "conversation"
    assert memory.description == "The town feels busy today."
    assert memory.participants == ["Maya", "Ethan"]
    assert memory.location == "library"
    assert memory.importance == 2
    assert memory.sentiment == 1
    assert memory.tags == ["conversation", "chat", "neutral"]


def test_remember_conversation_for_agents_updates_topics_and_memories():
    recorder = ConversationRecorder(logger=FakeLogger())
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    memory = recorder.remember_conversation_for_agents(
        day=3,
        hour=18,
        location_id="market",
        speaker=speaker,
        listener=listener,
        conversation="I can help with the market work.",
        relationship_change=1,
        tags=["market", "offer_help"],
    )

    assert memory in speaker.memory
    assert memory in listener.memory

    assert "market" in speaker.recent_topics
    assert "offer_help" in speaker.recent_topics
    assert "market" in listener.recent_topics
    assert "offer_help" in listener.recent_topics


def test_log_conversation_event_logs_conversation_and_event_records():
    logger = FakeLogger()
    recorder = ConversationRecorder(logger=logger)

    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    speaker_intent = AgentIntent(
        agent_name="Maya",
        intent_type="investigate",
        description="Maya wants to gather information.",
        created_day=1,
        expires_day=3,
        priority=2,
        target_agent=None,
        target_location="library",
    )

    listener_intent = AgentIntent(
        agent_name="Ethan",
        intent_type="socialize",
        description="Ethan wants to talk with residents.",
        created_day=1,
        expires_day=3,
        priority=2,
        target_agent=None,
        target_location="cafe",
    )

    recorder.log_conversation_event(
        day=4,
        hour=22,
        location_id="library",
        speaker=speaker,
        listener=listener,
        conversation="Could you give me advice?",
        relationship_change=0,
        new_score=2,
        relationship_label="neutral",
        action="ask_for_help",
        action_source="parsed",
        action_reason="direct_request",
        tags=["knowledge", "ask_for_help"],
        speaker_intent=speaker_intent,
        listener_intent=listener_intent,
        suggested_action="ask_for_help",
        parsed_action="ask_for_help",
        inferred_action="ask_for_help",
        base_action_weights={"chat": 5},
        intent_adjusted_weights={"chat": 5, "ask_for_help": 3},
        allowed_actions=["chat", "ask_for_help"],
        final_action_reason="trusted_parsed_non_chat",
        raw_response='{"dialogue": "Could you give me advice?"}',
        generation_error="",
        context_evidence={"daily_event_relevant": False},
        context_snapshot={"memories": ["Earlier advice"]},
    )

    assert len(logger.conversations) == 1
    assert len(logger.events) == 1

    conversation_record = logger.conversations[0]

    assert conversation_record["day"] == 4
    assert conversation_record["hour"] == 22
    assert conversation_record["location"] == "library"
    assert conversation_record["speaker"] == "Maya"
    assert conversation_record["listener"] == "Ethan"
    assert conversation_record["conversation"] == "Could you give me advice?"
    assert conversation_record["relationship_change"] == 0
    assert conversation_record["relationship_score"] == 2
    assert conversation_record["relationship_label"] == "neutral"
    assert conversation_record["action"] == "ask_for_help"
    assert conversation_record["tags"] == ["knowledge", "ask_for_help"]
    assert conversation_record["speaker_intent_type"] == "investigate"
    assert conversation_record["listener_intent_type"] == "socialize"
    assert conversation_record["allowed_actions"] == ["chat", "ask_for_help"]
    assert conversation_record["final_action_reason"] == "trusted_parsed_non_chat"
    assert conversation_record["raw_response"].startswith("{")
    assert conversation_record["generation_error"] == ""
    assert conversation_record["context_evidence"]["daily_event_relevant"] is False
    assert conversation_record["context"]["memories"] == ["Earlier advice"]

    event_record = logger.events[0]

    assert event_record == {
        "type": "conversation",
        "day": 4,
        "hour": 22,
        "location": "library",
        "participants": [
            "Maya",
            "Ethan",
        ],
    }


def test_print_conversation_event_outputs_expected_summary(capsys):
    recorder = ConversationRecorder(logger=FakeLogger())

    recorder.print_conversation_event(
        day=5,
        hour=12,
        location_id="market",
        conversation="I disagree with this plan.",
        relationship_label="tense",
        new_score=-3,
        relationship_change=-1,
        action="argue",
    )

    captured = capsys.readouterr()

    assert captured.out == (
        "Day 5, 12:00 at market: I disagree with this plan. "
        "Relationship is now tense "
        "(score -3, change -1). "
        "Action: argue.\n"
    )
