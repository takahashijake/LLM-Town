from dataclasses import replace

import pytest

from src.systems.location_growth import LocationTemplate
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def engine(tmp_path, name="state", load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=tmp_path / f"{name}.json",
        logs_dir=tmp_path / f"{name}-logs", simulation_seed=11,
    )


def sustain(instance, first, last):
    for day in range(first, last + 1):
        for agent in instance.agents:
            instance.activity_records.append({
                "type": "activity", "day": day, "agent_id": agent.id,
            })


def test_location_growth_requires_migration_and_sustained_activity(tmp_path):
    instance = engine(tmp_path)
    assert instance.review_location_growth(28).reason == "insufficient_population"
    instance = engine(tmp_path, name="inactive")
    sustain(instance, 8, 14)
    instance.review_town_growth(14)
    assert instance.review_location_growth(28).reason == "insufficient_sustained_activity"
    instance = engine(tmp_path, name="eligible")
    sustain(instance, 8, 14)
    instance.review_town_growth(14)
    sustain(instance, 22, 28)
    review = instance.review_location_growth(28)
    assert review.status == "activated"
    assert [item.id for item in instance.locations].count("community_garden") == 1


def test_location_activation_round_trips_once(tmp_path):
    instance = engine(tmp_path)
    sustain(instance, 8, 14)
    instance.review_town_growth(14)
    sustain(instance, 22, 28)
    instance.review_location_growth(28)
    instance.state.save(instance, 28, 8, day_complete=True)
    resumed = engine(tmp_path, load=True)
    assert [item.id for item in resumed.locations].count("community_garden") == 1
    assert len(resumed.location_growth.activation_records) == 1
    assert len(resumed.location_growth.public_history) == 1


def test_capacity_and_unknown_affinity_fail_closed(tmp_path):
    instance = engine(tmp_path)
    instance.location_growth.policy = replace(
        instance.location_growth.policy, location_capacity=4
    )
    assert "capacity" in instance.review_location_growth(28).reason
    with pytest.raises(ValueError, match="unknown affinity"):
        LocationTemplate.from_dict({
            "id": "x", "location_id": "x", "name": "X",
            "description": "X", "affinities": ["seller"],
        })


def proposed_engine(tmp_path, name):
    instance = engine(tmp_path, name=name)
    sustain(instance, 8, 14)
    instance.review_town_growth(14)
    sustain(instance, 22, 28)
    review = instance.location_growth.review(
        day=28, agents=instance.agents, locations=instance.locations,
        activity_records=instance.activity_records,
    )
    assert review.status == "proposed"
    return instance


def test_activation_rechecks_activity_authority(tmp_path):
    instance = proposed_engine(tmp_path, "stale")
    instance.activity_records = []
    assert instance.activate_pending_location(28) is None
    assert "community_garden" not in {item.id for item in instance.locations}
    assert not instance.location_growth.consumed_template_ids


def test_unexpected_commit_failure_rolls_back_location_and_memory(tmp_path):
    instance = proposed_engine(tmp_path, "rollback")

    def fail_projection(**_kwargs):
        raise RuntimeError("controlled projection failure")

    instance.outcome_memory.project = fail_projection
    assert instance.activate_pending_location(28) is None
    assert "community_garden" not in {item.id for item in instance.locations}
    assert not instance.location_growth.consumed_template_ids
    assert instance.location_growth.activation_records[0].status == "rejected"
    assert not any(
        memory.event_type == "location_opened"
        for agent in instance.agents
        for memory in agent.memory + agent.memory_archive
    )
