from src.agents.agent import Agent
from src.agents.intent import AgentIntent
from src.agents.journal_entry import JournalEntry
from src.agents.memory import Memory
from src.llm.client import TransformersLLMClient
from src.llm.context import build_conversation_context, select_recent_topics
from src.town.daily_event import DailyEvent


def agent(name: str) -> Agent:
    return Agent(
        id=name.lower(),
        name=name,
        personality="careful and curious",
        location_id="library",
        occupation="journalist",
        goals=["understand the supplier dispute"],
        needs={"knowledge": 25, "social": 60},
    )


def memory(day, kind, description, participants, importance=2, location="library"):
    return Memory(
        day=day,
        hour=12,
        type=kind,
        description=description,
        participants=participants,
        location=location,
        importance=importance,
        sentiment=0,
        tags=[],
    )


def test_context_prioritizes_partner_history_and_excludes_old_event_noise():
    speaker = agent("Maya")
    listener = agent("Ethan")
    speaker.memory = [
        memory(19, "conversation", "Ethan promised to compare the invoices.", ["Maya", "Ethan"]),
        memory(19, "daily_event", "A very important public festival happened.", [], importance=5),
        memory(1, "conversation", "Ethan discussed an obsolete lead.", ["Maya", "Ethan"], importance=5),
        memory(8, "conversation", "Carlos discussed bread.", ["Maya", "Carlos"], importance=5, location="market"),
    ]

    context = build_conversation_context(
        speaker, listener, "library", "friendly", 4, current_day=20
    )

    assert any("promised to compare" in item for item in context["relevant_memories"])
    assert all("festival" not in item for item in context["relevant_memories"])
    assert all("obsolete" not in item for item in context["relevant_memories"])
    assert all("Carlos" not in item for item in context["relevant_memories"])


def test_context_respects_speaker_information_boundary():
    speaker = agent("Maya")
    listener = agent("Ethan")
    speaker.memory.append(
        memory(2, "conversation", "Ethan told Maya the invoice total was wrong.", ["Maya", "Ethan"])
    )
    listener.memory.append(
        memory(2, "personal", "Ethan secretly plans to leave town.", ["Ethan"], importance=5)
    )
    listener.upsert_daily_journal(JournalEntry(day=2, summary="I hid the missing ledger."))
    listener_secret_intent = AgentIntent(
        agent_name="Ethan",
        intent_type="investigate",
        description="Ethan secretly wants to expose Maya.",
        created_day=1,
        expires_day=5,
        priority=3,
    ).to_dict()

    context = build_conversation_context(
        speaker,
        listener,
        "library",
        "neutral",
        0,
        current_day=3,
        listener_intent=listener_secret_intent,
    )
    prompt = TransformersLLMClient._build_prompt(object.__new__(TransformersLLMClient), context)

    assert "invoice total" in prompt
    assert "leave town" not in prompt
    assert "missing ledger" not in prompt
    assert "expose Maya" not in prompt
    assert "listener_intent" not in context


def test_recent_topics_are_deduplicated_and_action_tags_are_not_prompt_topics():
    topics = ["market", "offer_help", "MARKET", "books", "chat", "garden"]

    assert select_recent_topics(topics) == ["market", "books", "garden"]


def test_prompt_is_compact_and_requires_grounded_action_aligned_dialogue():
    context = build_conversation_context(
        agent("Maya"),
        agent("Ethan"),
        "library",
        "friendly",
        5,
        current_day=2,
        allowed_actions=["chat", "ask_for_help"],
        suggested_action="ask_for_help",
    )

    prompt = TransformersLLMClient._build_prompt(object.__new__(TransformersLLMClient), context)

    assert len(prompt.split()) < 550
    assert "Assert facts only" in prompt
    assert "The words and action must agree" in prompt
    assert "one focus, not every context item" in prompt
    assert "under 35 words" in prompt


def test_broad_activity_tag_does_not_make_remote_event_relevant():
    speaker = agent("Maya")
    speaker.current_activity = "Socialize with townspeople"
    speaker.current_activity_tags = ["social"]
    event = DailyEvent(
        id="town_cleanup",
        name="Town Cleanup",
        description="Volunteers are cleaning the square.",
        location_id="town_square",
        tags=["community", "social"],
    )

    context = build_conversation_context(
        speaker,
        agent("Ethan"),
        "cafe",
        "neutral",
        0,
        current_day=2,
        daily_event=event,
    )

    assert context["daily_event_relevant"] is False
    assert context["daily_event"] is None


def test_internal_arc_and_activity_labels_are_rendered_as_resident_context():
    speaker = agent("Maya")
    speaker.current_activity = "Work on intent: seek_work"
    speaker.memory.append(
        memory(
            2,
            "town_arc_participation",
            "Maya and Ethan affected the town arc 'Community Project' through action 'cooperate'. Progress changed from 0 to 1; tension changed from 1 to 0.",
            ["Maya", "Ethan"],
        )
    )

    context = build_conversation_context(
        speaker, agent("Ethan"), "library", "friendly", 3, current_day=3
    )
    prompt = TransformersLLMClient._build_prompt(object.__new__(TransformersLLMClient), context)

    assert "Look for work or business opportunities" in prompt
    assert "worked together on Community Project" in prompt
    assert "Progress changed" not in prompt
    assert "through action" not in prompt
