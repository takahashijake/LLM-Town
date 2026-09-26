import json

import pytest

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.commitments import CommitmentError, CommitmentSystem


def engine(tmp_path, *, load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=tmp_path / "state.json",
        logs_dir=tmp_path / "logs",
    )


def accepted_help(system, key="session:0:1"):
    session_id = key.split(":", 1)[0]
    return system.process_response(
        proposer_id="alice", counterpart_id="bob",
        proposal_text="Could you help me repair the fence tomorrow?",
        response_text="Sure, I'll help you tomorrow.", outcome="accepted",
        day=1, tick=8, session_id=session_id, proposal_turn=0,
        response_turn=1, known_goods={},
    )


def test_clear_proposal_acceptance_and_duplicate_processing():
    system = CommitmentSystem()
    item = accepted_help(system)
    duplicate = accepted_help(system)
    assert item.status == "accepted"
    assert item.metadata == {"task": "repair the fence"}
    assert duplicate.id == item.id
    assert len(system.commitments) == 1
    assert system.duplicate_attempts == 1


def test_explicit_help_location_is_preserved_for_bounded_planning(tmp_path):
    town = engine(tmp_path)
    item = town.commitment_system.process_response(
        proposer_id="agent_002", counterpart_id="agent_001",
        proposal_text="Could you help me review records at the cafe tomorrow?",
        response_text="Yes, I can help tomorrow.", outcome="accepted",
        day=1, tick=8, session_id="located-help", proposal_turn=0,
        response_turn=1, known_goods={},
    )
    assert item.metadata == {"task": "review records", "location": "cafe"}
    town.plan_system.ensure_commitment_plans(1)
    assert town.plan_system.plans[0].source_id == item.id
    assert town.plan_system.plans[0].plan_type == "commitment_help"


def test_clear_decline_is_terminal_and_inactive():
    system = CommitmentSystem()
    item = system.process_response(
        proposer_id="alice", counterpart_id="bob",
        proposal_text="Could you help me repair the fence tomorrow?",
        response_text="I don't think I can.", outcome="declined", day=1, tick=8,
        session_id="decline", proposal_turn=0, response_turn=1,
    )
    assert item.status == "declined"
    assert not item.active


@pytest.mark.parametrize("proposal,response,outcome", [
    ("Maybe we should meet sometime.", "Yeah, maybe.", "unresolved"),
    ("Could you help me repair the fence tomorrow?", "Maybe.", "unresolved"),
])
def test_ambiguous_language_creates_no_commitment(proposal, response, outcome):
    system = CommitmentSystem()
    assert system.process_response(
        proposer_id="alice", counterpart_id="bob", proposal_text=proposal,
        response_text=response, outcome=outcome, day=1, tick=8,
        session_id="ambiguous", proposal_turn=0, response_turn=1,
    ) is None


def test_fulfillment_once_and_invalid_terminal_transition():
    system = CommitmentSystem()
    item = accepted_help(system)
    system.transition(item.id, "fulfilled", day=2, tick=9, reason="observed_help")
    system.transition(item.id, "fulfilled", day=2, tick=9, reason="duplicate")
    assert system.duplicate_attempts == 1
    with pytest.raises(CommitmentError, match="cannot transition fulfilled to declined"):
        system.transition(item.id, "declined", day=2, reason="invalid")


def test_expiration_and_cancellation():
    system = CommitmentSystem()
    expired = accepted_help(system)
    assert system.expire_due(day=3)[0].status == "expired"
    cancelled = accepted_help(system, key="session2:0:1")
    system.transition(cancelled.id, "cancelled", day=1, reason="explicit_cancellation")
    assert cancelled.status == "cancelled"


def test_save_load_round_trip_and_resume_fulfillment(tmp_path):
    first = engine(tmp_path)
    item = first.commitment_system.create(
        proposer_id="agent_001", counterpart_id="agent_002", commitment_type="help",
        day=1, due_day=2, metadata={"task": "review records"}, status="proposed",
    )
    first.commitment_system.transition(item.id, "accepted", day=1, reason="accepted")
    first.state.save(first, 1, 8)
    raw_before = json.loads((tmp_path / "state.json").read_text())["commitments"]
    resumed = engine(tmp_path, load=True)
    assert resumed.commitment_system.to_dict() == raw_before
    resumed.commitment_system.transition(item.id, "fulfilled", day=2, reason="observed_help")
    assert resumed.commitment_system.get(item.id).status == "fulfilled"


def test_relationship_and_reputation_effect_exactly_once_and_bounded(tmp_path):
    town = engine(tmp_path)
    item = town.commitment_system.create(
        proposer_id="agent_001", counterpart_id="agent_002", commitment_type="help",
        day=1, due_day=1, metadata={"task": "review records"}, status="proposed",
    )
    town.commitment_system.transition(item.id, "accepted", day=1, reason="accepted")
    town.commitment_system.transition(item.id, "fulfilled", day=1, reason="observed_help")
    first_score = town.relationships.get_score("Maya", "Ethan")
    updates = len(town.reputation_updates)
    town.commitment_system.transition(item.id, "fulfilled", day=1, reason="duplicate")
    belief = town.agents[0].reputation_beliefs["Ethan"]["trustworthiness"]
    assert first_score == 1
    assert len(town.reputation_updates) == updates == 1
    assert 0 < belief.score <= 1.0


def test_transfer_fulfillment_requires_real_authoritative_exchange(tmp_path):
    town = engine(tmp_path)
    item = town.commitment_system.create(
        proposer_id="agent_001", counterpart_id="agent_004", commitment_type="transfer",
        day=1, due_day=2, metadata={"good_id": "trade_materials", "quantity": 1},
        status="proposed",
    )
    town.commitment_system.transition(item.id, "accepted", day=1, reason="accepted")
    source = town.materials.get_inventory("inventory:agent:agent_004").quantity("trade_materials")
    destination = town.materials.get_inventory("inventory:agent:agent_001").quantity("trade_materials")
    record = town.commitment_system.fulfill_transfer(item.id, day=2, tick=8)
    assert town.materials.get_inventory("inventory:agent:agent_004").quantity("trade_materials") == source - 1
    assert town.materials.get_inventory("inventory:agent:agent_001").quantity("trade_materials") == destination + 1
    assert item.evidence[-1]["material_transfer_id"] == record.id
    with pytest.raises(CommitmentError):
        town.commitment_system.fulfill_transfer(item.id, day=2, tick=8)
    town.materials._validate_history()


def test_context_is_pair_bounded_and_invariant_report_passes():
    system = CommitmentSystem()
    item = accepted_help(system)
    assert system.relevant_context("bob", "alice", 1) == [
        "you agreed to help repair the fence on day 2."
    ]
    assert system.relevant_context("carol", "alice", 1) == []
    assert all(system.validate_invariants().values())
