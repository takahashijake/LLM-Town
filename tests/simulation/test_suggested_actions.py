from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


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