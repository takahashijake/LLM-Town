from src.agents.agent import Agent
from src.agents.journal_entry import JournalEntry


def build_agent() -> Agent:
    return Agent(
        id="agent-1",
        name="Maya",
        personality="curious",
        location_id="cafe",
    )


def test_upsert_daily_journal_adds_new_day():
    agent = build_agent()
    journal = JournalEntry(
        day=1,
        summary="Maya visited the market.",
    )

    agent.upsert_daily_journal(journal)

    assert agent.daily_journals == [journal]


def test_upsert_daily_journal_replaces_existing_day():
    agent = build_agent()

    agent.upsert_daily_journal(
        JournalEntry(
            day=1,
            summary="Original summary.",
        )
    )

    replacement = JournalEntry(
        day=1,
        summary="Updated summary.",
    )

    agent.upsert_daily_journal(replacement)

    assert len(agent.daily_journals) == 1
    assert agent.daily_journals[0] == replacement
    assert agent.daily_journals[0].summary == "Updated summary."


def test_upsert_daily_journal_sorts_entries_by_day():
    agent = build_agent()

    agent.upsert_daily_journal(
        JournalEntry(day=3, summary="Day three.")
    )
    agent.upsert_daily_journal(
        JournalEntry(day=1, summary="Day one.")
    )
    agent.upsert_daily_journal(
        JournalEntry(day=2, summary="Day two.")
    )

    assert [
        journal.day
        for journal in agent.daily_journals
    ] == [1, 2, 3]


def test_get_recent_journals_excludes_current_and_future_days():
    agent = build_agent()

    for day in range(1, 6):
        agent.upsert_daily_journal(
            JournalEntry(
                day=day,
                summary=f"Day {day}.",
            )
        )

    journals = agent.get_recent_journals(
        current_day=4,
        limit=10,
    )

    assert [
        journal.day
        for journal in journals
    ] == [1, 2, 3]


def test_get_recent_journals_respects_limit():
    agent = build_agent()

    for day in range(1, 7):
        agent.upsert_daily_journal(
            JournalEntry(
                day=day,
                summary=f"Day {day}.",
            )
        )

    journals = agent.get_recent_journals(
        current_day=7,
        limit=3,
    )

    assert [
        journal.day
        for journal in journals
    ] == [4, 5, 6]


def test_get_recent_journals_returns_empty_when_no_history_exists():
    agent = build_agent()

    journals = agent.get_recent_journals(
        current_day=1,
        limit=3,
    )

    assert journals == []


def test_journal_entry_to_dict_contains_all_fields():
    journal = JournalEntry(
        day=2,
        summary="Maya helped Ethan.",
        important_people=["Ethan"],
        important_locations=["market"],
        important_events=["Market Festival"],
        relationship_changes={"Ethan": 4},
        completed_intents=["help: succeeded"],
        unresolved_topics=["vendor prices"],
        tags=["help", "market"],
    )

    journal_data = journal.to_dict()

    assert journal_data == {
        "day": 2,
        "summary": "Maya helped Ethan.",
        "important_people": ["Ethan"],
        "important_locations": ["market"],
        "important_events": ["Market Festival"],
        "relationship_changes": {"Ethan": 4},
        "completed_intents": ["help: succeeded"],
        "unresolved_topics": ["vendor prices"],
        "tags": ["help", "market"],
    }