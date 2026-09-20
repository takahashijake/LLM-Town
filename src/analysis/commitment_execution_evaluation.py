"""Controlled commitment-to-activity execution acceptance evaluation."""

from __future__ import annotations

import json
import random
from pathlib import Path

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def _accepted(system, kind, metadata, *, proposer="agent_001", actor="agent_004", due=2):
    item = system.create(
        proposer_id=proposer, counterpart_id=actor, commitment_type=kind,
        day=1, due_day=due, metadata=metadata, status="proposed",
    )
    system.transition(item.id, "accepted", day=1, reason="controlled_acceptance")
    return item


def run_commitment_execution_evaluation(work_dir: str | Path, project_root: str | Path = ".") -> dict:
    root, work = Path(project_root), Path(work_dir)
    engine = SimulationEngine(
        str(root / "data/agents.json"), str(root / "data/locations.json"),
        llm_client=FakeLLMClient(), state_path=work / "state.json",
        logs_dir=work / "logs",
    )
    system = engine.commitment_system
    proposer, actor = engine.agents[0], engine.agents[3]
    proposer.location_id = actor.location_id = "cafe"
    items = [
        _accepted(system, "transfer", {"good_id": "trade_materials", "quantity": 1}),
        _accepted(system, "transfer", {"good_id": "reference_book", "quantity": 1}),
        _accepted(system, "meet", {"location": "cafe"}),
        _accepted(system, "help", {"task": "repair fence", "location": "cafe"}),
    ]
    opportunities = [
        option for item in items
        for option in system.opportunities_for_agent(item.counterpart_id, day=2, tick=8)
        if option.commitment_id == item.id
    ]
    # Controlled execution bypasses stochastic selection while still using the
    # exact planner-produced Activity and authoritative ActivitySystem contract.
    executed = []
    for option in opportunities:
        if option.feasibility != "feasible":
            continue
        activity = engine.activity_planner.create_commitment_activity(actor, option)
        actor.set_activity(activity)
        engine.activity_system.log_activity_event(2, 8, actor, activity)
        record = engine.activity_records[-1]
        executed.append(system.execute_activity(
            commitment_id=option.commitment_id, agent_id=actor.id,
            day=2, tick=8, activity_record=record,
        ))
    system.expire_due(day=3, tick=8)
    engine.state.save(engine, 3, 8)
    resumed = SimulationEngine(
        str(root / "data/agents.json"), str(root / "data/locations.json"),
        load_state=True, llm_client=FakeLLMClient(), state_path=work / "state.json",
        logs_dir=work / "loaded-logs",
    )
    invariants = resumed.commitment_system.validate_invariants()
    material_ok = resumed.materials.material_history_reconstructs_inventories()
    metrics = {
        "accepted": len(items),
        "candidate_generated": len(opportunities),
        "candidate_feasible": sum(item.feasibility == "feasible" for item in opportunities),
        "candidate_temporarily_infeasible": sum(
            item.feasibility == "temporarily_infeasible" for item in opportunities
        ),
        "selected": len(executed),
        "executed": len(executed),
        "fulfilled": sum(item.status == "fulfilled" for item in items),
        "expired": sum(item.status == "expired" for item in items),
        "provenance_valid": all(
            record["source_commitment_id"] == record["commitment_id"] for record in executed
        ),
        "persistence_exact": resumed.commitment_system.to_dict() == system.to_dict(),
        "material_conserved": material_ok,
        "hard_invariant_count": sum(invariants.values()),
    }
    passed = (
        metrics["candidate_generated"] == 4
        and metrics["candidate_feasible"] == 3
        and metrics["fulfilled"] == 3
        and metrics["expired"] == 1
        and metrics["provenance_valid"] and metrics["persistence_exact"]
        and material_ok and all(invariants.values())
    )
    return {
        "passed": passed, "metrics": metrics, "hard_invariants": invariants,
        "opportunities": [item.__dict__ for item in opportunities],
        "execution_records": executed,
    }


def write_commitment_execution_evaluation(result: dict, output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True))
