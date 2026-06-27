from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.agents.intent import AgentIntent

def build_engine():
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )


def test_choose_suggested_action_returns_chat_when_only_chat_allowed():
    engine = build_engine()

    suggested_action = engine.choose_suggested_action(
        ["chat"],
        "neutral",
    )

    assert suggested_action == "chat"


def test_choose_suggested_action_returns_allowed_action():
    engine = build_engine()

    allowed_actions = ["chat", "compliment", "offer_help"]

    for _ in range(20):
        suggested_action = engine.choose_suggested_action(
            allowed_actions,
            "neutral",
        )

        assert suggested_action in allowed_actions


def test_choose_suggested_action_handles_empty_actions():
    engine = build_engine()

    suggested_action = engine.choose_suggested_action(
        [],
        "neutral",
    )

    assert suggested_action == "chat"


def test_choose_suggested_action_returns_allowed_action_for_neutral():
    engine = build_engine()

    allowed_actions = [
        "chat",
        "compliment",
        "offer_help",
        "ask_for_help",
        "cooperate",
        "share_rumor",
    ]

    for _ in range(20):
        suggested_action = engine.choose_suggested_action(
            allowed_actions,
            "neutral",
        )

        assert suggested_action in allowed_actions


def test_choose_suggested_action_does_not_suggest_cooperate_when_tense_if_not_allowed():
    engine = build_engine()

    allowed_actions = ["chat", "apologize", "argue", "storm_off"]

    for _ in range(20):
        suggested_action = engine.choose_suggested_action(
            allowed_actions,
            "tense",
        )

        assert suggested_action in allowed_actions
        assert suggested_action != "cooperate"

def test_repair_intent_increases_apology_weight_for_target():
    engine = build_engine()

    intent = AgentIntent(
        agent_name="Maya",
        intent_type="repair_relationship",
        target_agent="Carlos",
        target_location=None,
        description="Maya wants to repair her relationship with Carlos.",
        created_day=1,
        expires_day=3,
        priority=5,
    )

    base_weights = {
        "chat": 8,
        "apologize": 1,
        "argue": 2,
        "offer_help": 1,
    }

    adjusted = engine.adjust_action_weights_for_intent(
        weights=base_weights,
        intent=intent,
        listener_name="Carlos",
    )

    assert adjusted["apologize"] > base_weights["apologize"]
    assert adjusted["offer_help"] > base_weights["offer_help"]
    assert adjusted["argue"] < base_weights["argue"]


def test_targeted_intent_does_not_affect_non_target_listener():
    engine = build_engine()

    intent = AgentIntent(
        agent_name="Maya",
        intent_type="repair_relationship",
        target_agent="Carlos",
        target_location=None,
        description="Maya wants to repair her relationship with Carlos.",
        created_day=1,
        expires_day=3,
        priority=5,
    )

    base_weights = {
        "chat": 8,
        "apologize": 1,
        "argue": 2,
        "offer_help": 1,
    }

    adjusted = engine.adjust_action_weights_for_intent(
        weights=base_weights,
        intent=intent,
        listener_name="Lena",
    )

    assert adjusted == base_weights

def test_plain_i_heard_is_not_enough_for_rumor_marker():
    engine = build_engine()

    assert not engine.has_rumor_marker(
        "I heard the poetry readings were really inspiring today."
    )


def test_specific_rumor_marker_is_preserved():
    engine = build_engine()

    assert engine.has_rumor_marker(
        "Someone said the new vendor might be hiding something."
    )
    