from src.agents.agent import Agent
from src.agents.intent import AgentIntent
from src.agents.memory import Memory
from src.agents.relationship_event import RelationshipEvent
from src.simulation.journal_system import JournalSystem


def build_agent(name: str = "Maya") -> Agent:
    return Agent(
        id=name.lower(),
        name=name,
        personality="curious",
        location_id="cafe",
    )


def build_memory(
    day: int,
    *,
    memory_type: str = "conversation",
    description: str = "Maya spoke with Ethan.",
    participants: list[str] | None = None,
    location: str = "cafe",
    tags: list[str] | None = None,
    importance: int = 3,
    sentiment: int = 1,
) -> Memory:
    if participants is None:
        participants = ["Maya", "Ethan"]

    if tags is None:
        tags = ["conversation", "market"]

    return Memory(
        day=day,
        hour=12,
        type=memory_type,
        description=description,
        participants=participants,
        location=location,
        importance=importance,
        sentiment=sentiment,
        tags=tags,
    )


def build_relationship_event(
    day: int = 2,
    *,
    agent_a: str = "Maya",
    agent_b: str = "Ethan",
    relationship_change: int = 4,
) -> RelationshipEvent:
    return RelationshipEvent(
        day=day,
        hour=12,
        agent_a=agent_a,
        agent_b=agent_b,
        action="offer_help",
        relationship_change=relationship_change,
        relationship_score=14,
        relationship_label="friendly",
        description="Maya offered Ethan help.",
        location="market",
        tags=["help", "market"],
        conversation="I can help with the market records.",
    )


def build_completed_intent(
    day: int = 2,
    *,
    agent_name: str = "Maya",
) -> AgentIntent:
    intent = AgentIntent(
        agent_name=agent_name,
        intent_type="help",
        description="Help Ethan inspect the market records.",
        created_day=1,
        expires_day=4,
        priority=3,
        target_agent="Ethan",
        target_location="market",
    )

    intent.mark_succeeded(
        day=day,
        reason="Maya helped Ethan inspect the records.",
    )

    return intent


def test_create_daily_journal_collects_agent_specific_details():
    agent = build_agent()

    agent.memory = [
        build_memory(
            day=2,
            description="Maya discussed price changes with Ethan.",
            location="market",
            tags=["conversation", "market", "prices"],
        ),
        build_memory(
            day=2,
            memory_type="daily_event",
            description="Town event today: Market Festival.",
            participants=[],
            location="market",
            tags=["event", "market_festival"],
        ),
        build_memory(
            day=1,
            description="This older memory should not be used.",
        ),
    ]

    activity_records = [
        {
            "day": 2,
            "agent": "Maya",
            "activity_name": "work",
            "location": "market",
        },
        {
            "day": 2,
            "agent": "Ethan",
            "activity_name": "read",
            "location": "library",
        },
    ]

    town_arc_change_records = [
        {
            "day": 2,
            "speaker": "Maya",
            "listener": "Ethan",
            "arc_name": "Market Pressure",
        },
        {
            "day": 2,
            "speaker": "Carlos",
            "listener": "Ethan",
            "arc_name": "Unrelated Arc",
        },
    ]

    journal = JournalSystem().create_daily_journal(
        agent=agent,
        day=2,
        activity_records=activity_records,
        relationship_events=[
            build_relationship_event()
        ],
        intent_history=[
            build_completed_intent()
        ],
        town_arc_change_records=town_arc_change_records,
    )

    assert journal.day == 2
    assert journal.summary
    assert "Maya" in journal.summary
    assert "Ethan" in journal.important_people
    assert "market" in journal.important_locations

    assert (
        "Town event today: Market Festival."
        in journal.important_events
    )

    assert journal.relationship_changes == {
        "Ethan": 4
    }

    assert any(
        "succeeded" in outcome
        for outcome in journal.completed_intents
    )

    assert "market" in journal.tags
    assert "prices" in journal.unresolved_topics
    assert "Market Pressure" in journal.summary
    assert "Unrelated Arc" not in journal.summary


def test_create_daily_journal_ignores_records_from_other_days():
    agent = build_agent()
    agent.memory = [
        build_memory(day=1)
    ]

    journal = JournalSystem().create_daily_journal(
        agent=agent,
        day=2,
        activity_records=[],
        relationship_events=[
            build_relationship_event(day=1)
        ],
        intent_history=[
            build_completed_intent(day=1)
        ],
        town_arc_change_records=[],
    )

    assert journal.important_people == []
    assert journal.important_locations == []
    assert journal.important_events == []
    assert journal.relationship_changes == {}
    assert journal.completed_intents == []
    assert "quiet day" in journal.summary.lower()


def test_create_daily_journal_ignores_other_agents_activities():
    agent = build_agent("Maya")

    journal = JournalSystem().create_daily_journal(
        agent=agent,
        day=2,
        activity_records=[
            {
                "day": 2,
                "agent": "Ethan",
                "activity_name": "study",
                "location": "library",
            }
        ],
        relationship_events=[],
        intent_history=[],
        town_arc_change_records=[],
    )

    assert "study" not in journal.summary
    assert "library" not in journal.important_locations


def test_create_daily_journal_ignores_other_agents_intents():
    agent = build_agent("Maya")

    journal = JournalSystem().create_daily_journal(
        agent=agent,
        day=2,
        activity_records=[],
        relationship_events=[],
        intent_history=[
            build_completed_intent(
                day=2,
                agent_name="Ethan",
            )
        ],
        town_arc_change_records=[],
    )

    assert journal.completed_intents == []


def test_create_daily_journal_aggregates_relationship_changes():
    agent = build_agent()

    journal = JournalSystem().create_daily_journal(
        agent=agent,
        day=2,
        activity_records=[],
        relationship_events=[
            build_relationship_event(
                relationship_change=3,
            ),
            build_relationship_event(
                relationship_change=-1,
            ),
        ],
        intent_history=[],
        town_arc_change_records=[],
    )

    assert journal.relationship_changes == {
        "Ethan": 2
    }


def test_create_daily_journal_handles_agent_as_second_participant():
    agent = build_agent("Maya")

    journal = JournalSystem().create_daily_journal(
        agent=agent,
        day=2,
        activity_records=[],
        relationship_events=[
            build_relationship_event(
                agent_a="Ethan",
                agent_b="Maya",
                relationship_change=5,
            )
        ],
        intent_history=[],
        town_arc_change_records=[],
    )

    assert journal.relationship_changes == {
        "Ethan": 5
    }


def test_create_daily_journal_limits_important_people_to_five():
    agent = build_agent()

    memories = []

    for index in range(7):
        person = f"Person {index}"

        memories.append(
            build_memory(
                day=2,
                participants=["Maya", person],
                description=f"Maya spoke with {person}.",
            )
        )

    agent.memory = memories

    journal = JournalSystem().create_daily_journal(
        agent=agent,
        day=2,
        activity_records=[],
        relationship_events=[],
        intent_history=[],
        town_arc_change_records=[],
    )

    assert len(journal.important_people) == 5


def test_create_daily_journal_limits_locations_to_five():
    agent = build_agent()

    activity_records = [
        {
            "day": 2,
            "agent": "Maya",
            "activity_name": f"activity-{index}",
            "location": f"location-{index}",
        }
        for index in range(7)
    ]

    journal = JournalSystem().create_daily_journal(
        agent=agent,
        day=2,
        activity_records=activity_records,
        relationship_events=[],
        intent_history=[],
        town_arc_change_records=[],
    )

    assert len(journal.important_locations) == 5


def test_create_daily_journal_deduplicates_locations():
    agent = build_agent()

    agent.memory = [
        build_memory(
            day=2,
            location="market",
        )
    ]

    journal = JournalSystem().create_daily_journal(
        agent=agent,
        day=2,
        activity_records=[
            {
                "day": 2,
                "agent": "Maya",
                "activity_name": "work",
                "location": "market",
            }
        ],
        relationship_events=[],
        intent_history=[],
        town_arc_change_records=[],
    )

    assert journal.important_locations == [
        "market"
    ]


def test_create_daily_journal_removes_ignored_tags():
    agent = build_agent()

    agent.memory = [
        build_memory(
            day=2,
            tags=[
                "conversation",
                "chat",
                "neutral",
                "market",
                "prices",
            ],
        )
    ]

    journal = JournalSystem().create_daily_journal(
        agent=agent,
        day=2,
        activity_records=[],
        relationship_events=[],
        intent_history=[],
        town_arc_change_records=[],
    )

    assert "conversation" not in journal.tags
    assert "chat" not in journal.tags
    assert "neutral" not in journal.tags
    assert "market" in journal.tags
    assert "prices" in journal.tags


def test_create_journals_for_day_creates_one_journal_per_agent():
    agents = [
        build_agent("Maya"),
        build_agent("Ethan"),
    ]

    JournalSystem().create_journals_for_day(
        agents=agents,
        day=1,
        activity_records=[],
        relationship_events=[],
        intent_history=[],
        town_arc_change_records=[],
    )

    assert all(
        len(agent.daily_journals) == 1
        for agent in agents
    )

    assert all(
        agent.daily_journals[0].day == 1
        for agent in agents
    )


def test_create_journals_for_day_is_idempotent_for_same_day():
    agent = build_agent()
    system = JournalSystem()

    for _ in range(2):
        system.create_journals_for_day(
            agents=[agent],
            day=1,
            activity_records=[],
            relationship_events=[],
            intent_history=[],
            town_arc_change_records=[],
        )

    assert len(agent.daily_journals) == 1
    assert agent.daily_journals[0].day == 1


def test_compress_old_memories_archives_cutoff_and_older_days():
    agent = build_agent()

    old_day_1 = build_memory(day=1)
    old_day_3 = build_memory(day=3)
    recent_day_4 = build_memory(day=4)
    recent_day_10 = build_memory(day=10)

    agent.memory = [
        old_day_1,
        old_day_3,
        recent_day_4,
        recent_day_10,
    ]

    archived_count = JournalSystem().compress_old_memories(
        agent=agent,
        current_day=10,
        raw_memory_retention_days=7,
    )

    assert archived_count == 2

    assert agent.memory == [
        recent_day_4,
        recent_day_10,
    ]

    assert agent.memory_archive == [
        old_day_1,
        old_day_3,
    ]


def test_compress_old_memories_does_not_duplicate_archive_entries():
    agent = build_agent()
    memory = build_memory(day=1)

    agent.memory = [memory]
    agent.memory_archive = [memory]

    archived_count = JournalSystem().compress_old_memories(
        agent=agent,
        current_day=10,
        raw_memory_retention_days=7,
    )

    assert archived_count == 0
    assert agent.memory == []
    assert agent.memory_archive == [memory]


def test_compress_old_memories_preserves_all_recent_memories():
    agent = build_agent()

    day_4_memory = build_memory(day=4)
    day_10_memory = build_memory(day=10)

    agent.memory = [
        day_4_memory,
        day_10_memory,
    ]

    archived_count = JournalSystem().compress_old_memories(
        agent=agent,
        current_day=10,
        raw_memory_retention_days=7,
    )

    assert archived_count == 0
    assert agent.memory == [
        day_4_memory,
        day_10_memory,
    ]

    assert agent.memory_archive == []


def test_compress_old_memories_handles_empty_memory():
    agent = build_agent()

    archived_count = JournalSystem().compress_old_memories(
        agent=agent,
        current_day=10,
        raw_memory_retention_days=7,
    )

    assert archived_count == 0
    assert agent.memory == []
    assert agent.memory_archive == []


def test_compress_old_memories_enforces_archive_bound_after_end_of_day():
    agent = build_agent()
    agent.memory_archive = [
        Memory(day=day, hour=8, type="conversation", description=f"old {day}",
               participants=[agent.name], location="cafe", importance=1,
               sentiment=0, tags=["old"], id=f"archive-{day}")
        for day in range(500)
    ]
    agent.memory = [
        Memory(day=1, hour=8, type="conversation", description="newly old",
               participants=[agent.name], location="cafe", importance=1,
               sentiment=0, tags=["old"], id="newly-archived")
    ]

    archived_count = JournalSystem().compress_old_memories(
        agent, current_day=20, raw_memory_retention_days=7,
    )

    assert archived_count == 1
    assert len(agent.memory_archive) == 500
    assert agent.memory_archive[-1].id == "newly-archived"
    assert "Archived 1 older memories" in agent.memory_summary


def test_compression_does_not_remove_structured_journals():
    agent = build_agent()

    agent.upsert_daily_journal(
        journal=__import__(
            "src.agents.journal_entry",
            fromlist=["JournalEntry"],
        ).JournalEntry(
            day=1,
            summary="Historical journal.",
        )
    )

    agent.memory = [
        build_memory(day=1)
    ]

    JournalSystem().compress_old_memories(
        agent=agent,
        current_day=10,
        raw_memory_retention_days=7,
    )

    assert len(agent.daily_journals) == 1
    assert agent.daily_journals[0].day == 1
