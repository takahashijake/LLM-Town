from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.agents.relationships import RelationshipManager
from src.simulation.relationship_updater import RelationshipUpdater


def build_agent(name: str) -> Agent:
    return Agent(
        id=f"agent_{name.lower()}",
        name=name,
        personality="curious",
        location_id="market",
        occupation="resident",
        goals=[],
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
    )


def build_relationship_updater():
    return RelationshipUpdater(
        relationships=RelationshipManager(),
        actions=ActionSystem(),
    )


def test_record_relationship_event_can_be_retrieved_for_pair():
    updater = build_relationship_updater()

    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    relationship_events = []

    event = updater.create_relationship_event(
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

    updater.record_relationship_event(
        relationship_events=relationship_events,
        relationship_event=event,
    )

    events = updater.get_recent_relationship_events(
        relationship_events=relationship_events,
        agent_a="Maya",
        agent_b="Ethan",
        limit=3,
    )

    assert len(events) == 1
    assert events[0].agent_a == "Maya"
    assert events[0].agent_b == "Ethan"
    assert events[0].location == "market"
    assert events[0].action == "compliment"
    assert events[0].relationship_change == 1
    assert events[0].relationship_score == 3
    assert events[0].relationship_label == "friendly"
