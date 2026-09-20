from src.analysis.social_decision_evaluation import _agent, _belief
from src.agents.relationships import RelationshipManager
from src.simulation.conversation_selector import ConversationSelector


def test_reputation_target_adjustment_is_private_bounded_and_directional():
    selector = ConversationSelector(RelationshipManager())
    observer, other, target = _agent("Observer"), _agent("Other"), _agent("Target")
    baseline = selector.get_listener_weights(observer, [target])[0]
    observer.reputation_beliefs[target.name] = {
        "helpfulness": _belief(target.name, 1, "direct_observation", .8)
    }
    positive = selector.get_listener_weights(observer, [target])[0]
    observer.reputation_beliefs[target.name] = {
        "helpfulness": _belief(target.name, -1, "direct_observation", .8)
    }
    negative = selector.get_listener_weights(observer, [target])[0]
    assert negative < baseline < positive
    assert abs(selector.get_reputation_adjustment(observer, target)) <= 2.0
    assert selector.get_listener_weights(other, [target])[0] == baseline


def test_hearsay_is_weaker_than_equal_direct_evidence():
    selector = ConversationSelector(RelationshipManager())
    observer, target = _agent("Observer"), _agent("Target")
    observer.reputation_beliefs[target.name] = {
        "helpfulness": _belief(target.name, 1, "direct_observation", .8)
    }
    direct = selector.get_reputation_adjustment(observer, target)
    observer.reputation_beliefs[target.name] = {
        "helpfulness": _belief(target.name, 1, "hearsay", .6)
    }
    assert 0 < selector.get_reputation_adjustment(observer, target) <= direct
