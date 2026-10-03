from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from src.systems.growth_proposals import GrowthProposalSystem


class StaticProvider:
    provider_kind = "static-test"

    def __init__(self, resident=None, location=None):
        self.resident = resident
        self.location = location
        self.calls = []

    def propose_resident(self, context):
        self.calls.append(("resident", context))
        if isinstance(self.resident, Exception):
            raise self.resident
        return self.resident

    def propose_location(self, context):
        self.calls.append(("location", context))
        if isinstance(self.location, Exception):
            raise self.location
        return self.location


def config(resident_capacity=1, location_capacity=1):
    return {
        "templates": [{"id": "resident_template_001", "name": "Nora"}],
        "location_growth": {"templates": [{
            "id": "location_template_001", "location_id": "garden",
            "name": "Garden",
        }]},
        "procedural_growth": {"policy": {
            "enabled": True,
            "earliest_proposal_day": 1,
            "review_interval_days": 1,
            "proposal_cooldown_days": 0,
            "resident_proposal_capacity": resident_capacity,
            "location_proposal_capacity": location_capacity,
            "history_limit": resident_capacity + location_capacity or 1,
        }},
    }


def system(provider, *, state=None, resident_capacity=1, location_capacity=1):
    return GrowthProposalSystem.from_config(
        config(resident_capacity, location_capacity),
        agents=[SimpleNamespace(name="Ada")],
        locations=[SimpleNamespace(id="square", name="Town Square")],
        state=state,
        provider=provider,
    )


def context(instance, day=1):
    return instance.build_context(
        completed_day=day,
        agents=[SimpleNamespace(name="Ada")],
        locations=[SimpleNamespace(id="square", name="Town Square")],
        activity_records=[], town_history=[], location_history=[],
    )


def admitted_state():
    provider = StaticProvider(
        resident={"name": "Mira", "personality": "curious", "goals": ["learn"]},
        location={
            "name": "Reading Green", "description": "A quiet shared green.",
            "affinities": ["knowledge", "community"],
        },
    )
    instance = system(provider)
    instance.review(day=1, context=context(instance, 1))
    instance.review(day=2, context=context(instance, 2))
    return instance.to_dict()


def test_admits_canonical_resident_and_location_templates():
    state = admitted_state()
    assert [row["id"] for row in state["records"]] == [
        "growth-proposal:0001", "growth-proposal:0002",
    ]
    assert state["resident_templates"] == [{
        "id": "generated_resident_template_0001",
        "name": "Mira",
        "personality": "curious",
        "goals": ["learn"],
        "initial_needs": {"knowledge": 50, "social": 50, "wealth": 50},
        "initial_location_policy": "arrival_location",
    }]
    assert state["location_templates"][0]["location_id"] == "generated_location_0001"


@pytest.mark.parametrize("candidate", [
    {"name": "Alex", "starting_balance": 100000},
    {"agent_id": "agent_001", "name": "Clone", "personality": "x", "goals": ["x"]},
    '{bad json',
    {"name": "", "personality": "x", "goals": ["x"]},
    {"name": "Nora", "personality": "x", "goals": ["x"]},
])
def test_hostile_resident_candidates_fail_closed(candidate):
    instance = system(StaticProvider(resident=candidate), location_capacity=0)
    record = instance.review(day=1, context=context(instance))
    assert record.status == "rejected"
    assert not instance.resident_templates
    assert instance.next_resident_template_sequence == 1


@pytest.mark.parametrize("candidate", [
    {"name": "Market", "description": "x", "affinities": ["social"], "seller": True},
    {"name": "Courthouse", "description": "x", "affinities": ["justice"]},
    {"name": "Garden", "description": "x", "affinities": ["social"]},
])
def test_hostile_location_candidates_fail_closed(candidate):
    instance = system(StaticProvider(location=candidate), resident_capacity=0)
    record = instance.review(day=1, context=context(instance))
    assert record.status == "rejected"
    assert not instance.location_templates


def test_provider_exception_is_bounded_and_audited():
    provider = StaticProvider(resident=RuntimeError("boom"))
    instance = system(provider, location_capacity=0)
    assert instance.review(day=1, context=context(instance)).status == "rejected"
    assert instance.review(day=2, context=context(instance, 2)) is None
    assert len(provider.calls) == 1
    assert instance.next_proposal_sequence == 2


def test_context_is_aggregate_and_bounded():
    instance = system(StaticProvider())
    built = instance.build_context(
        completed_day=20,
        agents=[SimpleNamespace(name=f"Person {index}") for index in range(140)],
        locations=[SimpleNamespace(id=f"place-{index}", name=f"Place {index}") for index in range(140)],
        activity_records=[
            {"type": "activity", "day": day, "agent_id": "a", "description": "secret"}
            for day in range(1, 21)
        ],
        town_history=[], location_history=[],
    )
    assert len(built["resident_names"]) == 100
    assert len(built["active_locations"]) == 100
    assert len(built["recent_aggregate_activity"]) == 7
    assert "secret" not in json.dumps(built)


@pytest.mark.parametrize("mutation", [
    lambda data: data["records"][0].__setitem__("id", "growth-proposal:9999"),
    lambda data: data["records"][0].__setitem__("kind", "location"),
    lambda data: data["records"][0].__setitem__("status", "rejected"),
    lambda data: data["records"][0]["canonical_payload"].__setitem__("name", "Tampered"),
    lambda data: data["records"][0].__setitem__("canonical_payload_hash", "0" * 64),
    lambda data: data["records"][0].__setitem__("generated_template_id", "generated_resident_template_0002"),
    lambda data: data["resident_templates"][0].__setitem__("personality", "tampered"),
    lambda data: data.__setitem__("next_proposal_sequence", 1),
    lambda data: data.__setitem__("next_resident_template_sequence", 1),
    lambda data: data["resident_templates"].clear(),
])
def test_tampered_persistence_fails_closed(mutation):
    data = deepcopy(admitted_state())
    mutation(data)
    with pytest.raises((KeyError, TypeError, ValueError)):
        system(StaticProvider(), state=data)


def test_resume_reconstructs_without_provider_call():
    data = admitted_state()
    provider = StaticProvider(resident=AssertionError("must not be called"))
    restored = system(provider, state=data)
    assert restored.to_dict() == data
    assert restored.review(day=3, context=context(restored, 3)) is None
    assert provider.calls == []
