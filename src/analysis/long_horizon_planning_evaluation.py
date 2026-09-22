"""Deterministic acceptance evaluation for persistent bounded plans."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def _engine(root: Path, name: str, *, load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs",
    )


def _accept(engine, *, good="trade_materials", quantity=1, due=3):
    item = engine.commitment_system.create(
        proposer_id="agent_002", counterpart_id="agent_001",
        commitment_type="transfer", day=1, due_day=due,
        metadata={"good_id": good, "quantity": quantity}, status="proposed",
    )
    return engine.commitment_system.transition(item.id, "accepted", day=1,
                                                reason="controlled_acceptance")


def _act(engine, day, hour, *, choose=True):
    with patch("src.behavior.planner.random.random",
               return_value=0.0 if choose else 0.99):
        engine.activity_system.run_agent_activities(
            [engine.agents[0]], [place.id for place in engine.locations],
            day, hour, None, {},
        )


def evaluate_long_horizon_planning() -> dict:
    scenarios = {}
    with TemporaryDirectory() as directory:
        root = Path(directory)

        success = _engine(root, "success")
        commitment = _accept(success)
        total = success.materials.total_quantities()["trade_materials"]
        _act(success, 2, 8)
        plan = success.plan_system.plans[0]
        scenarios["two_step_success"] = (
            plan.current_step_index == 1 and commitment.status == "accepted"
        )
        _act(success, 2, 12)
        scenarios["two_step_success"] &= (
            plan.status == "completed" and commitment.status == "fulfilled"
            and success.materials.total_quantities()["trade_materials"] == total
        )
        scenarios["causal_memory"] = all(
            any(memory.type == "commitment_fulfilled" for memory in agent.memory)
            for agent in success.agents[:2]
        )
        scenarios["information_boundary"] = not any(
            f"source_id:{commitment.id}" in memory.tags
            for memory in success.agents[2].memory
        )
        executions = list(success.plan_system.execution_records)
        success.plan_system.record_execution(
            plan.id, plan.steps[-1].id, day=2, tick=12,
            execution_key=executions[-1]["execution_key"],
        )
        scenarios["replay_idempotent"] = success.plan_system.execution_records == executions

        interrupted = _engine(root, "interrupted")
        _accept(interrupted)
        _act(interrupted, 2, 8, choose=False)
        interrupted_plan = interrupted.plan_system.plans[0]
        preserved = interrupted_plan.current_step_index == 0
        _act(interrupted, 2, 12)
        scenarios["interruption_resume"] = preserved and interrupted_plan.current_step_index == 1

        unavailable = _engine(root, "unavailable")
        _accept(unavailable, good="reference_book", quantity=999)
        before = unavailable.materials.total_quantities()["reference_book"]
        for hour in (8, 12, 18):
            unavailable.plan_system.opportunities_for_agent(
                "agent_001", day=2, tick=hour,
            )
        failed_plan = unavailable.plan_system.plans[0]
        scenarios["resource_disappears_bounded"] = (
            failed_plan.status == "failed"
            and unavailable.materials.total_quantities()["reference_book"] == before
        )

        resume = _engine(root, "resume")
        _accept(resume)
        _act(resume, 2, 8)
        resume.state.save(resume, 2, 8)
        resumed = _engine(root, "resume", load=True)
        prior_records = len(resumed.plan_system.execution_records)
        _act(resumed, 2, 12)
        scenarios["save_resume"] = (
            prior_records == 1 and len(resumed.plan_system.execution_records) == 2
            and resumed.plan_system.plans[0].status == "completed"
        )

        stale = _engine(root, "stale")
        stale_commitment = _accept(stale)
        stale.plan_system.ensure_commitment_plans(1)
        stale.commitment_system.transition(stale_commitment.id, "cancelled", day=2,
                                           reason="controlled_cancel")
        no_actions = stale.plan_system.opportunities_for_agent(
            "agent_001", day=2, tick=8,
        )
        scenarios["terminal_source_invalidates"] = (
            not no_actions and stale.plan_system.plans[0].status == "abandoned"
        )

        invariants = success.plan_system.validate_invariants()
        invariants.update({
            "material_conserved": success.materials.total_quantities()["trade_materials"] == total,
            "commitment_invariants": all(success.commitment_system.validate_invariants().values()),
            "no_active_terminal_plans": all(plan.active == (plan.status == "active")
                                            for plan in success.plan_system.plans),
            "private_memory": scenarios["information_boundary"],
        })
        funnel = {
            "accepted": 1,
            "plan_created": 1,
            "steps_executed": len(success.plan_system.execution_records),
            "plan_completed": int(plan.status == "completed"),
            "commitment_fulfilled": int(commitment.status == "fulfilled"),
            "plans_failed": 1,
            "plans_abandoned": 1,
            "plans_interrupted": 1,
        }
    return {"passed": all(scenarios.values()) and all(invariants.values()),
            "scenarios": scenarios, "invariants": invariants, "funnel": funnel}
