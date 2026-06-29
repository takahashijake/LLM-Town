from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.simulation.conversation_policy import ConversationPolicy


def build_agent(name: str) -> Agent:
    agent = Agent(
        id=f"agent_{name.lower()}",
        name=name,
        personality="curious",
        location_id="cafe",
        occupation="accountant",
        goals=[],
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
    )
    agent.current_activity = "Review records and numbers"
    return agent


def build_policy(
    recent_dialogues=None,
    recent_actions=None,
) -> ConversationPolicy:
    return ConversationPolicy(
        actions=ActionSystem(),
        recent_dialogues=recent_dialogues or [],
        recent_actions=recent_actions or [],
    )


def test_remember_dialogue_normalizes_and_limits_history():
    policy = build_policy()

    policy.remember_dialogue("  Hello Town  ", limit=2)
    policy.remember_dialogue("Second line", limit=2)
    policy.remember_dialogue("Third line", limit=2)

    assert policy.recent_dialogues == [
        "second line",
        "third line",
    ]


def test_is_repeated_dialogue_detects_normalized_text():
    policy = build_policy(
        recent_dialogues=[
            "the town feels busy today.",
        ],
    )

    assert policy.is_repeated_dialogue("  The Town Feels Busy Today. ")
    assert not policy.is_repeated_dialogue("Something new.")


def test_get_non_repeated_fallback_dialogue_skips_recent_candidate():
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    first_candidate = "I can help with review records and numbers if you need another pair of hands."

    policy = build_policy(
        recent_dialogues=[
            first_candidate.lower(),
        ],
    )

    fallback = policy.get_non_repeated_fallback_dialogue(
        speaker=speaker,
        listener=listener,
        relationship_label="neutral",
        location_id="library",
        suggested_action="offer_help",
    )

    assert fallback != first_candidate
    assert "library" in fallback or "harder" in fallback


def test_remember_action_limits_history():
    policy = build_policy()

    policy.remember_action("chat", limit=2)
    policy.remember_action("argue", limit=2)
    policy.remember_action("offer_help", limit=2)

    assert policy.recent_actions == [
        "argue",
        "offer_help",
    ]


def test_should_cap_action_caps_repeated_share_rumor():
    policy = build_policy(
        recent_actions=[
            "share_rumor",
            "chat",
            "chat",
            "chat",
            "chat",
        ],
    )

    assert policy.should_cap_action("share_rumor")


def test_should_cap_action_never_caps_chat():
    policy = build_policy(
        recent_actions=[
            "argue",
            "argue",
            "argue",
            "argue",
            "argue",
        ],
    )

    assert not policy.should_cap_action("chat")


def test_choose_final_action_trusts_inferred_non_chat_action():
    policy = build_policy()

    action, reason = policy.choose_final_action_with_reason(
        conversation="I can help you with that.",
        parsed_action="chat",
        conversation_tags=[],
        allowed_actions=["chat", "offer_help"],
        inferred_action="offer_help",
    )

    assert action == "offer_help"
    assert reason == "trusted_inferred_non_chat"


def test_choose_final_action_downgrades_rumor_without_marker():
    policy = build_policy()

    action, reason = policy.choose_final_action_with_reason(
        conversation="The town feels busy today.",
        parsed_action="share_rumor",
        conversation_tags=[],
        allowed_actions=["chat", "share_rumor"],
        inferred_action="chat",
    )

    assert action == "chat"
    assert reason == "parsed_rumor_without_marker"


def test_choose_final_action_keeps_rumor_with_marker():
    policy = build_policy()

    action, reason = policy.choose_final_action_with_reason(
        conversation="I heard a rumor about the market.",
        parsed_action="share_rumor",
        conversation_tags=[],
        allowed_actions=["chat", "share_rumor"],
        inferred_action="chat",
    )

    assert action == "share_rumor"
    assert reason == "parsed_rumor_with_marker"


def test_choose_weighted_action_returns_chat_for_empty_weights():
    policy = build_policy()

    assert policy.choose_weighted_action({}) == "chat"
    