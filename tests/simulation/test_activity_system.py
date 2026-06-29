from src.agents.agent import Agent
from src.behavior.activity import Activity
from src.simulation.activity_system import ActivitySystem


class FakeLogger:
    def __init__(self):
        self.events = []

    def log_event(self, event):
        self.events.append(event)


class FakeActivityPlanner:
    def __init__(self, activity):
        self.activity = activity
        self.calls = []

    def choose_activity(
        self,
        agent,
        location_ids,
        current_day,
        hour,
        daily_event,
        current_intent,
    ):
        self.calls.append(
            {
                "agent": agent.name,
                "location_ids": location_ids,
                "current_day": current_day,
                "hour": hour,
                "daily_event": daily_event,
                "current_intent": current_intent,
            }
        )

        return self.activity


def build_agent(name: str = "Maya") -> Agent:
    return Agent(
        id=f"agent_{name.lower()}",
        name=name,
        personality="curious",
        location_id="library",
        occupation="journalist",
        goals=[],
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
    )


def build_activity() -> Activity:
    return Activity(
        id="review_records",
        name="Review records and numbers",
        location_id="library",
        reason="Maya wants reliable information.",
        tags=["knowledge", "accounting"],
    )


def test_get_activity_need_effects_combines_tag_effects():
    system = ActivitySystem(
        activity_planner=FakeActivityPlanner(build_activity()),
        logger=FakeLogger(),
        activity_records=[],
    )

    activity = Activity(
        id="market_social",
        name="Talk at market",
        location_id="market",
        reason="Maya wants to learn about vendors.",
        tags=["market", "business", "social", "knowledge"],
    )

    assert system.get_activity_need_effects(activity) == {
        "wealth": 3,
        "social": 2,
        "knowledge": 2,
    }


def test_log_activity_event_appends_record_and_logs_event():
    logger = FakeLogger()
    records = []

    system = ActivitySystem(
        activity_planner=FakeActivityPlanner(build_activity()),
        logger=logger,
        activity_records=records,
    )

    agent = build_agent()
    activity = build_activity()

    system.log_activity_event(
        day=2,
        hour=12,
        agent=agent,
        activity=activity,
    )

    assert len(records) == 1
    assert records[0]["type"] == "activity"
    assert records[0]["agent"] == "Maya"
    assert records[0]["activity_id"] == "review_records"
    assert records[0]["activity_name"] == "Review records and numbers"
    assert records[0]["location"] == "library"
    assert records[0]["tags"] == ["knowledge", "accounting"]

    assert logger.events == records


def test_run_agent_activities_sets_activity_logs_and_satisfies_needs():
    activity = build_activity()
    logger = FakeLogger()
    planner = FakeActivityPlanner(activity)
    records = []

    system = ActivitySystem(
        activity_planner=planner,
        logger=logger,
        activity_records=records,
    )

    agent = build_agent()
    starting_knowledge = agent.needs["knowledge"]

    system.run_agent_activities(
        agents=[agent],
        location_ids=["library", "market"],
        day=3,
        hour=8,
        current_daily_event=None,
        agent_intents={},
    )

    assert planner.calls[0]["agent"] == "Maya"
    assert planner.calls[0]["location_ids"] == ["library", "market"]
    assert planner.calls[0]["current_day"] == 3
    assert planner.calls[0]["hour"] == 8

    assert agent.current_activity == "Review records and numbers"
    assert agent.current_activity_reason == "Maya wants reliable information."
    assert agent.current_activity_tags == ["knowledge", "accounting"]

    assert agent.needs["knowledge"] > starting_knowledge

    assert len(records) == 1
    assert records[0]["activity_name"] == "Review records and numbers"
    assert logger.events == records
    