from src.town.town_arc import TownArc


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