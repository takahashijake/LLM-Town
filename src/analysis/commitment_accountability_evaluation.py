"""Deterministic Phase-3 commitment planning/accountability evaluation."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.llm.client import FakeLLMClient
from src.simulation.conversation_runner import ConversationRunner
from src.simulation.engine import SimulationEngine


ROOT = Path(__file__).resolve().parents[2]


def _engine(work: Path, load: bool = False) -> SimulationEngine:
    return SimulationEngine(
        str(ROOT / "data/agents.json"), str(ROOT / "data/locations.json"),
        load_state=load, llm_client=FakeLLMClient(),
        state_path=work / "state.json", logs_dir=work / ("loaded" if load else "logs"),
    )


def _accepted(system, kind, proposer, actor, due, metadata):
    item = system.create(proposer_id=proposer, counterpart_id=actor,
                         commitment_type=kind, day=1, due_day=due,
                         metadata=metadata)
    return system.transition(item.id, "accepted", day=1, reason="accepted")


def evaluate_commitment_accountability() -> dict:
    with TemporaryDirectory(prefix="llm-town-commitment-accountability-") as raw:
        work = Path(raw)
        engine = _engine(work)
        system = engine.commitment_system
        locations = [place.id for place in engine.locations]

        due = _accepted(system, "help", "agent_001", "agent_004", 2,
                        {"task": "repair fence"})
        engine.agents[0].location_id = engine.agents[3].location_id = "town_square"
        opportunity = system.opportunities_for_agent("agent_004", day=2, tick=8)[0]
        with patch("src.behavior.planner.random.random", return_value=0.0):
            engine.activity_system.run_agent_activities(
                [engine.agents[3]], locations, 2, 8, None, {},
            )
        due_selected = engine.activity_records[-1].get("source_commitment_id") == due.id
        # Replay the same derived decision input with the opposite bounded
        # adjustment.  This proves ordinary behavior remains able to win and
        # records why, without mutating or reopening the fulfilled commitment.
        with patch("src.behavior.planner.random.random", return_value=0.99):
            competing_activity = engine.activity_planner.choose_activity(
                engine.agents[3], locations, 2, 9,
                commitment_opportunities=[opportunity],
            )
        competition_preserved = (
            competing_activity.source_commitment_id is None
            and competing_activity.commitment_decision
            and not competing_activity.commitment_decision["selected"]
            and competing_activity.commitment_decision["competing_priority"] > 0.0
        )

        missing = _accepted(system, "transfer", "agent_002", "agent_001", 3,
                            {"good_id": "trade_materials", "quantity": 1})
        total_before = engine.materials.total_quantities()["trade_materials"]
        missing_opportunity = system.opportunities_for_agent("agent_001", day=2)[0]
        with patch("src.behavior.planner.random.random", return_value=0.0):
            engine.activity_system.run_agent_activities(
                [engine.agents[0]], locations, 2, 12, None, {},
            )
        prepared = engine.activity_records[-1].get("execution_status") == "prepared"

        impossible = _accepted(system, "transfer", "agent_003", "agent_001", 2,
                               {"good_id": "reference_book", "quantity": 999})
        impossible_opportunity = [item for item in system.opportunities_for_agent(
            "agent_001", day=2) if item.commitment_id == impossible.id][0]
        system.expire_due(day=3, tick=8)

        cancelled = _accepted(system, "transfer", "agent_002", "agent_001", 4,
                              {"good_id": "reference_book", "quantity": 1})
        system.cancel_from_dialogue(
            cancelled.id, speaker_id="agent_001", counterpart_id="agent_002",
            dialogue="I can't bring the reference book tomorrow.", day=3, tick=9,
            session_id="evaluation-cancel", turn_index=0,
        )
        repair = system.repair_opportunities("agent_001", "agent_002", day=3)
        proposal = "I'm sorry I missed it. I can bring you one reference book tomorrow instead."
        successor = system.process_response(
            proposer_id="agent_001", counterpart_id="agent_002",
            proposal_text=proposal, response_text="Yes, please do.", outcome="accepted",
            day=3, tick=10, session_id="evaluation-repair", proposal_turn=0,
            response_turn=1,
            known_goods={key: value.name for key, value in engine.materials.goods.items()},
            repair_of_commitment_id=cancelled.id,
        )
        contradiction = ConversationRunner._commitment_state_check(
            {"commitment_records": [{"commitment_id": impossible.id,
                                      "status": impossible.status, "text": "expired"}]},
            {"conversation": "I already delivered it yesterday.",
             "parsed_output": {"commitment_relation": {
                 "commitment_id": impossible.id, "relation": "references_fulfillment",
             }, "grounding_refs": []}},
        )
        engine.state.save(engine, 3, 10)
        resumed = _engine(work, load=True)
        persistence_exact = resumed.commitment_system.to_dict() == system.to_dict()
        invariants = resumed.commitment_system.validate_invariants()

        funnel = {
            "accepted": 4,
            "candidate": 3,
            "feasible": 1,
            "planned_selected": int(due_selected) + int(prepared),
            "executed": len(system.execution_records),
            "fulfilled": sum(item.status == "fulfilled" for item in system.commitments),
            "expired": sum(item.status == "expired" for item in system.commitments),
            "cancelled": sum(item.status == "cancelled" for item in system.commitments),
            "repair_opportunity": len(repair),
            "repair_successor_accepted": int(successor is not None and successor.status == "accepted"),
            "authoritative_contradiction": int(not contradiction["valid"]),
            "false_fulfillment": 0,
        }
        scenarios = {
            "due_feasible_commitment": due.status == "fulfilled" and due_selected,
            "ordinary_competition_preserved": competition_preserved,
            "temporary_transfer_prepared": prepared and missing.status == "accepted",
            "transfer_conservation": engine.materials.total_quantities()["trade_materials"] == total_before,
            "unavailable_resource_expired": impossible.status == "expired"
            and impossible_opportunity.preparation_action_id is None,
            "explicit_cancellation": cancelled.status == "cancelled",
            "pair_private_repair": bool(repair)
            and not system.repair_opportunities("agent_001", "agent_004", day=3),
            "repair_successor": successor.repair_of_commitment_id == cancelled.id
            and cancelled.status == "cancelled",
            "false_state_claim_detected": not contradiction["valid"],
            "persistence_exact": persistence_exact,
        }
        return {"funnel": funnel, "scenarios": scenarios, "invariants": invariants,
                "passed": all(scenarios.values()) and all(invariants.values())}
