from dataclasses import replace

import pytest

from src.agents.agent import Agent
from src.systems.economy import EconomicAccount, EconomySystem
from src.systems.town_growth import (
    ResidentTemplate,
    TownGrowthPolicy,
    TownGrowthSystem,
)
from src.town.location import Location


def policy(**changes):
    base = TownGrowthPolicy(
        resident_capacity=5,
        earliest_migration_day=7,
        review_interval_days=7,
        migration_cooldown_days=30,
        arrival_location_id="square",
        settlement_source_account_id="town",
        settlement_grant=25,
        recent_activity_window_days=3,
        minimum_active_residents_per_day=2,
    )
    return replace(base, **changes)


def template(name="Newcomer"):
    return ResidentTemplate.from_dict({
        "id": "template-1",
        "name": name,
        "personality": "careful",
        "goals": ["build close friendships"],
        "initial_needs": {"social": 50, "wealth": 50, "knowledge": 50},
    })


def authorities():
    agents = [
        Agent("agent_001", "One", "calm", "square"),
        Agent("agent_004", "Four", "calm", "square"),
    ]
    locations = [Location("square", "Square", "Public square")]
    economy = EconomySystem(
        accounts=[EconomicAccount("town", "system", "town", 100)],
        employments=[],
    )
    activity = [
        {"type": "activity", "day": day, "agent_id": agent.id}
        for day in range(5, 8) for agent in agents
    ]
    return agents, locations, economy, activity


def test_eligible_review_allocates_stable_noncolliding_identity_once():
    agents, locations, economy, activity = authorities()
    system = TownGrowthSystem(
        policy(), [template()], next_resident_sequence=1
    )
    review = system.review(
        day=7, agents=agents, locations=locations,
        activity_records=activity, economy=economy,
    )
    replay = system.review(
        day=7, agents=agents, locations=locations,
        activity_records=activity, economy=economy,
    )
    assert review.status == "proposed"
    assert review.migration_id == "migration:0001"
    assert review.agent_id == "agent_002"
    assert replay.migration_id == review.migration_id
    assert len(system.migration_records) == 1


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"earliest_migration_day": 8}, "before_earliest_migration_day"),
        ({"resident_capacity": 2}, "resident_capacity_reached"),
        ({"settlement_grant": 101}, "insufficient_settlement_funds"),
    ],
)
def test_readiness_gates_fail_closed(change, reason):
    agents, locations, economy, activity = authorities()
    system = TownGrowthSystem(policy(**change), [template()])
    review = system.review(
        day=7, agents=agents, locations=locations,
        activity_records=activity, economy=economy,
    )
    assert review.status == "waiting"
    assert review.reason == reason
    assert system.migration_records == []


def test_old_name_only_activity_is_not_guessed_into_authority():
    agents, locations, economy, _ = authorities()
    activity = [
        {"type": "activity", "day": day, "agent": agent.name}
        for day in range(5, 8) for agent in agents
    ]
    review = TownGrowthSystem(policy(), [template()]).review(
        day=7, agents=agents, locations=locations,
        activity_records=activity, economy=economy,
    )
    assert review.reason == "insufficient_sustained_activity"


def test_malformed_template_and_future_state_fail_closed(tmp_path):
    with pytest.raises(ValueError):
        ResidentTemplate.from_dict({"id": "bad", "name": "Bad"})

    config = tmp_path / "growth.json"
    config.write_text(
        '{"policy":{"resident_capacity":5,"earliest_migration_day":1,'
        '"review_interval_days":1,"migration_cooldown_days":0,'
        '"arrival_location_id":"square","settlement_source_account_id":"town",'
        '"settlement_grant":1,"recent_activity_window_days":1,'
        '"minimum_active_residents_per_day":1},"templates":[]}'
    )
    with pytest.raises(ValueError, match="unsupported town growth"):
        TownGrowthSystem.from_config(
            config, [], {"schema_version": 999}
        )
    with pytest.raises(ValueError, match="unsupported town growth"):
        TownGrowthSystem.from_config(config, [], {})


def test_processed_review_key_survives_bounded_review_history():
    agents, locations, economy, activity = authorities()
    system = TownGrowthSystem(
        policy(resident_capacity=2, earliest_migration_day=1,
               review_interval_days=1),
        [template()],
    )
    for day in range(1, system.REVIEW_HISTORY_LIMIT + 3):
        system.review(
            day=day, agents=agents, locations=locations,
            activity_records=activity, economy=economy,
        )

    assert all(item.day != 1 for item in system.review_history)
    history_size = len(system.review_history)
    replay = system.review(
        day=1, agents=agents, locations=locations,
        activity_records=activity, economy=economy,
    )
    assert replay.reason == "review_already_processed"
    assert len(system.review_history) == history_size


def test_stale_sequences_are_advanced_past_persisted_records():
    agents, _locations, _economy, _activity = authorities()
    event_key = "migration-review:day:14"
    state = {
        "schema_version": 1,
        "next_migration_sequence": 1,
        "next_resident_sequence": 1,
        "review_history": [{
            "event_key": event_key,
            "day": 14,
            "status": "rejected",
            "reason": "activation_failed",
            "migration_id": "migration:0007",
            "template_id": "resident_template_001",
            "agent_id": "agent_099",
        }],
        "migration_records": [{
            "id": "migration:0007",
            "event_key": event_key,
            "template_id": "resident_template_001",
            "agent_id": "agent_099",
            "review_day": 14,
            "arrival_location_id": "town_square",
            "status": "rejected",
            "reason": "activation_failed",
            "activation_day": None,
            "settlement_transaction_id": None,
        }],
        "last_successful_activation_day": None,
        "processed_event_keys": [event_key],
        "consumed_template_ids": [],
        "public_history": [],
    }

    system = TownGrowthSystem.from_config(
        "data/town_growth.json", agents, state
    )
    assert system.next_migration_sequence == 8
    assert system.next_resident_sequence == 100


def test_malformed_activated_history_fails_closed():
    agents, _locations, _economy, _activity = authorities()
    event_key = "migration-review:day:14"
    state = {
        "schema_version": 1,
        "review_history": [{
            "event_key": event_key,
            "day": 14,
            "status": "activated",
            "reason": "activated",
            "migration_id": "migration:0001",
            "template_id": "resident_template_001",
            "agent_id": "agent_005",
        }],
        "migration_records": [{
            "id": "migration:0001",
            "event_key": event_key,
            "template_id": "resident_template_001",
            "agent_id": "agent_005",
            "review_day": 14,
            "arrival_location_id": "town_square",
            "status": "activated",
            "reason": "activated",
            "activation_day": 14,
            "settlement_transaction_id": "txn-00000001",
        }],
        "last_successful_activation_day": 14,
        "processed_event_keys": [event_key],
        "consumed_template_ids": ["resident_template_001"],
        "public_history": [],
    }
    with pytest.raises(ValueError, match="public history"):
        TownGrowthSystem.from_config("data/town_growth.json", agents, state)
