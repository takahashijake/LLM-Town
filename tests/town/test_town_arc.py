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