from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.agents.relationships import RelationshipManager
from src.simulation.relationship_updater import RelationshipUpdater


def make_agent(name: str) -> Agent:
    return Agent(id=name.lower(), name=name, personality="steady", location_id="cafe")


def make_updater() -> RelationshipUpdater:
    return RelationshipUpdater(RelationshipManager(), ActionSystem())


def test_unseen_counterparts_are_neutral_and_independent():
    alice = make_agent("Alice")

    bob = alice.get_relationship_state("Bob")
    carol = alice.get_relationship_state("Carol")
    bob.trust = 0.5

    assert carol.is_neutral()
    assert alice.get_relationship_state("Bob") is not carol


def test_successful_help_improves_recipient_trust_and_helpfulness():
    alice, bob = make_agent("Alice"), make_agent("Bob")

    result = make_updater().apply_structured_relationship_update(
        day=1, hour=8, speaker=bob, listener=alice,
        action="offer_help", outcome="completed",
    )

    view = alice.get_relationship_state("Bob")
    assert view.trust > 0
    assert view.helpfulness > view.affinity > 0
    assert result["Alice"]["delta"]["helpfulness"] > 0
    assert alice.get_social_memories("Bob")[0].summary == "Bob offered me help."


def test_cooperation_updates_both_private_views():
    alice, bob = make_agent("Alice"), make_agent("Bob")

    make_updater().apply_structured_relationship_update(
        day=1, hour=8, speaker=alice, listener=bob,
        action="cooperate", outcome="completed",
    )

    assert alice.get_relationship_state("Bob").cooperation > 0
    assert bob.get_relationship_state("Alice").cooperation > 0


def test_argument_reduces_affinity_and_increases_hostility():
    alice, bob = make_agent("Alice"), make_agent("Bob")

    make_updater().apply_structured_relationship_update(
        day=1, hour=8, speaker=bob, listener=alice,
        action="argue", outcome="completed",
    )

    view = alice.get_relationship_state("Bob")
    assert view.affinity < 0
    assert view.trust < 0
    assert view.hostility > 0


def test_repeated_interactions_accumulate_and_remain_bounded():
    alice, bob = make_agent("Alice"), make_agent("Bob")
    updater = make_updater()

    for day in range(1, 31):
        updater.apply_structured_relationship_update(
            day=day, hour=8, speaker=bob, listener=alice,
            action="offer_help", outcome="completed",
        )

    view = alice.get_relationship_state("Bob")
    assert view.interaction_count == 30
    assert view.trust == 1.0
    assert view.helpfulness == 1.0
    assert all(-1.0 <= value <= 1.0 for value in (
        view.trust, view.affinity, view.cooperation, view.helpfulness, view.hostility
    ))


def test_counterpart_and_observer_views_do_not_leak():
    alice, bob, carol = (
        make_agent("Alice"), make_agent("Bob"), make_agent("Carol")
    )

    make_updater().apply_structured_relationship_update(
        day=1, hour=8, speaker=bob, listener=alice,
        action="offer_help", outcome="completed",
    )

    assert alice.get_relationship_state("Bob").helpfulness > 0
    assert alice.get_relationship_state("Carol").is_neutral()
    assert carol.get_relationship_state("Bob").is_neutral()


def test_social_memory_is_bounded_and_keeps_most_recent_events():
    alice, bob = make_agent("Alice"), make_agent("Bob")
    updater = make_updater()

    for day in range(1, 13):
        updater.apply_structured_relationship_update(
            day=day, hour=8, speaker=bob, listener=alice,
            action="compliment", outcome="completed",
        )

    memories = alice.social_memories["Bob"]
    assert len(memories) == updater.MEMORY_LIMIT
    assert [memory.day for memory in memories] == list(range(5, 13))
    assert alice.get_social_memories("Bob", limit=3)[0].day == 12


def test_help_after_conflict_gradually_repairs_but_does_not_reset_history():
    alice, bob = make_agent("Alice"), make_agent("Bob")
    updater = make_updater()
    updater.apply_structured_relationship_update(
        day=1, hour=8, speaker=bob, listener=alice,
        action="insult", outcome="completed",
    )
    hostile = alice.get_relationship_state("Bob").decision_value()
    updater.apply_structured_relationship_update(
        day=2, hour=8, speaker=bob, listener=alice,
        action="offer_help", outcome="completed",
    )

    repaired = alice.get_relationship_state("Bob")
    assert repaired.decision_value() > hostile
    assert repaired.hostility > 0
    assert repaired.negative_interactions == 1
    assert repaired.positive_interactions == 1


def test_refusal_memories_preserve_each_agents_perspective():
    alice, bob = make_agent("Alice"), make_agent("Bob")
    make_updater().apply_structured_relationship_update(
        day=1, hour=8, speaker=alice, listener=bob,
        action="ask_for_help", outcome="refused",
    )

    assert alice.get_social_memories("Bob")[0].summary == (
        "Bob refused my request for help."
    )
    assert bob.get_social_memories("Alice")[0].summary == (
        "I refused Alice's request for help."
    )
