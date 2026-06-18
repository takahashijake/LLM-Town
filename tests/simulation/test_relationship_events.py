from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def build_engine():
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )


def get_agent(engine, name):
    return next(agent for agent in engine.agents if agent.name == name)


def test_record_relationship_event_can_be_retrieved_for_pair():
    engine = build_engine()

    speaker = get_agent(engine, "Maya")
    listener = get_agent(engine, "Ethan")

    event = engine.create_relationship_event(
        day=2,
        hour=12,
        location_id="market",
        speaker=speaker,
        listener=listener,
        action="compliment",
        relationship_change=1,
        new_score=3,
        relationship_label="friendly",
        conversation="You handled that really well.",
        tags=["conversation", "compliment"],
    )

    engine.record_relationship_event(event)

    events = engine.get_recent_relationship_events(
        "Maya",
        "Ethan",
        limit=3,
    )

    assert len(events) == 1
    assert events[0].action == "compliment"
    assert events[0].relationship_change == 1
    assert events[0].relationship_score == 3
    assert events[0].relationship_label == "friendly"