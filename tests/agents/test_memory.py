def test_remember_adds_memory(base_agent, memory_factory):
    memory = memory_factory(
        description="Maya talked with Ethan.",
        participants=["Maya", "Ethan"],
    )

    base_agent.remember(memory)

    assert base_agent.memory == [memory]


def test_get_recent_memories_returns_last_memories(base_agent, memory_factory):
    memories = [
        memory_factory(description=f"Memory {index}")
        for index in range(5)
    ]

    for memory in memories:
        base_agent.remember(memory)

    recent = base_agent.get_recent_memories(limit=2)

    assert [memory.description for memory in recent] == [
        "Memory 3",
        "Memory 4",
    ]


def test_get_memories_about_returns_only_memories_with_other_agent(
    base_agent,
    memory_factory,
):
    ethan_memory = memory_factory(
        description="Talked with Ethan.",
        participants=["Test Agent", "Ethan"],
    )
    carlos_memory = memory_factory(
        description="Talked with Carlos.",
        participants=["Test Agent", "Carlos"],
    )

    base_agent.remember(ethan_memory)
    base_agent.remember(carlos_memory)

    memories_about_ethan = base_agent.get_memories_about("Ethan")

    assert memories_about_ethan == [ethan_memory]


def test_get_relevant_memories_includes_recent_memories_about_listener(
    base_agent,
    memory_factory,
):
    relevant_memory = memory_factory(
        day=5,
        description="Talked with Ethan about the market.",
        participants=["Test Agent", "Ethan"],
        importance=2,
    )
    irrelevant_memory = memory_factory(
        day=5,
        description="Talked with Carlos about the cafe.",
        participants=["Test Agent", "Carlos"],
        importance=3,
    )

    base_agent.remember(relevant_memory)
    base_agent.remember(irrelevant_memory)

    relevant = base_agent.get_relevant_memories(
        other_name="Ethan",
        current_day=6,
        max_age_days=5,
    )

    assert relevant == [relevant_memory]


def test_get_relevant_memories_includes_daily_events(
    base_agent,
    memory_factory,
):
    daily_event_memory = memory_factory(
        day=5,
        memory_type="daily_event",
        description="Town event today: Book Club.",
        participants=[],
        location="library",
        importance=3,
        tags=["event", "book_club", "learning"],
    )

    base_agent.remember(daily_event_memory)

    relevant = base_agent.get_relevant_memories(
        other_name="Ethan",
        current_day=6,
        max_age_days=5,
    )

    assert relevant == [daily_event_memory]


def test_get_relevant_memories_excludes_old_memories(
    base_agent,
    memory_factory,
):
    old_memory = memory_factory(
        day=1,
        description="Old conversation with Ethan.",
        participants=["Test Agent", "Ethan"],
        importance=5,
    )

    base_agent.remember(old_memory)

    relevant = base_agent.get_relevant_memories(
        other_name="Ethan",
        current_day=10,
        max_age_days=5,
    )

    assert relevant == []


def test_get_relevant_memories_sorts_by_importance_day_and_hour(
    base_agent,
    memory_factory,
):
    low_importance_recent = memory_factory(
        day=5,
        hour=18,
        description="Recent but low importance.",
        participants=["Test Agent", "Ethan"],
        importance=1,
    )
    high_importance_old = memory_factory(
        day=4,
        hour=8,
        description="Older but high importance.",
        participants=["Test Agent", "Ethan"],
        importance=3,
    )
    high_importance_recent = memory_factory(
        day=5,
        hour=12,
        description="Recent and high importance.",
        participants=["Test Agent", "Ethan"],
        importance=3,
    )

    base_agent.remember(low_importance_recent)
    base_agent.remember(high_importance_old)
    base_agent.remember(high_importance_recent)

    relevant = base_agent.get_relevant_memories(
        other_name="Ethan",
        current_day=5,
        max_age_days=5,
    )

    assert [memory.description for memory in relevant] == [
        "Recent and high importance.",
        "Older but high importance.",
        "Recent but low importance.",
    ]