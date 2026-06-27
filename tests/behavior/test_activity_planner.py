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

def test_location_intent_can_be_prioritized_before_daily_event(monkeypatch):
    planner = ActivityPlanner()

    class FakeAgent:
        name = "Lena"
        occupation = "community organizer"
        personality = "helpful"
        goals = ["help the town"]

        def initialize_needs(self):
            self.needs = {
                "social": 50,
                "wealth": 50,
                "knowledge": 50,
            }

        def get_primary_need(self):
            return "social"

    class FakeIntent:
        intent_type = "socialize"
        target_location = "cafe"
        description = "Lena wants to spend time with other residents."

    class FakeDailyEvent:
        id = "town_cleanup"
        name = "Town Cleanup"
        description = "Volunteers are cleaning the town square."
        location_id = "town_square"
        tags = ["volunteer", "cleanup"]

    monkeypatch.setattr("random.random", lambda: 0.0)

    activity = planner.choose_activity(
        agent=FakeAgent(),
        location_ids=["cafe", "town_square", "library", "market"],
        current_day=1,
        hour=8,
        daily_event=FakeDailyEvent(),
        current_intent=FakeIntent(),
    )

    assert activity.id == "intent_socialize"
    assert activity.location_id == "cafe"
    assert "intent" in activity.tags
    assert "socialize" in activity.tags

def test_daily_event_can_happen_when_intent_not_prioritized(monkeypatch):
    planner = ActivityPlanner()

    class FakeAgent:
        name = "Lena"
        occupation = "community organizer"
        personality = "helpful"
        goals = ["help the town"]

        def initialize_needs(self):
            self.needs = {
                "social": 50,
                "wealth": 50,
                "knowledge": 50,
            }

        def get_primary_need(self):
            return "social"

    class FakeIntent:
        intent_type = "socialize"
        target_location = "cafe"
        description = "Lena wants to spend time with other residents."

    class FakeDailyEvent:
        id = "town_cleanup"
        name = "Town Cleanup"
        description = "Volunteers are cleaning the town square."
        location_id = "town_square"
        tags = ["volunteer", "cleanup"]

    random_values = iter([
        0.99,  # do not prioritize intent before event
        0.0,   # attend relevant daily event
    ])

    monkeypatch.setattr("random.random", lambda: next(random_values))

    activity = planner.choose_activity(
        agent=FakeAgent(),
        location_ids=["cafe", "town_square", "library", "market"],
        current_day=1,
        hour=8,
        daily_event=FakeDailyEvent(),
        current_intent=FakeIntent(),
    )

    assert activity.id == "attend_event"
    assert activity.location_id == "town_square"

def test_investigate_intent_priority_before_event_is_not_too_high(monkeypatch):
    planner = ActivityPlanner()

    class FakeIntent:
        intent_type = "investigate"
        target_location = "library"
        description = "Maya wants to gather information."

    monkeypatch.setattr("random.random", lambda: 0.25)

    assert not planner.should_prioritize_intent_before_event(FakeIntent())


def test_socialize_intent_priority_before_event_still_can_happen(monkeypatch):
    planner = ActivityPlanner()

    class FakeIntent:
        intent_type = "socialize"
        target_location = "cafe"
        description = "Lena wants to spend time with residents."

    monkeypatch.setattr("random.random", lambda: 0.30)

    assert planner.should_prioritize_intent_before_event(FakeIntent())