from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.agents.relationships import RelationshipManager
from src.simulation.conversation_effects_applier import ConversationEffectsApplier
from src.simulation.conversation_policy import ConversationPolicy
from src.simulation.conversation_recorder import ConversationRecorder
from src.simulation.relationship_updater import RelationshipUpdater
from src.simulation.town_arc_system import TownArcSystem
from src.utils.logger import TownLogger


def build_agent(name: str, location_id: str = "library") -> Agent:
    return Agent(
        id=f"agent_{name.lower()}",
        name=name,
        personality="curious",
        location_id=location_id,
        occupation="resident",
        goals=[],
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
    )


def build_applier():
    actions = ActionSystem()
    relationships = RelationshipManager()
    relationship_updater = RelationshipUpdater(
        relationships=relationships,
        actions=actions,
    )

    # Keep these tests deterministic.
    relationship_updater.get_relationship_change = lambda relationship_label: 0

    town_arc_system = TownArcSystem(
        town_arcs=[],
        town_arc_change_records=[],
    )
    conversation_policy = ConversationPolicy(
        actions=actions,
        recent_dialogues=[],
        recent_actions=[],
    )
    conversation_recorder = ConversationRecorder(
        logger=TownLogger(),
    )

    applier = ConversationEffectsApplier(
        actions=actions,
        relationship_updater=relationship_updater,
        town_arc_system=town_arc_system,
        conversation_recorder=conversation_recorder,
        conversation_policy=conversation_policy,
    )

    return applier, relationship_updater, conversation_policy


def test_apply_conversation_effects_updates_relationship_and_memory():
    applier, relationship_updater, conversation_policy = build_applier()

    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    relationship_events = []

    result = applier.apply_conversation_effects(
        day=1,
        hour=8,
        location_id="library",
        speaker=speaker,
        listener=listener,
        action="compliment",
        conversation="You handled that really well.",
        conversation_tags=["conversation", "compliment", "neutral"],
        old_relationship_label="neutral",
        old_score=0,
        relationship_events=relationship_events,
    )

    assert result["relationship_change"] == 1
    assert result["new_score"] == 1
    assert result["relationship_label"] == "neutral"

    assert relationship_updater.relationships.get_score("Maya", "Ethan") == 1
    assert speaker.relationships["Ethan"] == 1
    assert listener.relationships["Maya"] == 1

    assert len(speaker.memory) == 1
    assert len(listener.memory) == 1
    assert result["memory"] is speaker.memory[0]
    assert result["memory"] is listener.memory[0]

    assert conversation_policy.recent_dialogues == [
        "you handled that really well.",
    ]
    assert conversation_policy.recent_actions == [
        "compliment",
    ]


def test_apply_conversation_effects_records_relationship_event_when_needed():
    applier, relationship_updater, conversation_policy = build_applier()

    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    relationship_events = []

    result = applier.apply_conversation_effects(
        day=1,
        hour=8,
        location_id="library",
        speaker=speaker,
        listener=listener,
        action="argue",
        conversation="I disagree with that plan.",
        conversation_tags=["conversation", "argue", "neutral"],
        old_relationship_label="neutral",
        old_score=0,
        relationship_events=relationship_events,
    )

    assert result["relationship_change"] == -1
    assert result["relationship_event"] is not None
    assert relationship_events == [
        result["relationship_event"],
    ]

    event = result["relationship_event"]

    assert event.day == 1
    assert event.hour == 8
    assert event.location == "library"
    assert event.agent_a == "Maya"
    assert event.agent_b == "Ethan"
    assert event.action == "argue"
    assert event.relationship_change == -1
    assert event.relationship_score == -1
    assert event.relationship_label == "neutral"


def test_apply_conversation_effects_applies_need_effects():
    applier, relationship_updater, conversation_policy = build_applier()

    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    applier.apply_conversation_effects(
        day=1,
        hour=8,
        location_id="library",
        speaker=speaker,
        listener=listener,
        action="ask_for_help",
        conversation="Could you help me understand this?",
        conversation_tags=["conversation", "ask_for_help", "neutral"],
        old_relationship_label="neutral",
        old_score=0,
        relationship_events=[],
    )

    assert speaker.needs["knowledge"] == 52
