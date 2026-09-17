import json

import pytest

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.crime import CrimeError, CrimeSystem


def build_engine(tmp_path, *, load_state=False):
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=load_state,
        llm_client=FakeLLMClient(),
        state_path=tmp_path / "state.json",
        logs_dir=tmp_path / "logs",
    )


def arrange(engine, *, lena_at_market=False, maya_at_market=False):
    locations = {
        "agent_001": "market" if maya_at_market else "library",
        "agent_002": "market",
        "agent_003": "market" if lena_at_market else "library",
        "agent_004": "market",
    }
    for agent in engine.agents:
        agent.location_id = locations[agent.id]


def event_key_with_observation(witness_id, observed):
    for number in range(1000):
        key = f"crime-test-{witness_id}-{observed}-{number}"
        if CrimeSystem.witness_observes(key, witness_id) is observed:
            return key
    raise AssertionError("unable to find deterministic witness event key")


def attempt(engine, event_key, **overrides):
    values = {
        "actor_id": "agent_002",
        "source_inventory_id": "inventory:agent:agent_004",
        "good_id": "trade_materials",
        "quantity": 1,
        "day": 2,
        "hour": 12,
        "location_id": "market",
        "event_key": event_key,
        "agents": engine.agents,
    }
    values.update(overrides)
    return engine.crime.attempt_theft(**values)


def authoritative_snapshot(engine):
    return {
        "balances": {
            account_id: account.balance
            for account_id, account in engine.economy.accounts.items()
        },
        "inventories": {
            inventory_id: inventory.to_dict()
            for inventory_id, inventory in engine.materials.inventories.items()
        },
        "ledger": list(engine.economy.ledger),
        "exchanges": list(engine.materials.exchanges),
        "transfers": list(engine.materials.inventory_transfers),
        "incidents": list(engine.crime.incidents),
        "opportunities": list(engine.crime.witness_opportunities),
        "evidence": list(engine.crime.evidence),
    }


def test_valid_theft_transfers_owned_goods_without_money_or_exchange(tmp_path):
    engine = build_engine(tmp_path)
    arrange(engine)
    key = event_key_with_observation("agent_004", False)
    source_id = "inventory:agent:agent_004"
    destination_id = "inventory:agent:agent_002"
    source_before = engine.materials.quantity(source_id, "trade_materials")
    destination_before = engine.materials.quantity(destination_id, "trade_materials")
    balances_before = engine.economy.total_currency()
    ledger_before = len(engine.economy.ledger)

    incident = attempt(engine, key)

    assert incident.victim_id == "agent_004"
    assert incident.actor_id == "agent_002"
    assert incident.total_value == 18
    assert engine.materials.quantity(source_id, "trade_materials") == source_before - 1
    assert engine.materials.quantity(destination_id, "trade_materials") == destination_before + 1
    assert engine.economy.total_currency() == balances_before
    assert len(engine.economy.ledger) == ledger_before
    assert engine.materials.exchanges == []
    transfer = engine.materials.inventory_transfers[-1]
    assert transfer.id == incident.unauthorized_transfer_id
    assert transfer.authorization_type == "unauthorized_theft"
    assert transfer.authorization_id == incident.id
    assert engine.crime.incidents_reconcile_with_materials()
    assert engine.crime.evidence_is_valid()


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"quantity": 999}, "insufficient_stock"),
        ({"quantity": 0}, "invalid_quantity"),
        ({"good_id": "unknown"}, "unknown_good"),
        ({"source_inventory_id": "missing"}, "unknown_inventory"),
        ({"actor_id": "missing"}, "unknown_actor"),
        ({"actor_id": "agent_004"}, "self_theft"),
        ({"location_id": "library"}, "actor_not_present"),
    ],
)
def test_rejected_theft_has_no_partial_authoritative_mutation(
    tmp_path, overrides, code
):
    engine = build_engine(tmp_path)
    arrange(engine)
    before = authoritative_snapshot(engine)
    with pytest.raises(CrimeError) as error:
        attempt(engine, f"reject-{code}", **overrides)
    assert error.value.code == code
    assert authoritative_snapshot(engine) == before
    assert engine.crime.rejected_attempts[-1]["code"] == code


def test_source_property_must_be_at_incident_location(tmp_path):
    engine = build_engine(tmp_path)
    arrange(engine)
    next(agent for agent in engine.agents if agent.id == "agent_004").location_id = "cafe"
    before = authoritative_snapshot(engine)
    with pytest.raises(CrimeError) as error:
        attempt(engine, "source-elsewhere")
    assert error.value.code == "source_not_present"
    assert authoritative_snapshot(engine) == before


def test_duplicate_theft_cannot_replay(tmp_path):
    engine = build_engine(tmp_path)
    arrange(engine)
    attempt(engine, "one-theft")
    before = authoritative_snapshot(engine)
    with pytest.raises(CrimeError) as error:
        attempt(engine, "one-theft")
    assert error.value.code == "duplicate_event"
    assert authoritative_snapshot(engine) == before


def test_witness_opportunity_direct_evidence_and_private_reputation(tmp_path):
    engine = build_engine(tmp_path)
    arrange(engine, lena_at_market=True)
    key = event_key_with_observation("agent_003", True)
    incident = attempt(engine, key)

    assert "agent_003" in incident.potential_witness_ids
    assert "agent_003" in incident.eyewitness_ids
    assert "agent_002" not in incident.potential_witness_ids
    direct = next(
        record for record in engine.crime.knowledge_for_agent("agent_003")
        if record.evidence_type == "eyewitness"
    )
    assert direct.provenance_type == "direct_observation"
    assert direct.originating_observer_id == "agent_003"
    assert direct.transmission_chain == ("agent_003",)
    assert engine.crime.knowledge_for_agent("agent_001") == []
    lena = next(agent for agent in engine.agents if agent.id == "agent_003")
    maya = next(agent for agent in engine.agents if agent.id == "agent_001")
    assert lena.get_reputation_belief("Ethan", "trustworthiness").source_type == "direct_observation"
    assert maya.get_reputation_belief("Ethan", "trustworthiness") is None


def test_absent_agent_cannot_be_given_direct_evidence(tmp_path):
    engine = build_engine(tmp_path)
    arrange(engine)
    incident = attempt(engine, "absent-witness")
    assert "agent_001" not in incident.potential_witness_ids
    assert not any(
        record.holder_agent_id == "agent_001"
        and record.provenance_type == "direct_observation"
        for record in engine.crime.evidence
    )


def test_hearsay_preserves_provenance_and_never_becomes_direct(tmp_path):
    engine = build_engine(tmp_path)
    arrange(engine, lena_at_market=True)
    key = event_key_with_observation("agent_003", True)
    attempt(engine, key)
    direct = next(
        record for record in engine.crime.knowledge_for_agent("agent_003")
        if record.evidence_type == "eyewitness"
    )
    hearsay = engine.crime.share_evidence(
        speaker_id="agent_003",
        listener_id="agent_001",
        evidence_id=direct.id,
        day=2,
        hour=18,
        event_key="lena-tells-maya",
    )
    assert hearsay.evidence_type == "hearsay"
    assert hearsay.provenance_type == "hearsay"
    assert hearsay.source_evidence_id == direct.id
    assert hearsay.originating_observer_id == "agent_003"
    assert hearsay.source_agent_id == "agent_003"
    assert hearsay.transmission_chain == ("agent_003", "agent_001")
    maya = next(agent for agent in engine.agents if agent.id == "agent_001")
    belief = maya.get_reputation_belief("Ethan", "trustworthiness")
    assert belief.source_type == "hearsay"
    assert engine.crime.evidence_is_valid()


def test_victim_can_discover_loss_without_learning_actor(tmp_path):
    engine = build_engine(tmp_path)
    arrange(engine)
    key = event_key_with_observation("agent_004", False)
    incident = attempt(engine, key)
    assert incident.discovery_status == "undiscovered"
    loss = engine.crime.discover_loss(
        incident_id=incident.id,
        victim_id="agent_004",
        day=3,
        hour=8,
        event_key="carlos-counts-stock",
    )
    assert loss.provenance_type == "direct_discovery"
    assert loss.claims_actor is False
    updated = engine.crime.incidents[0]
    assert updated.discovery_status == "victim_discovered_loss"
    assert updated.discovered_by == ("agent_004",)


def test_crime_round_trip_and_resume_replay_guard(tmp_path):
    engine = build_engine(tmp_path)
    arrange(engine, lena_at_market=True)
    key = event_key_with_observation("agent_003", True)
    attempt(engine, key)
    engine.state.save(engine, 2, 12, day_complete=False)
    expected = engine.crime.to_dict()

    resumed = build_engine(tmp_path, load_state=True)
    assert resumed.crime.to_dict() == expected
    before = authoritative_snapshot(resumed)
    with pytest.raises(CrimeError) as error:
        attempt(resumed, key)
    assert error.value.code == "duplicate_event"
    assert authoritative_snapshot(resumed) == before


def test_phase_two_save_without_crime_initializes_safely(tmp_path):
    engine = build_engine(tmp_path)
    engine.state.save(engine, 1, 8)
    state_path = tmp_path / "state.json"
    phase_two = json.loads(state_path.read_text())
    phase_two.pop("crime")
    state_path.write_text(json.dumps(phase_two))
    resumed = build_engine(tmp_path, load_state=True)
    assert resumed.crime.incidents == []
    assert "attempt_theft" in resumed.crime.theft_activity_rules
