from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.agents.relationships import RelationshipManager
from src.simulation.relationship_updater import RelationshipUpdater


def build_agent(name: str) -> Agent:
    return Agent(
        id=f"agent_{name.lower()}",
        name=name,
        personality="curious",
        occupation="resident",
        location_id="cafe",
        goals=[],
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
    )


def build_updater():
    relationships = RelationshipManager()
    actions = ActionSystem()
    updater = RelationshipUpdater(
        relationships=relationships,
        actions=actions,
    )

    return updater, relationships


def test_relationship_updater_creates_event_description():
    updater, _relationships = build_updater()

    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

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

    assert event.agent_a == "Maya"
    assert event.agent_b == "Ethan"
    assert event.action == "compliment"
    assert event.relationship_change == 1
    assert event.relationship_score == 3
    assert "improved by +1" in event.description


def test_relationship_updater_records_and_retrieves_recent_events():
    updater, _relationships = build_updater()

    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    first_event = updater.create_relationship_event(
        day=1,
        hour=8,
        location_id="cafe",
        speaker=speaker,
        listener=listener,
        action="chat",
        relationship_change=1,
        new_score=1,
        relationship_label="neutral",
        conversation="Good morning.",
        tags=["conversation"],
    )

    second_event = updater.create_relationship_event(
        day=2,
        hour=12,
        location_id="market",
        speaker=listener,
        listener=speaker,
        action="argue",
        relationship_change=-1,
        new_score=0,
        relationship_label="neutral",
        conversation="I disagree.",
        tags=["conversation", "argue"],
    )

    relationship_events = []

    updater.record_relationship_event(relationship_events, first_event)
    updater.record_relationship_event(relationship_events, second_event)

    recent_events = updater.get_recent_relationship_events(
        relationship_events=relationship_events,
        agent_a="Maya",
        agent_b="Ethan",
        limit=1,
    )

    assert len(recent_events) == 1
    assert recent_events[0].action == "argue"


def test_relationship_updater_calculates_relationship_change_with_supplied_drift():
    updater, _relationships = build_updater()

    change = updater.calculate_relationship_change(
        action="compliment",
        old_relationship_label="neutral",
        old_relationship_score=0,
        relationship_drift=1,
    )

    assert change == 2


def test_relationship_updater_applies_change_to_manager_and_agents():
    updater, relationships = build_updater()

    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    new_score, label = updater.apply_relationship_change(
        speaker=speaker,
        listener=listener,
        relationship_change=2,
    )

    assert relationships.get_score("Maya", "Ethan") == 2
    assert speaker.relationships["Ethan"] == 2
    assert listener.relationships["Maya"] == 2
    assert new_score == 2
    assert label == "neutral"