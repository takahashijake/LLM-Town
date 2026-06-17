from src.agents.agent import Agent
from src.behavior.planner import ActivityPlanner
from src.town.daily_event import DailyEvent


def test_choose_activity_for_social_need(location_ids):
    planner = ActivityPlanner()
    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        occupation="unemployed",
        location_id="town_square",
        needs={
            "social": 10,
            "wealth": 50,
            "knowledge": 50,
        },
    )

    activity = planner.choose_activity(
        agent=agent,
        location_ids=location_ids,
        current_day=1,
        hour=8,
    )

    assert activity.id in {"socialize", "public_socialize"}
    assert activity.location_id in {"cafe", "town_square"}
    assert "social" in activity.tags


def test_choose_activity_for_wealth_need(location_ids):
    planner = ActivityPlanner()
    agent = Agent(
        id="agent_002",
        name="Carlos",
        personality="ambitious",
        occupation="unemployed",
        location_id="market",
        needs={
            "social": 50,
            "wealth": 10,
            "knowledge": 50,
        },
    )

    activity = planner.choose_activity(
        agent=agent,
        location_ids=location_ids,
        current_day=1,
        hour=8,
    )

    assert activity.id == "seek_work"
    assert activity.location_id == "market"
    assert "wealth" in activity.tags


def test_choose_activity_for_knowledge_need(location_ids):
    planner = ActivityPlanner()
    agent = Agent(
        id="agent_003",
        name="Lena",
        personality="friendly",
        occupation="unemployed",
        location_id="library",
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 10,
        },
    )

    activity = planner.choose_activity(
        agent=agent,
        location_ids=location_ids,
        current_day=1,
        hour=8,
    )

    assert activity.id == "learn"
    assert activity.location_id == "library"
    assert "knowledge" in activity.tags


def test_choose_activity_can_attend_relevant_daily_event(
    monkeypatch,
    location_ids,
):
    monkeypatch.setattr(
        "src.behavior.planner.random.random",
        lambda: 0.0,
    )

    planner = ActivityPlanner()
    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        occupation="local journalist",
        location_id="town_square",
        goals=["learn town secrets"],
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
    )
    daily_event = DailyEvent(
        id="town_hall_meeting",
        name="Town Hall Meeting",
        description="Residents are discussing future plans for the town.",
        location_id="town_square",
        tags=["community", "planning", "social"],
    )

    activity = planner.choose_activity(
        agent=agent,
        location_ids=location_ids,
        current_day=1,
        hour=12,
        daily_event=daily_event,
    )

    assert activity.id == "attend_event"
    assert activity.name == "Attend Town Hall Meeting"
    assert activity.location_id == "town_square"
    assert "event" in activity.tags
    assert "town_hall_meeting" in activity.tags


def test_choose_activity_falls_back_to_wander_when_no_candidates():
    planner = ActivityPlanner()
    agent = Agent(
        id="agent_004",
        name="Noah",
        personality="quiet",
        occupation="unemployed",
        location_id="park",
        needs={
            "social": 10,
            "wealth": 50,
            "knowledge": 50,
        },
    )

    activity = planner.choose_activity(
        agent=agent,
        location_ids=["park"],
        current_day=1,
        hour=8,
    )

    assert activity.id == "wander"
    assert activity.location_id == "park"
    assert "wander" in activity.tags