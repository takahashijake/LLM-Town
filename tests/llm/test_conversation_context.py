from src.agents.agent import Agent
from src.agents.intent import AgentIntent
from src.agents.journal_entry import JournalEntry
from src.agents.memory import Memory
from src.llm.client import TransformersLLMClient
from src.llm.context import build_conversation_context, select_recent_topics
from src.town.daily_event import DailyEvent
from src.actions.action_system import ActionSystem
from src.systems.reputation import ReputationSystem


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


def test_context_keeps_speaker_private_state_and_shared_public_information():
    speaker = agent("Maya")
    listener = agent("Ethan")
    speaker.upsert_daily_journal(
        JournalEntry(day=2, summary="I privately decided to verify the red ledger.")
    )
    event = DailyEvent(
        id="public_reading",
        name="Public Reading",
        description="Residents are reading together in the library.",
        location_id="library",
        tags=["public", "learning"],
    )
    intent = AgentIntent(
        agent_name="Maya",
        intent_type="investigate",
        description="Verify the red ledger with Ethan.",
        created_day=2,
        expires_day=4,
        priority=3,
        target_agent="Ethan",
        target_location="library",
    ).to_dict()

    context = build_conversation_context(
        speaker,
        listener,
        "library",
        "friendly",
        4,
        current_day=3,
        speaker_intent=intent,
        relationship_history=["Maya and Ethan agreed to compare notes."],
        daily_event=event,
    )

    assert context["speaker_intent"]["description"] == intent["description"]
    assert "privately decided" in context["recent_journals"][0]
    assert context["relationship_history"] == [
        "Maya and Ethan agreed to compare notes."
    ]
    assert context["daily_event"]["name"] == "Public Reading"


def test_irrelevant_speaker_intent_and_private_arc_state_are_not_prompt_context():
    secret_intent = AgentIntent(
        agent_name="Maya",
        intent_type="investigate",
        description="Question Carlos privately at the market.",
        created_day=1,
        expires_day=5,
        priority=3,
        target_agent="Carlos",
        target_location="market",
    ).to_dict()
    context = build_conversation_context(
        agent("Maya"),
        agent("Ethan"),
        "library",
        "neutral",
        0,
        current_day=2,
        speaker_intent=secret_intent,
        town_arcs=[
            {
                "id": "public_questions",
                "name": "Public Questions",
                "description": "Residents are asking about town records.",
                "location_id": "library",
                "status": "active",
                "tags": ["private-system-tag"],
                "tension": 5,
                "progress": 2,
                "involved_agents": ["Carlos"],
            }
        ],
    )

    assert context["speaker_intent"] is None
    assert context["town_arcs"] == [
        {
            "id": "public_questions",
            "name": "Public Questions",
            "description": "Residents are asking about town records.",
            "location_id": "library",
        }
    ]
    prompt = TransformersLLMClient._build_prompt(object.__new__(TransformersLLMClient), context)
    assert "Question Carlos" not in prompt
    assert "tension" not in prompt.lower()
    assert "private-system-tag" not in prompt


def test_context_is_bounded_and_journal_does_not_duplicate_explicit_memory():
    speaker = agent("Maya")
    listener = agent("Ethan")
    repeated = "Ethan and Maya compared the red ledger totals carefully."
    speaker.memory = [
        memory(9, "conversation", repeated + (" detail" * 200), ["Maya", "Ethan"], 5)
        for _ in range(6)
    ]
    speaker.upsert_daily_journal(JournalEntry(day=9, summary=repeated))
    speaker.memory_summary = "old summary " * 200
    speaker.goals = ["red ledger totals", "unrelated gardening", "another goal"]
    context = build_conversation_context(
        speaker,
        listener,
        "library",
        "friendly",
        4,
        current_day=10,
        relationship_history=["relationship detail " * 100] * 5,
    )

    assert len(context["relevant_memories"]) == 1
    assert context["recent_journals"] == []
    assert context["memory_summary"] == ""
    assert context["goals"] == ["red ledger totals"]
    assert len(context["relationship_history"]) == 2
    assert context["context_evidence"]["prompt_context_text_chars"] <= 2_400
    assert all(len(item) <= 320 for item in context["relevant_memories"])


def test_memory_summary_is_used_only_when_specific_context_is_sparse():
    speaker = agent("Maya")
    listener = agent("Ethan")
    speaker.memory_summary = "Maya has long tracked discrepancies in public records."

    sparse = build_conversation_context(
        speaker, listener, "library", "neutral", 0, current_day=5
    )
    sparse_prompt = TransformersLLMClient._build_prompt(
        object.__new__(TransformersLLMClient), sparse
    )
    assert sparse["memory_summary"] == speaker.memory_summary
    assert speaker.memory_summary in sparse_prompt

    speaker.memory.append(
        memory(4, "conversation", "Ethan compared the latest ledger.", ["Maya", "Ethan"])
    )
    specific = build_conversation_context(
        speaker, listener, "library", "neutral", 0, current_day=5
    )
    assert specific["memory_summary"] == ""


def test_hard_context_budget_counts_all_dynamic_prompt_fields():
    speaker = agent("Maya")
    listener = agent("Ethan")
    speaker.personality = "observant " * 100
    speaker.current_activity = "Review enormous public records " * 100
    speaker.current_activity_reason = "A detailed immediate reason " * 100
    speaker.recent_topics = ["topic " * 100 for _ in range(10)]
    speaker.memory = [
        memory(
            9,
            "conversation",
            f"Shared ledger evidence {index} " * 100,
            ["Maya", "Ethan"],
            5,
        )
        for index in range(4)
    ]
    speaker.upsert_daily_journal(JournalEntry(day=9, summary="Journal evidence " * 100))
    event = DailyEvent(
        id="large_event",
        name="Public Records Day " * 20,
        description="Residents inspect public records together. " * 100,
        location_id="library",
        tags=["public"],
    )

    context = build_conversation_context(
        speaker,
        listener,
        "library",
        "friendly",
        5,
        current_day=10,
        daily_event=event,
        relationship_history=["Shared relationship event " * 100] * 3,
        town_arcs=[
            {
                "id": "records_arc",
                "name": "Records Review " * 20,
                "description": "A public records issue continues. " * 100,
                "location_id": "library",
            }
        ],
    )

    assert context["context_evidence"]["prompt_context_text_chars"] <= 2_400


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


def test_context_exposes_only_speakers_belief_about_listener():
    speaker = agent("Maya")
    listener = agent("Ethan")
    system = ReputationSystem(ActionSystem())
    system.record_observation(
        day=1,
        observer=speaker,
        target_agent="Ethan",
        dimension="trustworthiness",
        value=1,
        evidence_id="maya-saw-ethan",
    )
    system.record_observation(
        day=1,
        observer=listener,
        target_agent="Maya",
        dimension="hostility",
        value=1,
        evidence_id="ethan-private-belief",
    )

    reputation_context = system.format_beliefs_for_context(speaker, "Ethan")
    context = build_conversation_context(
        speaker,
        listener,
        "library",
        "neutral",
        0,
        current_day=2,
        reputation_context=reputation_context,
    )
    prompt = TransformersLLMClient._build_prompt(
        object.__new__(TransformersLLMClient), context
    )

    assert "Ethan is slightly trustworthy" in prompt
    assert "Maya" not in " ".join(context["reputation_context"])
    assert "The speaker believes Maya" not in prompt
    assert "0.8" not in prompt
