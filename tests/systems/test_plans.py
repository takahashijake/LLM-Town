from unittest.mock import patch

import pytest

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.plans import AgentPlan, PlanStep


def town(tmp_path, load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=tmp_path / "state.json",
        logs_dir=tmp_path / ("loaded-logs" if load else "logs"),
    )


def accepted_transfer(engine, due=3):
    item = engine.commitment_system.create(
        proposer_id="agent_002", counterpart_id="agent_001",
        commitment_type="transfer", day=1, due_day=due,
        metadata={"good_id": "trade_materials", "quantity": 1},
        status="proposed",
    )
    return engine.commitment_system.transition(
        item.id, "accepted", day=1, reason="accepted",
    )


def run_actor(engine, day, hour):
    actor = engine.agents[0]
    with patch("src.behavior.planner.random.random", return_value=0.0):
        engine.activity_system.run_agent_activities(
            [actor], [place.id for place in engine.locations], day, hour, None, {},
        )


def test_characterization_activity_has_no_continuity_without_authoritative_source(tmp_path):
    engine = town(tmp_path)
    run_actor(engine, 1, 8)
    assert engine.activity_records[-1]["source_plan_id"] is None
    assert engine.plan_system.plans == []


def test_transfer_plan_persists_acquisition_then_delivery_without_minting(tmp_path):
    engine = town(tmp_path)
    commitment = accepted_transfer(engine)
    total_before = engine.materials.total_quantities()["trade_materials"]
    run_actor(engine, 2, 8)
    plan = engine.plan_system.plans[0]
    assert plan.source_id == commitment.id
    assert plan.current_step_index == 1
    assert plan.steps[0].execution_key
    assert commitment.status == "accepted"
    assert engine.materials.total_quantities()["trade_materials"] == total_before
    run_actor(engine, 2, 12)
    assert commitment.status == "fulfilled"
    assert plan.status == "completed"
    assert plan.current_step_index == 2
    assert all(plan.steps[index].status == "completed" for index in (0, 1))
    assert engine.materials.total_quantities()["trade_materials"] == total_before
    assert all(engine.plan_system.validate_invariants().values())


def test_plan_save_resume_is_semantically_exact_and_does_not_repeat_purchase(tmp_path):
    engine = town(tmp_path)
    accepted_transfer(engine)
    run_actor(engine, 2, 8)
    inventory = engine.materials.inventory_for_agent("agent_001")
    quantity = inventory.quantity("trade_materials")
    expected = engine.plan_system.to_dict()
    engine.state.save(engine, 2, 8)
    resumed = town(tmp_path, load=True)
    assert resumed.plan_system.to_dict() == expected
    assert resumed.materials.inventory_for_agent("agent_001").quantity("trade_materials") == quantity
    run_actor(resumed, 2, 12)
    assert resumed.plan_system.plans[0].status == "completed"
    assert len(resumed.plan_system.execution_records) == 2


def test_terminal_source_abandons_stale_plan_before_action(tmp_path):
    engine = town(tmp_path)
    item = accepted_transfer(engine)
    engine.plan_system.ensure_commitment_plans(1)
    plan = engine.plan_system.plans[0]
    engine.commitment_system.transition(item.id, "cancelled", day=2, reason="cancelled")
    assert engine.plan_system.opportunities_for_agent("agent_001", day=2, tick=8) == []
    assert plan.status == "abandoned"
    assert plan.terminal_reason == "source_cancelled"


def test_unavailable_resource_has_bounded_observations_and_private_failure_memory(tmp_path):
    engine = town(tmp_path)
    item = accepted_transfer(engine)
    item.metadata = {"good_id": "reference_book", "quantity": 999}
    for hour in (8, 12, 18):
        engine.plan_system.opportunities_for_agent("agent_001", day=2, tick=hour)
    plan = engine.plan_system.plans[0]
    assert plan.status == "failed"
    assert plan.steps[0].attempts == 3
    assert len([event for event in plan.transitions if event["type"] == "blocked"]) == 3
    actor, counterpart = engine.agents[:2]
    memories = [memory for memory in actor.memory if memory.type == "plan_failed"]
    assert len(memories) == 1
    assert memories[0].owner_id == actor.id
    assert memories[0].knowledge_basis == "self_action"
    assert not [memory for memory in counterpart.memory if memory.type == "plan_failed"]
    assert f"source_id:{plan.id}" in memories[0].tags
    assert not [memory for memory in engine.agents[2].memory
                if f"source_id:{item.id}" in memory.tags]


def test_plan_interruption_preserves_step_and_later_resumes(tmp_path):
    engine = town(tmp_path)
    accepted_transfer(engine)
    with patch("src.behavior.planner.random.random", return_value=0.99):
        engine.activity_system.run_agent_activities(
            [engine.agents[0]], [place.id for place in engine.locations],
            2, 8, None, {},
        )
    plan = engine.plan_system.plans[0]
    assert plan.status == "active" and plan.current_step_index == 0
    run_actor(engine, 2, 12)
    assert plan.current_step_index == 1


def test_success_memories_are_pair_private_and_idempotent(tmp_path):
    engine = town(tmp_path)
    item = accepted_transfer(engine)
    run_actor(engine, 2, 8)
    run_actor(engine, 2, 12)
    engine.plan_system.ensure_commitment_plans(2)
    for agent in engine.agents[:2]:
        matching = [memory for memory in agent.memory
                    if f"source_id:{item.id}" in memory.tags]
        assert {memory.type for memory in matching} == {
            "commitment_accepted", "commitment_fulfilled",
        }
        assert len({memory.id for memory in matching}) == 2
    assert not [memory for memory in engine.agents[2].memory
                if f"source_id:{item.id}" in memory.tags]


def test_plan_model_rejects_unbounded_or_unknown_steps():
    with pytest.raises(ValueError, match="unknown plan action"):
        PlanStep("bad", "invent_resource")
    with pytest.raises(ValueError, match="one to four"):
        AgentPlan("p", "a", "x", "commitment", "c", 1, [])
