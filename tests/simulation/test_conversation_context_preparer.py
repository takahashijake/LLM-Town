from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.agents.intent import AgentIntent
from src.agents.relationships import RelationshipManager
from src.behavior.social_policy import SocialBehaviorPolicy
from src.simulation.conversation_context_preparer import ConversationContextPreparer
from src.simulation.conversation_policy import ConversationPolicy
from src.simulation.intent_system import IntentSystem
from src.simulation.relationship_updater import RelationshipUpdater
from src.simulation.town_arc_system import TownArcSystem
from src.town.daily_event import DailyEvent


class FakeIntentPlanner:
    pass


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


def build_preparer():
    relationships = RelationshipManager()
    actions = ActionSystem()
    social_policy = SocialBehaviorPolicy()
    intent_system = IntentSystem(
        intent_planner=FakeIntentPlanner(),
        agent_intents={},
    )
    conversation_policy = ConversationPolicy(
        actions=actions,
        recent_dialogues=[],
        recent_actions=[],
    )
    relationship_updater = RelationshipUpdater(
        relationships=relationships,
        actions=actions,
    )
    town_arc_system = TownArcSystem(
        town_arcs=[],
        town_arc_change_records=[],
    )

    preparer = ConversationContextPreparer(
        relationships=relationships,
        actions=actions,
        social_policy=social_policy,
        intent_system=intent_system,
        conversation_policy=conversation_policy,
        relationship_updater=relationship_updater,
        town_arc_system=town_arc_system,
    )

    return preparer, relationships


def test_prepare_conversation_context_builds_relationship_and_action_setup():
    preparer, relationships = build_preparer()

    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    relationships.change_score("Maya", "Ethan", 4)

    setup = preparer.prepare_conversation_context(
        location_id="library",
        speaker=speaker,
        listener=listener,
        current_day=2,
        current_daily_event=None,
        agent_intents={},
        relationship_events=[],
    )

    assert setup["old_score"] == 4
    assert setup["old_relationship_label"] == "friendly"

    assert setup["allowed_actions"] == [
        "chat",
        "compliment",
        "offer_help",
        "ask_for_help",
        "cooperate",
        "apologize",
        "argue",
        "share_rumor",
    ]

    assert setup["speaker_intent"] is None
    assert setup["listener_intent"] is None
    assert setup["recent_relationship_events"] == []
    assert setup["relationship_history"] == []

    assert setup["suggested_action"] in setup["arc_adjusted_weights"]

    context = setup["context"]

    assert context["speaker"] == "Maya"
    assert context["listener"] == "Ethan"
    assert context["location"] == "library"
    assert context["relationship_label"] == "friendly"
    assert context["relationship_score"] == 4
    assert context["allowed_actions"] == setup["allowed_actions"]
    assert context["suggested_action"] == setup["suggested_action"]


def test_prepare_conversation_context_applies_speaker_intent_weights():
    preparer, relationships = build_preparer()

    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    speaker_intent = AgentIntent(
        agent_name="Maya",
        intent_type="investigate",
        description="Maya wants to gather information.",
        created_day=1,
        expires_day=3,
        priority=2,
        target_agent=None,
        target_location="library",
    )

    setup = preparer.prepare_conversation_context(
        location_id="library",
        speaker=speaker,
        listener=listener,
        current_day=2,
        current_daily_event=None,
        agent_intents={
            "Maya": speaker_intent,
        },
        relationship_events=[],
    )

    assert setup["speaker_intent"] == speaker_intent
    assert setup["listener_intent"] is None

    assert setup["intent_adjusted_weights"]["ask_for_help"] == (
        setup["base_action_weights"]["ask_for_help"] + 3
    )
    assert setup["intent_adjusted_weights"]["share_rumor"] == (
        setup["base_action_weights"]["share_rumor"] + 2
    )
    assert setup["intent_adjusted_weights"]["chat"] == (
        setup["base_action_weights"]["chat"] + 1
    )

    assert setup["context"]["speaker_intent"] == speaker_intent.to_dict()


def test_prepare_conversation_context_includes_daily_event_context():
    preparer, relationships = build_preparer()

    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    daily_event = DailyEvent(
        id="library_fundraiser",
        name="Library Fundraiser",
        description="The library is raising money for repairs.",
        location_id="library",
        tags=["library", "community"],
    )

    setup = preparer.prepare_conversation_context(
        location_id="library",
        speaker=speaker,
        listener=listener,
        current_day=2,
        current_daily_event=daily_event,
        agent_intents={},
        relationship_events=[],
    )

    assert setup["context"]["daily_event"] == {
        "id": "library_fundraiser",
        "name": "Library Fundraiser",
        "description": "The library is raising money for repairs.",
        "location_id": "library",
        "tags": ["library", "community"],
    }