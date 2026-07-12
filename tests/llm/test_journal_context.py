from src.agents.agent import Agent
from src.agents.journal_entry import JournalEntry
from src.llm.context import build_conversation_context


def build_agent(name: str) -> Agent:
    return Agent(
        id=name.lower(),
        name=name,
        personality="curious",
        location_id="cafe",
    )


def build_context(
    speaker: Agent,
    listener: Agent,
    current_day: int,
) -> dict:
    return build_conversation_context(
        speaker=speaker,
        listener=listener,
        location_id="cafe",
        relationship_label="friendly",
        relationship_score=10,
        current_day=current_day,
        daily_event=None,
        allowed_actions=["chat"],
    )


def test_conversation_context_includes_recent_journals():
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    for day in range(1, 6):
        speaker.upsert_daily_journal(
            JournalEntry(
                day=day,
                summary=f"Summary for day {day}.",
            )
        )

    context = build_context(
        speaker,
        listener,
        current_day=6,
    )

    assert "recent_journals" in context

    assert context["recent_journals"] == [
        "Day 3: Summary for day 3.",
        "Day 4: Summary for day 4.",
        "Day 5: Summary for day 5.",
    ]


def test_conversation_context_does_not_include_current_day_journal():
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    speaker.upsert_daily_journal(
        JournalEntry(
            day=3,
            summary="Historical summary.",
        )
    )

    speaker.upsert_daily_journal(
        JournalEntry(
            day=4,
            summary="Current-day summary.",
        )
    )

    context = build_context(
        speaker,
        listener,
        current_day=4,
    )

    assert context["recent_journals"] == [
        "Day 3: Historical summary."
    ]


def test_conversation_context_does_not_include_future_journal():
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    speaker.upsert_daily_journal(
        JournalEntry(
            day=5,
            summary="Future journal.",
        )
    )

    context = build_context(
        speaker,
        listener,
        current_day=4,
    )

    assert context["recent_journals"] == []


def test_conversation_context_uses_empty_list_without_journals():
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    context = build_context(
        speaker,
        listener,
        current_day=1,
    )

    assert context["recent_journals"] == []


def test_conversation_context_uses_speaker_journals_only():
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    speaker.upsert_daily_journal(
        JournalEntry(
            day=1,
            summary="Maya's journal.",
        )
    )

    listener.upsert_daily_journal(
        JournalEntry(
            day=1,
            summary="Ethan's journal.",
        )
    )

    context = build_context(
        speaker,
        listener,
        current_day=2,
    )

    assert context["recent_journals"] == [
        "Day 1: Maya's journal."
    ]

    assert all(
        "Ethan's journal" not in journal
        for journal in context["recent_journals"]
    )