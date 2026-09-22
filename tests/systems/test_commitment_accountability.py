from unittest.mock import patch

from src.llm.client import FakeLLMClient
from src.simulation.conversation_runner import ConversationRunner
from src.simulation.engine import SimulationEngine
from src.simulation.social_semantics import classify_explicit_cancellation


def town(tmp_path, load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=tmp_path / "state.json",
        logs_dir=tmp_path / ("loaded-logs" if load else "logs"),
    )


def accepted(system, kind="transfer", proposer="agent_002", actor="agent_001",
             due=2, metadata=None):
    item = system.create(
        proposer_id=proposer, counterpart_id=actor, commitment_type=kind,
        day=1, due_day=due, metadata=metadata or {
            "good_id": "trade_materials", "quantity": 1,
        }, status="proposed",
    )
    return system.transition(item.id, "accepted", day=1, reason="accepted")


def test_due_decision_is_inspectable_but_can_lose_to_bounded_lapse(tmp_path):
    engine = town(tmp_path)
    actor = engine.agents[0]
    item = accepted(engine.commitment_system, kind="help",
                    metadata={"task": "repair fence"})
    opportunity = engine.commitment_system.opportunities_for_agent(actor.id, day=2)[0]
    with patch("src.behavior.planner.random.random", return_value=0.0):
        selected = engine.activity_planner.choose_activity(
            actor, [place.id for place in engine.locations], 2, 8,
            commitment_opportunities=[opportunity],
        )
    assert selected.source_commitment_id == item.id
    assert round(selected.commitment_decision["pressure"], 2) == 0.95
    assert selected.commitment_decision["reason"]
    with patch("src.behavior.planner.random.random", return_value=0.99):
        ignored = engine.activity_planner.choose_activity(
            actor, [place.id for place in engine.locations], 2, 8,
            commitment_opportunities=[opportunity],
        )
    assert ignored.source_commitment_id is None
    assert ignored.commitment_decision["selected"] is False
    assert "did not meet" in ignored.commitment_decision["reason"]


def test_missing_transfer_resource_can_be_bought_without_minting(tmp_path):
    engine = town(tmp_path)
    actor = engine.agents[0]
    item = accepted(engine.commitment_system)
    seller_id = "inventory:business:market_stall"
    seller_before = engine.materials.quantity(seller_id, "trade_materials")
    total_before = engine.materials.total_quantities()["trade_materials"]
    opportunity = engine.commitment_system.opportunities_for_agent(actor.id, day=2)[0]
    assert opportunity.feasibility == "temporarily_infeasible"
    assert opportunity.preparation_action_id == "commitment_acquire_resource"
    with patch("src.behavior.planner.random.random", return_value=0.0):
        engine.activity_system.run_agent_activities(
            [actor], [place.id for place in engine.locations], 2, 8, None, {},
        )
    assert item.status == "accepted"
    assert engine.materials.quantity(f"inventory:agent:{actor.id}", "trade_materials") == 1
    assert engine.materials.quantity(seller_id, "trade_materials") == seller_before - 1
    assert engine.materials.total_quantities()["trade_materials"] == total_before
    assert engine.activity_records[-1]["execution_status"] == "prepared"


def test_no_stock_means_no_preparation_route_and_eventual_expiration(tmp_path):
    engine = town(tmp_path)
    item = accepted(engine.commitment_system, metadata={
        "good_id": "reference_book", "quantity": 999,
    })
    before = engine.materials.total_quantities()["reference_book"]
    opportunity = engine.commitment_system.opportunities_for_agent("agent_001", day=2)[0]
    assert opportunity.infeasibility_reason == "resource_unavailable"
    assert opportunity.preparation_action_id is None
    engine.commitment_system.expire_due(day=3)
    assert item.status == "expired"
    assert engine.materials.total_quantities()["reference_book"] == before


def test_explicit_cancellation_is_grounded_idempotent_and_ambiguous_is_not(tmp_path):
    engine = town(tmp_path)
    system = engine.commitment_system
    item = accepted(system, metadata={"good_id": "reference_book", "quantity": 1})
    assert classify_explicit_cancellation(
        item.to_dict(), "I can't believe how useful that book is."
    )["cancel"] is False
    assert system.cancel_from_dialogue(
        item.id, speaker_id="agent_001", counterpart_id="agent_002",
        dialogue="I'm sorry, but I can't bring the reference book tomorrow.",
        day=1, tick=12, session_id="cancel-session", turn_index=1,
    ).status == "cancelled"
    evidence = list(item.evidence)
    assert system.cancel_from_dialogue(
        item.id, speaker_id="agent_001", counterpart_id="agent_002",
        dialogue="I'm sorry, but I can't bring the reference book tomorrow.",
        day=1, tick=12, session_id="cancel-session", turn_index=1,
    ) is None
    assert item.evidence == evidence
    assert system.validate_invariants()["cancelled_has_evidence"]


def test_repair_opportunity_is_pair_private_bounded_and_successor_needs_acceptance(tmp_path):
    engine = town(tmp_path)
    system = engine.commitment_system
    parent = accepted(system, metadata={"good_id": "reference_book", "quantity": 1})
    system.expire_due(day=3)
    assert system.repair_opportunities("agent_001", "agent_002", day=3)
    assert not system.repair_opportunities("agent_001", "agent_003", day=3)
    assert not system.repair_opportunities("agent_001", "agent_002", day=6)
    proposal = "I'm sorry I missed it. I can bring you one reference book tomorrow instead."
    assert system.recognize_proposal(
        proposal, day=3,
        known_goods={key: value.name for key, value in engine.materials.goods.items()},
    )
    assert len(system.commitments) == 1
    child = system.process_response(
        proposer_id="agent_001", counterpart_id="agent_002",
        proposal_text=proposal, response_text="Yes, please do.", outcome="accepted",
        day=3, tick=9, session_id="repair-session", proposal_turn=0,
        response_turn=1,
        known_goods={key: value.name for key, value in engine.materials.goods.items()},
        repair_of_commitment_id=parent.id,
    )
    assert parent.status == "expired"
    assert child.id != parent.id and child.status == "accepted"
    assert child.repair_of_commitment_id == parent.id
    assert system.process_response(
        proposer_id="agent_001", counterpart_id="agent_002",
        proposal_text=proposal, response_text="Yes, please do.", outcome="accepted",
        day=3, tick=9, session_id="repair-session", proposal_turn=0,
        response_turn=1,
        known_goods={key: value.name for key, value in engine.materials.goods.items()},
        repair_of_commitment_id=parent.id,
    ).id == child.id
    assert len(system.commitments) == 2


def test_contradictory_claims_are_detected_without_ledger_mutation(tmp_path):
    engine = town(tmp_path)
    item = accepted(engine.commitment_system,
                    metadata={"good_id": "reference_book", "quantity": 1})
    context = {"commitment_records": [{"commitment_id": item.id,
                                        "status": item.status, "text": "active"}]}
    processed = {"conversation": "I already brought it yesterday.",
                 "parsed_output": {"commitment_relation": {
                     "commitment_id": item.id, "relation": "references_fulfillment",
                 }, "grounding_refs": []}}
    result = ConversationRunner._commitment_state_check(context, processed)
    assert not result["valid"]
    assert item.status == "accepted"


def test_terminal_lineage_and_attempts_persist_exactly(tmp_path):
    engine = town(tmp_path)
    system = engine.commitment_system
    parent = accepted(system, metadata={"good_id": "reference_book", "quantity": 1})
    system.cancel_from_dialogue(
        parent.id, speaker_id="agent_001", counterpart_id="agent_002",
        dialogue="I can't bring the reference book tomorrow.", day=1, tick=9,
        session_id="persist-cancel", turn_index=0,
    )
    child = system.create(
        proposer_id="agent_002", counterpart_id="agent_001", commitment_type="transfer",
        day=1, due_day=2, metadata={"good_id": "reference_book", "quantity": 1},
        repair_of_commitment_id=parent.id, evidence={"proposal": "replacement"},
        evidence_key="persist:0:1",
    )
    system.transition(child.id, "accepted", day=1, reason="counterpart_accepted")
    system.record_attempt(child.id, agent_id="agent_001", day=1, tick=10,
                          kind="preparation", activity_id="commitment_acquire_resource")
    engine.state.save(engine, 1, 10)
    resumed = town(tmp_path, load=True)
    assert resumed.commitment_system.to_dict() == system.to_dict()
    assert all(resumed.commitment_system.validate_invariants().values())
