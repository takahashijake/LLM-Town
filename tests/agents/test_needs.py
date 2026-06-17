from src.agents.agent import Agent


def test_initialize_needs_when_empty():
    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        location_id="town_square",
    )

    agent.initialize_needs()

    assert agent.needs == {
        "social": 50,
        "wealth": 50,
        "knowledge": 50,
    }


def test_initialize_needs_does_not_overwrite_existing_needs():
    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        location_id="town_square",
        needs={
            "social": 20,
            "wealth": 80,
            "knowledge": 40,
        },
    )

    agent.initialize_needs()

    assert agent.needs == {
        "social": 20,
        "wealth": 80,
        "knowledge": 40,
    }


def test_satisfy_need_increases_existing_need():
    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        location_id="town_square",
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
    )

    agent.satisfy_need("social", 10)

    assert agent.needs["social"] == 60


def test_satisfy_need_clamps_at_100():
    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        location_id="town_square",
        needs={
            "social": 95,
            "wealth": 50,
            "knowledge": 50,
        },
    )

    agent.satisfy_need("social", 20)

    assert agent.needs["social"] == 100


def test_satisfy_unknown_need_does_nothing():
    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        location_id="town_square",
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
    )

    agent.satisfy_need("energy", 10)

    assert "energy" not in agent.needs
    assert agent.needs == {
        "social": 50,
        "wealth": 50,
        "knowledge": 50,
    }


def test_decay_needs_decrements_all_needs():
    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        location_id="town_square",
        needs={
            "social": 50,
            "wealth": 40,
            "knowledge": 30,
        },
    )

    agent.decay_needs()

    assert agent.needs["social"] == 49
    assert agent.needs["wealth"] == 39
    assert agent.needs["knowledge"] == 29


def test_decay_needs_clamps_at_zero():
    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        location_id="town_square",
        needs={
            "social": 0,
            "wealth": 1,
            "knowledge": 2,
        },
    )

    agent.decay_needs()

    assert agent.needs["social"] == 0
    assert agent.needs["wealth"] == 0
    assert agent.needs["knowledge"] == 1


def test_get_primary_need_returns_lowest_need():
    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        location_id="town_square",
        needs={
            "social": 70,
            "wealth": 20,
            "knowledge": 50,
        },
    )

    assert agent.get_primary_need() == "wealth"