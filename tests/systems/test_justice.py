from dataclasses import replace

import pytest

from src.systems.crime import CrimeSystem
from src.systems.justice import JusticeError, JusticeSystem


def event_key(*requirements):
    for number in range(10000):
        key = f"justice-test-{number}"
        if all(CrimeSystem.witness_observes(key, agent_id) is expected for agent_id, expected in requirements):
            return key
    raise AssertionError("no deterministic witness key")


def arrange(engine, witness=True):
    positions = {"agent_001": "library", "agent_002": "market", "agent_003": "market" if witness else "library", "agent_004": "market"}
    for agent in engine.agents:
        agent.location_id = positions[agent.id]


def steal(engine, witness=True):
    arrange(engine, witness)
    key = event_key(("agent_003", True), ("agent_004", False)) if witness else event_key(("agent_004", False))
    return engine.crime.attempt_theft(
        actor_id="agent_002", source_inventory_id="inventory:agent:agent_004",
        good_id="trade_materials", quantity=1, day=2, hour=12,
        location_id="market", event_key=key, agents=engine.agents,
    )


def witnessed_case(engine):
    incident = steal(engine)
    direct = next(x for x in engine.crime.evidence if x.incident_id == incident.id and x.evidence_type == "eyewitness" and x.holder_agent_id == "agent_003")
    case = engine.justice.open_case(
        incident_id=incident.id, opened_by_agent_id="agent_003",
        investigator_agent_id="agent_001", trigger_evidence_id=direct.id,
        day=2, hour=13, event_key="open:witnessed",
    )
    return incident, direct, case


def test_valid_case_creation_and_duplicate_prevention(fake_engine):
    incident, direct, case = witnessed_case(fake_engine)
    assert case.incident_id == incident.id
    assert {x.evidence_type for x in fake_engine.justice.admitted_evidence} == {"unauthorized_transfer", "eyewitness"}
    with pytest.raises(JusticeError, match="already has a case") as error:
        fake_engine.justice.open_case(incident_id=incident.id, opened_by_agent_id="agent_003", investigator_agent_id="agent_001", trigger_evidence_id=direct.id, day=2, hour=14, event_key="open:again")
    assert error.value.code == "duplicate_case"


def test_configuration_cannot_promote_hearsay(fake_engine):
    with pytest.raises(ValueError, match="exactly direct eyewitness"):
        JusticeSystem(
            crime=fake_engine.crime, materials=fake_engine.materials,
            agents=fake_engine.agents, reputation_system=fake_engine.reputation_system,
            investigator_agent_ids=("agent_001",), rule_version="theft-direct-eyewitness-v1",
            qualifying_actor_evidence=(("hearsay", "hearsay"),),
        )


def test_unknown_and_undiscovered_incidents_cannot_open(fake_engine):
    with pytest.raises(JusticeError) as error:
        fake_engine.justice.open_case(incident_id="crime-nope", opened_by_agent_id="agent_004", investigator_agent_id="agent_001", trigger_evidence_id="none", day=2, hour=1, event_key="bad")
    assert error.value.code == "unknown_incident"
    incident = steal(fake_engine, witness=False)
    actor_knowledge = next(x for x in fake_engine.crime.evidence if x.incident_id == incident.id and x.evidence_type == "actor_knowledge")
    with pytest.raises(JusticeError) as error:
        fake_engine.justice.open_case(incident_id=incident.id, opened_by_agent_id="agent_002", investigator_agent_id="agent_001", trigger_evidence_id=actor_knowledge.id, day=2, hour=13, event_key="secret")
    assert error.value.code == "invalid_case_trigger"
    assert fake_engine.justice.knowledge_for_agent("agent_003")["cases"] == []


def test_evidence_provenance_and_hearsay_never_upgrade(fake_engine):
    incident, direct, case = witnessed_case(fake_engine)
    hearsay = fake_engine.crime.share_evidence(speaker_id="agent_003", listener_id="agent_001", evidence_id=direct.id, day=2, hour=14, event_key="share")
    admitted = fake_engine.justice.submit_evidence(case_id=case.id, submitter_agent_id="agent_001", evidence_id=hearsay.id, day=2, hour=15, event_key="submit:hearsay")
    assert direct.provenance_type == "direct_observation"
    assert hearsay.provenance_type == admitted.provenance_type == "hearsay"
    assert hearsay.source_evidence_id == direct.id


def test_direct_evidence_adjudicates_without_using_incident_actor(fake_engine):
    _incident, direct, case = witnessed_case(fake_engine)
    decision = fake_engine.justice.adjudicate(case_id=case.id, reviewer_agent_id="agent_001", day=2, hour=16, event_key="decide")
    assert decision.result == "responsible"
    assert decision.responsible_actor_id == direct.actor_id
    assert decision.actor_identifying_evidence_ids == (direct.id,)
    assert all(x != _incident.evidence_ids[0] for x in decision.actor_identifying_evidence_ids)


def test_victim_discovery_and_hearsay_only_are_insufficient(fake_engine):
    incident = steal(fake_engine, witness=False)
    loss = fake_engine.crime.discover_loss(incident_id=incident.id, victim_id="agent_004", day=2, hour=13, event_key="discover")
    assert not loss.claims_actor
    case = fake_engine.justice.open_case(incident_id=incident.id, opened_by_agent_id="agent_004", investigator_agent_id="agent_001", trigger_evidence_id=loss.id, day=2, hour=14, event_key="open:loss")
    # Reputation state is intentionally irrelevant to adjudication.
    fake_engine.reputation_system.record_observation(day=2, observer=fake_engine.agents[0], target_agent="Ethan", dimension="trustworthiness", value=-1, evidence_id="unrelated-reputation")
    decision = fake_engine.justice.adjudicate(case_id=case.id, reviewer_agent_id="agent_001", day=2, hour=16, event_key="decide:loss")
    assert decision.result == "insufficient_evidence"
    assert decision.responsible_actor_id is None
    assert not decision.actor_identifying_evidence_ids
    with pytest.raises(JusticeError) as error:
        fake_engine.justice.apply_consequence(adjudication_id=decision.id, day=2, hour=17, event_key="punish:no-proof")
    assert error.value.code == "no_responsible_actor"


def test_hearsay_only_cannot_identify_actor(fake_engine):
    incident, direct, _case = witnessed_case(fake_engine)
    # Build a second system to open on victim loss and submit only the hearsay actor claim.
    # The first case already demonstrates that hearsay remains explicitly indirect.
    hearsay = fake_engine.crime.share_evidence(speaker_id="agent_003", listener_id="agent_001", evidence_id=direct.id, day=2, hour=14, event_key="hear")
    # Remove the direct trigger admission to model what the adjudicator actually has.
    trigger_admission = next(x for x in fake_engine.justice.admitted_evidence if x.evidence_id == direct.id)
    fake_engine.justice.admitted_evidence.remove(trigger_admission)
    case = fake_engine.justice.cases[0]
    fake_engine.justice.cases[0] = replace(case, admitted_evidence_ids=tuple(x for x in case.admitted_evidence_ids if x != trigger_admission.id))
    fake_engine.justice.submit_evidence(case_id=case.id, submitter_agent_id="agent_001", evidence_id=hearsay.id, day=2, hour=15, event_key="submit:hear")
    decision = fake_engine.justice.adjudicate(case_id=case.id, reviewer_agent_id="agent_001", day=2, hour=16, event_key="decide:hear")
    assert decision.result == "insufficient_evidence"


def test_full_restitution_conserves_material_and_currency_and_is_idempotent(fake_engine):
    incident, _direct, case = witnessed_case(fake_engine)
    decision = fake_engine.justice.adjudicate(case_id=case.id, reviewer_agent_id="agent_001", day=2, hour=16, event_key="decide")
    balances = {k: v.balance for k, v in fake_engine.economy.accounts.items()}
    total = fake_engine.materials.total_quantities()
    consequence = fake_engine.justice.apply_consequence(adjudication_id=decision.id, day=2, hour=17, event_key="consequence")
    restitution = fake_engine.justice.restitutions[0]
    transfer = next(x for x in fake_engine.materials.inventory_transfers if x.id == restitution.material_transfer_id)
    assert restitution.status == "full" and restitution.returned_quantity == 1
    assert transfer.authorization_type == "justice_restitution"
    assert transfer.authorization_id == decision.id
    assert fake_engine.materials.lot_ids_moved_by_transfer(transfer.id) == \
        fake_engine.materials.lot_ids_moved_by_transfer(incident.unauthorized_transfer_id)
    assert fake_engine.materials.total_quantities() == total
    assert {k: v.balance for k, v in fake_engine.economy.accounts.items()} == balances
    assert consequence.affected_agent_ids
    with pytest.raises(JusticeError) as error:
        fake_engine.justice.apply_consequence(adjudication_id=decision.id, day=2, hour=17, event_key="consequence")
    assert error.value.code == "duplicate_event"
    assert len(fake_engine.justice.restitutions) == len(fake_engine.justice.consequences) == 1


def test_unavailable_stock_records_unresolved_without_minting(fake_engine):
    incident, _direct, case = witnessed_case(fake_engine)
    actor_inventory = fake_engine.materials.inventory_for_agent("agent_002")
    fake_engine.materials.transfer_good(actor_inventory.id, "inventory:agent:agent_003", incident.good_id, 1, day=2, hour=15, reason="Disposed before review", authorization_type="authorized_transfer", authorization_id="dispose", event_key="dispose")
    before = fake_engine.materials.total_quantities()
    decision = fake_engine.justice.adjudicate(case_id=case.id, reviewer_agent_id="agent_001", day=2, hour=16, event_key="decide")
    fake_engine.justice.apply_consequence(adjudication_id=decision.id, day=2, hour=17, event_key="consequence")
    assert fake_engine.justice.restitutions[0].status == "unresolved"
    assert fake_engine.justice.restitutions[0].material_transfer_id is None
    assert fake_engine.materials.total_quantities() == before


def test_partial_restitution_returns_only_available_stolen_stock(fake_engine):
    arrange(fake_engine, True)
    key = event_key(("agent_003", True), ("agent_004", False))
    incident = fake_engine.crime.attempt_theft(
        actor_id="agent_002", source_inventory_id="inventory:agent:agent_004",
        good_id="trade_materials", quantity=2, day=2, hour=12,
        location_id="market", event_key=key, agents=fake_engine.agents,
    )
    direct = next(x for x in fake_engine.crime.evidence if x.incident_id == incident.id and x.evidence_type == "eyewitness" and x.holder_agent_id == "agent_003")
    case = fake_engine.justice.open_case(incident_id=incident.id, opened_by_agent_id="agent_003", investigator_agent_id="agent_001", trigger_evidence_id=direct.id, day=2, hour=13, event_key="open:partial")
    actor_inventory = fake_engine.materials.inventory_for_agent("agent_002")
    fake_engine.materials.transfer_good(actor_inventory.id, "inventory:agent:agent_003", incident.good_id, 1, day=2, hour=15, reason="One unit unavailable", authorization_type="authorized_transfer", authorization_id="dispose-one", event_key="dispose-one")
    decision = fake_engine.justice.adjudicate(case_id=case.id, reviewer_agent_id="agent_001", day=2, hour=16, event_key="decide:partial")
    fake_engine.justice.apply_consequence(adjudication_id=decision.id, day=2, hour=17, event_key="consequence:partial")
    restitution = fake_engine.justice.restitutions[0]
    assert restitution.status == "partial"
    assert (restitution.requested_quantity, restitution.returned_quantity) == (2, 1)


def test_private_case_boundary_then_public_adjudication(fake_engine):
    _incident, _direct, case = witnessed_case(fake_engine)
    assert fake_engine.justice.knowledge_for_agent("agent_002")["cases"] == []
    assert fake_engine.justice.knowledge_for_agent("agent_004")["cases"] == []
    fake_engine.justice.adjudicate(case_id=case.id, reviewer_agent_id="agent_001", day=2, hour=16, event_key="decide")
    assert [x.id for x in fake_engine.justice.knowledge_for_agent("agent_002")["cases"]] == [case.id]
