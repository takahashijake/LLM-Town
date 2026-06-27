from src.town.town_arc import TownArc
from tests.simulation.test_suggested_actions import build_engine 


def test_town_arc_round_trip_dict():
    arc = TownArc(
        id="arc_market_pressure_day_1",
        name="Market Pressure",
        description="Residents are watching market prices.",
        status="active",
        location_id="market",
        involved_agents=["Maya", "Ethan"],
        tags=["market", "business"],
        tension=2,
        progress=1,
        created_day=1,
        updated_day=2,
    )

    restored = TownArc.from_dict(arc.to_dict())

    assert restored == arc
    assert restored.is_active()


def test_resolved_town_arc_is_not_active():
    arc = TownArc(
        id="arc_done",
        name="Resolved Arc",
        description="The issue has settled.",
        status="resolved",
        location_id="town_square",
        involved_agents=[],
        tags=["community"],
        tension=0,
        progress=3,
        created_day=1,
        updated_day=4,
        resolved_day=4,
    )

    assert not arc.is_active()

def test_does_not_create_duplicate_active_community_arc():
    engine = build_engine()

    engine.town_arcs = [
        TownArc(
            id="arc_community_project_day_1",
            name="Community Project",
            description="Residents are working together.",
            status="active",
            location_id="town_square",
            involved_agents=[],
            tags=["community"],
            tension=1,
            progress=0,
            created_day=1,
            updated_day=1,
        )
    ]

    class FakeDailyEvent:
        tags = ["community", "social"]
        id = "town_cleanup"
        name = "Town Cleanup"
        description = "Volunteers are cleaning the town square."
        location_id = "town_square"

    new_arc = engine.create_town_arc_from_daily_event(
        day=2,
        daily_event=FakeDailyEvent(),
    )

    assert new_arc is None

def test_creates_community_project_from_community_event():
    engine = build_engine()

    class FakeDailyEvent:
        tags = ["community", "social"]
        id = "town_cleanup"
        name = "Town Cleanup"
        description = "Volunteers are cleaning the town square."
        location_id = "town_square"

    arc = engine.create_town_arc_from_daily_event(
        day=1,
        daily_event=FakeDailyEvent(),
    )

    assert arc is not None
    assert arc.name == "Community Project"
    assert arc.location_id == "town_square"


def test_creates_public_questions_from_learning_event():
    engine = build_engine()

    class FakeDailyEvent:
        tags = ["learning", "social"]
        id = "book_club"
        name = "Book Club"
        description = "Residents are discussing a new book."
        location_id = "library"

    arc = engine.create_town_arc_from_daily_event(
        day=1,
        daily_event=FakeDailyEvent(),
    )

    assert arc is not None
    assert arc.name == "Public Questions"
    assert arc.location_id == "library"


def test_creates_market_pressure_from_market_event():
    engine = build_engine()

    class FakeDailyEvent:
        tags = ["market", "business"]
        id = "farmers_market"
        name = "Farmers Market"
        description = "Vendors are selling goods."
        location_id = "market"

    arc = engine.create_town_arc_from_daily_event(
        day=1,
        daily_event=FakeDailyEvent(),
    )

    assert arc is not None
    assert arc.name == "Market Pressure"
    assert arc.location_id == "market"

def test_town_arc_update_memory_only_goes_to_relevant_agents():
    engine = build_engine()

    arc = TownArc(
        id="arc_market_pressure_day_1",
        name="Market Pressure",
        description="Residents are watching market prices.",
        status="active",
        location_id="market",
        involved_agents=[],
        tags=["market", "business", "wealth"],
        tension=2,
        progress=1,
        created_day=1,
        updated_day=2,
    )

    for agent in engine.agents:
        agent.location_id = "library"
        agent.current_activity_tags = []

    engine.agents[0].location_id = "market"

    before_counts = {
        agent.name: len(agent.memory)
        for agent in engine.agents
    }

    engine.remember_town_arc_for_all_agents(
        day=2,
        arc=arc,
        reason="updated",
    )

    after_counts = {
        agent.name: len(agent.memory)
        for agent in engine.agents
    }

    assert after_counts[engine.agents[0].name] == before_counts[engine.agents[0].name] + 1

    for agent in engine.agents[1:]:
        assert after_counts[agent.name] == before_counts[agent.name]

def test_constructive_conversation_advances_relevant_town_arc():
    engine = build_engine()

    arc = TownArc(
        id="arc_community_project_day_1",
        name="Community Project",
        description="Residents are working together.",
        status="active",
        location_id="town_square",
        involved_agents=[],
        tags=["community", "volunteer", "social"],
        tension=2,
        progress=0,
        created_day=1,
        updated_day=1,
    )

    engine.town_arcs = [arc]
    speaker = engine.agents[0]
    listener = engine.agents[1]

    engine.apply_conversation_to_town_arcs(
        day=2,
        location_id="town_square",
        speaker=speaker,
        listener=listener,
        action="cooperate",
        conversation_tags=["community", "cooperate"],
    )

    assert arc.progress == 1
    assert arc.tension == 1
    assert speaker.name in arc.involved_agents
    assert listener.name in arc.involved_agents
    assert arc.updated_day == 2


def test_irrelevant_conversation_does_not_change_town_arc():
    engine = build_engine()

    arc = TownArc(
        id="arc_market_pressure_day_1",
        name="Market Pressure",
        description="Residents are watching market prices.",
        status="active",
        location_id="market",
        involved_agents=[],
        tags=["market", "business", "wealth"],
        tension=2,
        progress=0,
        created_day=1,
        updated_day=1,
    )

    engine.town_arcs = [arc]
    speaker = engine.agents[0]
    listener = engine.agents[1]

    engine.apply_conversation_to_town_arcs(
        day=2,
        location_id="library",
        speaker=speaker,
        listener=listener,
        action="cooperate",
        conversation_tags=["learning"],
    )

    assert arc.progress == 0
    assert arc.tension == 2
    assert arc.involved_agents == []
    assert arc.updated_day == 1


def test_destabilizing_conversation_increases_relevant_arc_tension():
    engine = build_engine()

    arc = TownArc(
        id="arc_market_pressure_day_1",
        name="Market Pressure",
        description="Residents are watching market prices.",
        status="active",
        location_id="market",
        involved_agents=[],
        tags=["market", "business", "wealth"],
        tension=2,
        progress=0,
        created_day=1,
        updated_day=1,
    )

    engine.town_arcs = [arc]
    speaker = engine.agents[0]
    listener = engine.agents[1]

    engine.apply_conversation_to_town_arcs(
        day=2,
        location_id="market",
        speaker=speaker,
        listener=listener,
        action="share_rumor",
        conversation_tags=["market", "share_rumor"],
    )

    assert arc.progress == 0
    assert arc.tension == 3
    assert speaker.name in arc.involved_agents
    assert listener.name in arc.involved_agents

    