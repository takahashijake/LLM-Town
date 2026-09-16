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
    belief = listener.get_reputation_belief("Maya", "helpfulness")
    assert belief is not None
    assert belief.score > 0


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


def test_apply_conversation_effects_transmits_only_supplied_rumor_claim():
    applier, relationship_updater, conversation_policy = build_applier()
    maya = build_agent("Maya")
    carlos = build_agent("Carlos")
    lena = build_agent("Lena")
    applier.reputation_system.record_direct_action(
        day=1, hour=8, actor=maya, observer=carlos, action="offer_help"
    )
    claim = applier.reputation_system.select_shareable_claim(carlos, lena)

    result = applier.apply_conversation_effects(
        day=2,
        hour=8,
        location_id="library",
        speaker=carlos,
        listener=lena,
        action="share_rumor",
        conversation="From what I saw, Maya seemed helpful.",
        conversation_tags=["conversation", "share_rumor"],
        old_relationship_label="neutral",
        old_score=0,
        relationship_events=[],
        rumor_claim=claim,
    )

    assert result["rumor_transmission"]["target_agent"] == "Maya"
    assert lena.get_reputation_belief("Maya", "helpfulness").source_type == "hearsay"


def test_apply_conversation_effects_does_not_fabricate_missing_rumor_claim():
    applier, relationship_updater, conversation_policy = build_applier()
    speaker = build_agent("Carlos")
    listener = build_agent("Lena")

    result = applier.apply_conversation_effects(
        day=2,
        hour=8,
        location_id="library",
        speaker=speaker,
        listener=listener,
        action="share_rumor",
        conversation="I heard something damaging.",
        conversation_tags=["conversation", "share_rumor"],
        old_relationship_label="neutral",
        old_score=0,
        relationship_events=[],
    )

    assert result["rumor_transmission"] is None
    assert listener.reputation_beliefs == {}


def test_suppressed_semantic_action_is_remembered_but_has_no_effects():
    applier, relationship_updater, conversation_policy = build_applier()
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")
    before_need = speaker.needs["social"]

    result = applier.apply_conversation_effects(
        day=1,
        hour=8,
        location_id="library",
        speaker=speaker,
        listener=listener,
        action="offer_help",
        conversation="I can help you with those records.",
        conversation_tags=["conversation", "offer_help"],
        old_relationship_label="neutral",
        old_score=0,
        relationship_events=[],
        effect_eligible=False,
        effect_suppression_reason="action_rate_cap",
    )

    assert result["effect_applied"] is False
    assert result["effect_suppression_reason"] == "action_rate_cap"
    assert relationship_updater.relationships.get_score("Maya", "Ethan") == 0
    assert speaker.needs["social"] == before_need
    assert listener.reputation_beliefs == {}
    assert conversation_policy.recent_actions == ["offer_help"]
