from src.agents.agent import Agent
from src.agents.memory import Memory


def make_memory(day: int, importance: int = 1) -> Memory:
    return Memory(
        day=day,
        hour=8,
        type="conversation",
        description=f"Memory from day {day}",
        participants=["Maya", "Ethan"],
        location="cafe",
        importance=importance,
        sentiment=0,
        tags=["conversation"],
    )


def test_agent_memory_is_pruned_to_limit():
    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        location_id="cafe",
    )

    for day in range(20):
        agent.remember(make_memory(day), active_memory_limit=10)

    assert len(agent.memory) == 10
    assert len(agent.memory_archive) == 10


def test_important_memories_survive_pruning():
    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        location_id="cafe",
    )

    for day in range(20):
        importance = 5 if day == 0 else 1
        agent.remember(make_memory(day, importance), active_memory_limit=10)

    descriptions = [memory.description for memory in agent.memory]

    assert "Memory from day 0" in descriptions


def test_archived_memories_can_be_summarized():
    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        location_id="cafe",
    )

    for day in range(20):
        agent.memory_archive.append(make_memory(day))

    agent.summarize_archived_memories(max_archive_size=5)

    assert len(agent.memory_archive) == 5
    assert "Archived 15 older memories" in agent.memory_summary