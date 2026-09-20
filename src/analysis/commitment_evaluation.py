"""Deterministic acceptance evaluation for persistent social commitments."""

from __future__ import annotations

import json
from pathlib import Path

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.commitments import CommitmentError, CommitmentSystem


def run_commitment_evaluation(work_dir: str | Path, project_root: str | Path = ".") -> dict:
    root = Path(project_root)
    work = Path(work_dir)
    engine = SimulationEngine(
        str(root / "data/agents.json"), str(root / "data/locations.json"),
        llm_client=FakeLLMClient(), state_path=work / "state.json",
        logs_dir=work / "logs",
    )
    system = engine.commitment_system
    recognized = []
    accepted = system.process_response(
        proposer_id="agent_001", counterpart_id="agent_002",
        proposal_text="Could you help me repair the fence tomorrow?",
        response_text="Sure, I'll help tomorrow.", outcome="accepted", day=1, tick=8,
        session_id="eval-help", proposal_turn=0, response_turn=1,
    )
    recognized.append(accepted)
    declined = system.process_response(
        proposer_id="agent_001", counterpart_id="agent_003",
        proposal_text="Could you help me sort supplies tomorrow?",
        response_text="Sorry, I can't.", outcome="declined", day=1, tick=9,
        session_id="eval-decline", proposal_turn=0, response_turn=1,
    )
    recognized.append(declined)
    unresolved = system.process_response(
        proposer_id="agent_001", counterpart_id="agent_002",
        proposal_text="Maybe we should meet sometime.", response_text="Maybe.",
        outcome="unresolved", day=1, tick=10, session_id="eval-ambiguous",
        proposal_turn=0, response_turn=1,
    )
    duplicate = system.process_response(
        proposer_id="agent_001", counterpart_id="agent_002",
        proposal_text="Could you help me repair the fence tomorrow?",
        response_text="Sure, I'll help tomorrow.", outcome="accepted", day=1, tick=8,
        session_id="eval-help", proposal_turn=0, response_turn=1,
    )
    system.transition(
        accepted.id, "fulfilled", day=2, tick=8,
        reason="controlled_authoritative_observation",
        evidence={"activity_event_key": "controlled-help:eval-help"},
    )
    expiring = system.create(
        proposer_id="agent_003", counterpart_id="agent_004", commitment_type="meet",
        day=1, due_day=1, metadata={"location": "cafe"}, status="proposed",
    )
    system.transition(expiring.id, "accepted", day=1, reason="controlled_acceptance")
    system.expire_due(day=2, tick=8)
    try:
        system.transition(accepted.id, "declined", day=2, reason="illegal_probe")
    except CommitmentError:
        pass
    engine.state.save(engine, 2, 8)
    resumed = SimulationEngine(
        str(root / "data/agents.json"), str(root / "data/locations.json"),
        load_state=True, llm_client=FakeLLMClient(), state_path=work / "state.json",
        logs_dir=work / "resumed-logs",
    )
    invariants = resumed.commitment_system.validate_invariants()
    persistence_ok = resumed.commitment_system.to_dict() == system.to_dict()
    metrics = {
        "proposals_generated": 3,
        "proposals_recognized": len([item for item in recognized if item]),
        "accepted": sum(item.status in {"accepted", "fulfilled"} for item in system.commitments),
        "declined": sum(item.status == "declined" for item in system.commitments),
        "unresolved": int(unresolved is None),
        "fulfilled": sum(item.status == "fulfilled" for item in system.commitments),
        "failed_or_expired": sum(item.status in {"failed", "expired"} for item in system.commitments),
        "duplicate_mutation_attempts": system.duplicate_attempts,
        "illegal_state_transition_attempts": system.illegal_transition_attempts,
        "persistence_round_trip_success": persistence_ok,
        "relationship_reputation_reconciled": bool(accepted.consequence_applied),
        "hard_invariant_count": sum(invariants.values()),
    }
    passed = (
        metrics["proposals_recognized"] == 2
        and duplicate.id == accepted.id
        and persistence_ok and all(invariants.values())
        and metrics["duplicate_mutation_attempts"] == 1
        and metrics["illegal_state_transition_attempts"] == 1
    )
    return {"passed": passed, "metrics": metrics, "hard_invariants": invariants,
            "commitments": [item.to_dict() for item in system.commitments]}


def write_commitment_evaluation(result: dict, output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True))
