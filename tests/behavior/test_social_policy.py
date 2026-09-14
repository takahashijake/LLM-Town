from src.agents.relationship_event import RelationshipEvent
from src.behavior.social_policy import SocialBehaviorPolicy
from src.systems.reputation import ReputationBelief, ReputationEvidence


def make_event(
    action,
    relationship_change,
    score=0,
):
    return RelationshipEvent(
        day=1,
        hour=8,
        agent_a="Maya",
        agent_b="Carlos",
        action=action,
        relationship_change=relationship_change,
        relationship_score=score,
        relationship_label="neutral",
        description="Test relationship event.",
        location="market",
        tags=["conversation", action],
        conversation="Test conversation.",
    )


def test_positive_history_increases_positive_action_weights():
    policy = SocialBehaviorPolicy()

    weights = policy.get_action_weights(
        allowed_actions=[
            "chat",
            "compliment",
            "offer_help",
            "cooperate",
            "ask_for_help",
            "argue",
        ],
        relationship_label="neutral",
        recent_events=[
            make_event("compliment", 1),
            make_event("offer_help", 1),
        ],
    )

    assert weights["compliment"] > 1
    assert weights["offer_help"] > 2
    assert weights["cooperate"] > 1
    assert weights["argue"] == 1


def test_negative_history_increases_repair_or_conflict_weights():
    policy = SocialBehaviorPolicy()

    weights = policy.get_action_weights(
        allowed_actions=[
            "chat",
            "compliment",
            "offer_help",
            "cooperate",
            "apologize",
            "argue",
        ],
        relationship_label="neutral",
        recent_events=[
            make_event("argue", -1),
            make_event("share_rumor", -1),
        ],
    )

    assert weights["apologize"] > 0
    assert weights["chat"] > 8
    assert weights["argue"] > 0
    assert weights["compliment"] == 1


def test_no_history_uses_base_neutral_weights():
    policy = SocialBehaviorPolicy()

    weights = policy.get_action_weights(
        allowed_actions=[
            "chat",
            "compliment",
            "offer_help",
            "ask_for_help",
            "cooperate",
            "share_rumor",
        ],
        relationship_label="neutral",
        recent_events=[],
    )

    assert weights == {
        "chat": 8,
        "cooperate": 1,
        "offer_help": 2,
        "ask_for_help": 2,
        "compliment": 1,
        "share_rumor": 1,
    }


def test_policy_never_returns_disallowed_actions():
    policy = SocialBehaviorPolicy()

    weights = policy.get_action_weights(
        allowed_actions=["chat", "argue"],
        relationship_label="neutral",
        recent_events=[
            make_event("compliment", 1),
            make_event("offer_help", 1),
        ],
    )

    assert set(weights).issubset({"chat", "argue"})


def test_reputation_modestly_changes_action_weights_without_adding_actions():
    policy = SocialBehaviorPolicy()
    belief = ReputationBelief(
        target_agent="Carlos",
        dimension="helpfulness",
        evidence=[
            ReputationEvidence(
                evidence_id="help-1",
                value=1,
                confidence=0.9,
                source_type="direct_interaction",
                source_agent="Carlos",
                day=1,
            ),
            ReputationEvidence(
                evidence_id="help-2",
                value=1,
                confidence=0.9,
                source_type="direct_interaction",
                source_agent="Carlos",
                day=2,
            ),
        ],
    )
    weights, deltas = policy.adjust_action_weights_for_reputation(
        {"chat": 8, "ask_for_help": 2, "argue": 1},
        {"helpfulness": belief},
    )

    assert weights == {"chat": 8, "ask_for_help": 3, "argue": 1}
    assert deltas == {"ask_for_help": 1}
