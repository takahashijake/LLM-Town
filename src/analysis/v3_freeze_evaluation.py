"""Deterministic end-to-end acceptance evaluation for the V3 planning loop."""

from contextlib import contextmanager
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.analysis.batched_social_evaluation import evaluate_batched_social
from src.llm.client import FakeLLMClient
from src.llm.grounding import GroundingValidator
from src.simulation.engine import SimulationEngine
from src.simulation.social_semantics import classify_commitment_relation
from src.systems.plans import KNOWN_ACTION_TYPES, TEMPLATE_ACTIONS, PlanSystem


@contextmanager
def _isolated_random_state(seed: int = 0):
    """Keep evaluator setup deterministic without contaminating its caller."""
    state = random.getstate()
    random.seed(seed)
    try:
        yield
    finally:
        random.setstate(state)


def _engine(root: Path, name: str, *, load: bool = False) -> SimulationEngine:
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs",
    )


def _accept(engine, kind: str, *, metadata: dict, due: int | None = 2):
    item = engine.commitment_system.create(
        proposer_id="agent_002", counterpart_id="agent_001",
        commitment_type=kind, day=1, due_day=due, metadata=metadata,
        status="proposed",
    )
    return engine.commitment_system.transition(
        item.id, "accepted", day=1, reason="freeze_controlled_acceptance",
    )


def _act(engine, day: int, hour: int) -> None:
    with patch("src.behavior.planner.random.random", return_value=0.0):
        engine.activity_system.run_agent_activities(
            [engine.agents[0]], [place.id for place in engine.locations],
            day, hour, None, {},
        )


def _participant_memory(engine, item, event_type: str) -> bool:
    return all(any(
        memory.event_type == event_type and memory.source_id == item.id
        for memory in agent.memory + agent.memory_archive
    ) for agent in engine.agents[:2])


def evaluate_v3_freeze() -> dict:
    scenarios: dict[str, bool] = {}
    diagnostics: dict[str, str] = {}
    with _isolated_random_state(), TemporaryDirectory() as directory:
        root = Path(directory)

        transfer = _engine(root, "transfer")
        transfer_item = _accept(
            transfer, "transfer", metadata={"good_id": "trade_materials", "quantity": 1},
        )
        total = transfer.materials.total_quantities()["trade_materials"]
        _act(transfer, 2, 8)
        transfer_plan = transfer.plan_system.plans[0]
        acquired = transfer_plan.current_step_index == 1
        _act(transfer, 2, 12)
        scenarios["transfer_regression"] = (
            acquired and transfer_item.status == "fulfilled"
            and transfer_plan.status == "completed"
            and len(transfer.plan_system.execution_records) == 2
            and transfer.materials.total_quantities()["trade_materials"] == total
            and _participant_memory(transfer, transfer_item, "commitment_fulfilled")
        )

        meet = _engine(root, "meet")
        meet_item = _accept(meet, "meet", metadata={"location": "cafe"})
        meet.plan_system.ensure_commitment_plans(1)
        meet_plan = meet.plan_system.plans[0]
        scenarios["concrete_meet_plan"] = (
            meet_plan.id == meet.plan_system.plan_id_for("agent_001", meet_item.id)
            and len(meet_plan.steps) == 1
            and meet_plan.steps[0].action_type == "commitment_meet"
        )
        _act(meet, 2, 8)
        scenarios["authoritative_meeting_success"] = (
            meet_item.status == "fulfilled" and meet_plan.status == "completed"
            and meet_plan.steps[0].execution_key is not None
        )

        vague_meet = _engine(root, "vague-meet")
        vague_meet_item = _accept(vague_meet, "meet", metadata={}, due=None)
        vague_meet.plan_system.ensure_commitment_plans(1)
        scenarios["vague_meet_no_invention"] = (
            not vague_meet.plan_system.plans
            and vague_meet.plan_system.planning_records[0]["reason"]
            == "missing_meeting_location"
            and vague_meet_item.metadata == {}
        )

        help_town = _engine(root, "help")
        help_item = _accept(
            help_town, "help",
            metadata={"task": "review records", "location": "cafe"},
        )
        help_town.plan_system.ensure_commitment_plans(1)
        help_plan = help_town.plan_system.plans[0]
        scenarios["concrete_help_plan"] = (
            len(help_plan.steps) == 1
            and help_plan.steps[0].action_type == "commitment_help"
        )

        dialogue_help = _engine(root, "dialogue-help")
        dialogue_help_item = dialogue_help.commitment_system.process_response(
            proposer_id="agent_002", counterpart_id="agent_001",
            proposal_text="Could you help me review records at the cafe tomorrow?",
            response_text="Yes, I can help tomorrow.", outcome="accepted",
            day=1, tick=8, session_id="freeze-located-help",
            proposal_turn=0, response_turn=1, known_goods={},
        )
        dialogue_help.plan_system.ensure_commitment_plans(1)
        scenarios["dialogue_help_terms_are_plannable"] = (
            dialogue_help_item.metadata
            == {"task": "review records", "location": "cafe"}
            and dialogue_help.plan_system.plans[0].source_id == dialogue_help_item.id
        )
        _act(help_town, 2, 8)
        unrelated = _accept(
            help_town, "help", metadata={"task": "sort files", "location": "library"},
        )
        help_town.plan_system.ensure_commitment_plans(2)
        scenarios["matching_help_success"] = (
            help_item.status == "fulfilled" and help_plan.status == "completed"
            and unrelated.status == "accepted"
        )

        vague_help = _engine(root, "vague-help")
        vague_help_item = _accept(vague_help, "help", metadata={"task": "help somehow"})
        vague_help.plan_system.ensure_commitment_plans(1)
        scenarios["vague_help_no_decomposition"] = (
            not vague_help.plan_system.plans
            and vague_help.plan_system.planning_records[0]["reason"] == "missing_help_location"
            and vague_help_item.metadata == {"task": "help somehow"}
        )

        pending = _engine(root, "pending")
        _accept(pending, "meet", metadata={"location": "library"})
        pending.plan_system.opportunities_for_agent("agent_001", day=2, tick=8)
        pending_plan = pending.plan_system.plans[0]
        scenarios["temporary_infeasibility_pending"] = (
            pending_plan.active and pending_plan.steps[0].attempts == 0
            and any(row["type"] == "blocked_observation"
                    for row in pending_plan.transitions)
        )

        expiring = _engine(root, "expiry")
        expiring_item = _accept(expiring, "meet", metadata={"location": "library"}, due=1)
        expiring.plan_system.ensure_commitment_plans(1)
        expiring.commitment_system.expire_due(day=2, tick=8)
        expiring.plan_system.ensure_commitment_plans(2)
        scenarios["expiry_synchronizes"] = (
            expiring_item.status == "expired"
            and expiring.plan_system.plans[0].status == "expired"
        )

        cancelled = _engine(root, "cancel")
        cancelled_item = _accept(
            cancelled, "help", metadata={"task": "review records", "location": "cafe"},
        )
        cancelled.plan_system.ensure_commitment_plans(1)
        cancelled.commitment_system.cancel_from_dialogue(
            cancelled_item.id, speaker_id="agent_001", counterpart_id="agent_002",
            dialogue="I cannot help review records.", day=1, tick=12,
            session_id="freeze-cancel", turn_index=1,
        )
        scenarios["cancellation_no_orphan"] = (
            cancelled_item.status == "cancelled"
            and not cancelled.plan_system.plans[0].active
        )

        failed = _engine(root, "failure")
        failed_item = _accept(
            failed, "help", metadata={"task": "review records", "location": "cafe"},
        )
        failed.plan_system.ensure_commitment_plans(1)
        failed_plan = failed.plan_system.plans[0]
        for hour in (8, 12, 18):
            failed.plan_system.record_failure(
                failed_plan.id, failed_plan.steps[0].id, day=2, tick=hour,
                reason="controlled_unavailable",
            )
        before = failed.plan_system.to_dict()
        failed.plan_system.record_execution(
            failed_plan.id, failed_plan.steps[0].id, day=3, tick=8,
            execution_key="late-claim", source_commitment_id=failed_item.id,
            action_type="commitment_help",
        )
        scenarios["failure_never_reopens"] = (
            failed_item.status == "failed" and failed_plan.status == "failed"
            and failed.plan_system.to_dict() == before
        )

        proof = transfer.plan_system.execution_records[-1]
        before_replay = transfer.plan_system.to_dict()
        transfer.plan_system.record_execution(
            transfer_plan.id, transfer_plan.steps[-1].id, day=2, tick=12,
            execution_key=proof["execution_key"],
            source_commitment_id=transfer_item.id, action_type="commitment_transfer",
        )
        scenarios["proof_replay_idempotent"] = transfer.plan_system.to_dict() == before_replay

        cross = _engine(root, "cross-proof")
        cross_meet = _accept(cross, "meet", metadata={"location": "cafe"})
        cross_help = _accept(
            cross, "help", metadata={"task": "review records", "location": "cafe"},
        )
        cross.plan_system.ensure_commitment_plans(1)
        cross_plan = cross.plan_system.plans[0]
        cross.commitment_system.execution_records.append({
            "event_key": "other-proof", "source_commitment_id": cross_help.id,
            "commitment_id": cross_help.id, "activity_id": "commitment_help",
        })
        cross.plan_system.record_execution(
            cross_plan.id, cross_plan.steps[0].id, day=2, tick=8,
            execution_key="other-proof", source_commitment_id=cross_help.id,
            action_type="commitment_help",
        )
        scenarios["proof_source_isolation"] = (
            cross_meet.status == "accepted" and cross_plan.current_step_index == 0
        )

        resume = _engine(root, "resume")
        resume_item = _accept(resume, "meet", metadata={"location": "cafe"})
        resume.plan_system.ensure_commitment_plans(1)
        stable_id = resume.plan_system.plans[0].id
        resume.state.save(resume, 1, 8)
        resumed = _engine(root, "resume", load=True)
        _act(resumed, 2, 8)
        resumed.state.save(resumed, 2, 8)
        after = _engine(root, "resume", load=True)
        _act(after, 2, 12)
        scenarios["save_resume_idempotent"] = (
            after.plan_system.plans[0].id == stable_id
            and after.commitment_system.get(resume_item.id).status == "fulfilled"
            and len(after.plan_system.execution_records) == 1
        )

        scenarios["justified_outcome_knowledge"] = (
            _participant_memory(meet, meet_item, "commitment_fulfilled")
            and _participant_memory(help_town, help_item, "commitment_fulfilled")
        )
        scenarios["private_details_do_not_leak"] = (
            not any(memory.source_system == "plans"
                    for memory in meet.agents[1].memory + meet.agents[1].memory_archive)
            and not any(memory.source_id == help_item.id
                        for memory in help_town.agents[2].memory)
        )

        authority_before = (pending.plan_system.to_dict(), pending.commitment_system.to_dict())
        pending.agents[0].memory.clear()
        scenarios["memory_not_authority"] = authority_before == (
            pending.plan_system.to_dict(), pending.commitment_system.to_dict()
        )

        preparing = _engine(root, "preparing-context")
        preparing_item = _accept(
            preparing, "transfer",
            metadata={"good_id": "trade_materials", "quantity": 1},
        )
        preparing.plan_system.ensure_commitment_plans(1)
        preparing_context = preparing.prepare_conversation_context(
            "cafe", preparing.agents[0], preparing.agents[1], 1,
        )["context"]
        preparing_record = next(
            row for row in preparing_context["commitment_records"]
            if row["commitment_id"] == preparing_item.id
        )

        repair = _engine(root, "repair-context")
        repair_parent = _accept(
            repair, "help", metadata={"task": "review records", "location": "cafe"},
            due=1,
        )
        repair.commitment_system.transition(
            repair_parent.id, "failed", day=2, reason="controlled_failure",
        )
        repair_child = repair.commitment_system.create(
            proposer_id="agent_002", counterpart_id="agent_001",
            commitment_type="help", day=2, due_day=3,
            metadata={"task": "review records", "location": "cafe"},
            status="proposed", repair_of_commitment_id=repair_parent.id,
        )
        repair.commitment_system.transition(
            repair_child.id, "accepted", day=2, reason="accepted_repair",
        )
        repair.plan_system.ensure_commitment_plans(2)
        repair_context = repair.prepare_conversation_context(
            "cafe", repair.agents[0], repair.agents[1], 2,
        )["context"]
        repair_record = next(
            row for row in repair_context["commitment_records"]
            if row["commitment_id"] == repair_child.id
        )
        scenarios["active_lifecycle_grounding"] = (
            preparing_record["lifecycle_state"] == "preparing"
            and repair_record["lifecycle_state"] == "repair_successor_active"
            and _participant_memory(
                repair, repair_child, "commitment_repair_accepted",
            )
        )
        _act(repair, 3, 8)
        scenarios["repair_successor_outcome_knowledge"] = (
            repair_child.status == "fulfilled"
            and repair.plan_system.plans[0].status == "completed"
            and _participant_memory(
                repair, repair_child, "commitment_repair_fulfilled",
            )
        )

        validator = GroundingValidator()
        lifecycle_examples = {
            "accepted": ("I still plan to do it.", "I already completed it."),
            "repair_active": (
                "I will try again to make this right.", "I already completed it.",
            ),
            "fulfilled": ("I fulfilled it.", "I failed it."),
            "failed": ("I failed it.", "I fulfilled it."),
            "expired": ("The deadline expired.", "I completed it."),
            "cancelled": ("It was cancelled.", "I fulfilled it."),
        }
        scenarios["grounded_lifecycle_distinctions"] = all(
            validator.validate_realization(good, {
                "history_use": "required", "required_polarity": polarity,
            }).valid
            and not validator.validate_realization(bad, {
                "history_use": "required", "required_polarity": polarity,
            }).valid
            for polarity, (good, bad) in lifecycle_examples.items()
        )
        false_claim = classify_commitment_relation(
            {**pending.commitment_system.commitments[0].to_dict()},
            "We already met at the library.",
            {"commitment_id": pending.commitment_system.commitments[0].id,
             "relation": "references_fulfillment"}, [],
        )
        scenarios["false_model_fulfillment_rejected"] = (
            false_claim["classification"] == "contradiction"
            and pending.commitment_system.commitments[0].status == "accepted"
        )

        batch = evaluate_batched_social()
        scenarios["batched_snapshot_and_ordered_commit"] = batch["passed"]

        for day in range(3, 40):
            for agent in meet.agents:
                meet.journal_system.compress_old_memories(agent, current_day=day)
        meet.state.save(meet, 40, 12)
        longitudinal = _engine(root, "meet", load=True)
        scenarios["longitudinal_bounds_and_recall"] = (
            longitudinal.plan_system.plans[0].status == "completed"
            and _participant_memory(longitudinal, meet_item, "commitment_fulfilled")
            and all(len(agent.memory) <= 200 and len(agent.memory_archive) <= 500
                    for agent in longitudinal.agents)
        )

        legacy = transfer.plan_system.to_dict()
        legacy.pop("schema_version")
        legacy.pop("planning_records")
        restored = PlanSystem.from_dict(
            legacy, commitment_system=transfer.commitment_system,
            agents=transfer.agents, outcome_memory=transfer.outcome_memory,
        )
        scenarios["old_save_compatibility"] = (
            restored.planning_records == []
            and restored.plans[0].id == transfer_plan.id
        )

        plan_checks = transfer.plan_system.validate_invariants()
        commitment_checks = transfer.commitment_system.validate_invariants()
        memory_checks = transfer.outcome_memory.validate()
        invariants = {
            "all_template_actions_registered": all(
                step.action_type in KNOWN_ACTION_TYPES
                for town in (transfer, meet, help_town)
                for plan in town.plan_system.plans for step in plan.steps
            ),
            "template_steps_match_policy": all(
                tuple(step.action_type for step in plan.steps)
                == TEMPLATE_ACTIONS[plan.plan_type.removeprefix("commitment_")]
                for town in (transfer, meet, help_town, dialogue_help, repair)
                for plan in town.plan_system.plans
            ),
            "stable_owner_scoped_ids": all(
                plan.id == town.plan_system.plan_id_for(plan.agent_id, plan.source_id)
                for town in (transfer, meet, help_town)
                for plan in town.plan_system.plans
            ),
            "no_active_terminal_sources": all(
                not plan.active or town.commitment_system.get(plan.source_id).status == "accepted"
                for town in (transfer, meet, help_town, expiring, cancelled, failed)
                for plan in town.plan_system.plans
            ),
            "execution_proof_unique": plan_checks["execution_unique"],
            "execution_proof_matches_source": plan_checks["execution_matches_source"],
            "commitment_authority_valid": all(commitment_checks.values()),
            "causal_provenance_valid": all(memory_checks.values()),
            "bounded_plans": all(
                1 <= len(plan.steps) <= 4
                for town in (transfer, meet, help_town)
                for plan in town.plan_system.plans
            ),
        }

    for name, passed in scenarios.items():
        if not passed:
            diagnostics[name] = "scenario invariant returned false; inspect named lifecycle path"
    for name, passed in invariants.items():
        if not passed:
            diagnostics[name] = "shared hard invariant returned false"
    return {
        "passed": all(scenarios.values()) and all(invariants.values()),
        "scenario_count": len(scenarios),
        "scenarios_passed": sum(scenarios.values()),
        "invariant_count": len(invariants),
        "invariants_passed": sum(invariants.values()),
        "scenarios": scenarios,
        "invariants": invariants,
        "diagnostics": diagnostics,
    }
