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


def accepted_social(engine, commitment_type, *, metadata, due=2):
    item = engine.commitment_system.create(
        proposer_id="agent_002", counterpart_id="agent_001",
        commitment_type=commitment_type, day=1, due_day=due,
        metadata=metadata, status="proposed",
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
    assert plan.status == "abandoned"
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
    assert item.status == "failed"
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
    with pytest.raises(ValueError, match="unknown bounded plan template"):
        AgentPlan(
            "p", "a", "commitment_invented", "commitment", "c", 1,
            [PlanStep("s", "commitment_help")],
        )
    with pytest.raises(ValueError, match="steps do not match"):
        AgentPlan(
            "p", "a", "commitment_meet", "commitment", "c", 1,
            [PlanStep("s", "commitment_help")],
        )


@pytest.mark.parametrize(("commitment_type", "metadata", "action_type"), [
    ("meet", {"location": "cafe"}, "commitment_meet"),
    ("help", {"task": "review records", "location": "cafe"}, "commitment_help"),
])
def test_concrete_social_commitment_gets_one_stable_bounded_plan(
    tmp_path, commitment_type, metadata, action_type,
):
    engine = town(tmp_path)
    item = accepted_social(engine, commitment_type, metadata=metadata)
    engine.plan_system.ensure_commitment_plans(1)
    engine.plan_system.ensure_commitment_plans(1)
    plan = engine.plan_system.plans[0]
    assert plan.id == f"plan:commitment:agent_001:{item.id}"
    assert plan.plan_type == f"commitment_{commitment_type}"
    assert [step.action_type for step in plan.steps] == [action_type]
    assert len(engine.plan_system.plans) == 1


@pytest.mark.parametrize(("commitment_type", "metadata", "reason"), [
    ("meet", {}, "missing_meeting_location"),
    ("meet", {"location": "cafe"}, "missing_meeting_time"),
    ("help", {"location": "cafe"}, "missing_help_task"),
    ("help", {"task": "review records"}, "missing_help_location"),
])
def test_vague_social_commitment_has_inspectable_no_plan_reason(
    tmp_path, commitment_type, metadata, reason,
):
    engine = town(tmp_path)
    item = accepted_social(
        engine, commitment_type, metadata=metadata,
        due=None if reason.endswith("time") else 2,
    )
    engine.plan_system.ensure_commitment_plans(1)
    assert engine.plan_system.plans == []
    assert engine.plan_system.planning_records == [{
        "commitment_id": item.id, "agent_id": "agent_001",
        "commitment_type": commitment_type, "eligible": False,
        "reason": reason, "day": 1,
    }]


@pytest.mark.parametrize(("commitment_type", "metadata"), [
    ("meet", {"location": "cafe"}),
    ("help", {"task": "review records", "location": "cafe"}),
])
def test_authoritative_social_activity_fulfills_matching_plan_once(
    tmp_path, commitment_type, metadata,
):
    engine = town(tmp_path)
    item = accepted_social(engine, commitment_type, metadata=metadata)
    run_actor(engine, 2, 8)
    plan = engine.plan_system.plans[0]
    assert item.status == "fulfilled"
    assert plan.status == "completed"
    assert len(engine.plan_system.execution_records) == 1
    assert all(any(
        memory.type == "commitment_fulfilled"
        and f"source_id:{item.id}" in memory.tags
        for memory in agent.memory
    ) for agent in engine.agents[:2])
    assert not any(
        f"source_id:{item.id}" in memory.tags
        for memory in engine.agents[2].memory
    )
    record = engine.plan_system.execution_records[0]
    before = engine.plan_system.to_dict()
    engine.plan_system.record_execution(
        plan.id, plan.steps[0].id, day=2, tick=8,
        execution_key=record["execution_key"],
        source_commitment_id=item.id,
        action_type=f"commitment_{commitment_type}",
    )
    assert engine.plan_system.to_dict() == before


def test_temporary_meeting_absence_keeps_plan_pending_and_bounded(tmp_path):
    engine = town(tmp_path)
    accepted_social(engine, "meet", metadata={"location": "library"})
    engine.plan_system.opportunities_for_agent("agent_001", day=2, tick=8)
    engine.plan_system.opportunities_for_agent("agent_001", day=2, tick=8)
    plan = engine.plan_system.plans[0]
    observations = [event for event in plan.transitions
                    if event["type"] == "blocked_observation"]
    assert plan.status == "active" and plan.steps[0].attempts == 0
    assert len(observations) == 1


def test_unproven_or_cross_commitment_execution_cannot_advance_plan(tmp_path):
    engine = town(tmp_path)
    first = accepted_social(engine, "meet", metadata={"location": "cafe"})
    second = accepted_social(
        engine, "help", metadata={"task": "review records", "location": "cafe"},
    )
    engine.plan_system.ensure_commitment_plans(1)
    meet_plan, help_plan = engine.plan_system.plans
    engine.plan_system.record_execution(
        meet_plan.id, meet_plan.steps[0].id, day=2, tick=8,
        execution_key="dialogue-claimed-fulfillment",
        source_commitment_id=first.id, action_type="commitment_meet",
    )
    engine.commitment_system.execution_records.append({
        "event_key": "proof-for-second", "source_commitment_id": second.id,
        "commitment_id": second.id, "activity_id": "commitment_help",
    })
    engine.plan_system.record_execution(
        meet_plan.id, meet_plan.steps[0].id, day=2, tick=8,
        execution_key="proof-for-second",
        source_commitment_id=second.id, action_type="commitment_help",
    )
    assert meet_plan.current_step_index == help_plan.current_step_index == 0
    assert engine.plan_system.execution_records == []


def test_terminal_commitment_synchronizes_plan_without_reopening(tmp_path):
    engine = town(tmp_path)
    item = accepted_social(
        engine, "help", metadata={"task": "review records", "location": "cafe"},
    )
    engine.plan_system.ensure_commitment_plans(1)
    plan = engine.plan_system.plans[0]
    engine.commitment_system.transition(item.id, "failed", day=2, reason="authoritative_failure")
    assert plan.status == "failed"
    engine.plan_system.ensure_commitment_plans(2)
    engine.plan_system.ensure_commitment_plans(3)
    assert plan.status == "failed"
    assert len(engine.plan_system.plans) == 1


def test_social_plan_save_resume_before_and_after_execution_is_idempotent(tmp_path):
    engine = town(tmp_path)
    item = accepted_social(engine, "meet", metadata={"location": "cafe"})
    engine.plan_system.ensure_commitment_plans(1)
    stable_id = engine.plan_system.plans[0].id
    engine.state.save(engine, 1, 8)
    resumed = town(tmp_path, load=True)
    assert resumed.plan_system.plans[0].id == stable_id
    run_actor(resumed, 2, 8)
    resumed.state.save(resumed, 2, 8)
    after = town(tmp_path, load=True)
    run_actor(after, 2, 12)
    assert after.commitment_system.get(item.id).status == "fulfilled"
    assert after.plan_system.plans[0].status == "completed"
    assert len(after.plan_system.execution_records) == 1


def test_old_unversioned_plan_save_loads_with_defaults(tmp_path):
    engine = town(tmp_path)
    accepted_transfer(engine)
    engine.plan_system.ensure_commitment_plans(1)
    legacy = engine.plan_system.to_dict()
    legacy.pop("schema_version")
    legacy.pop("planning_records")
    restored = type(engine.plan_system).from_dict(
        legacy, commitment_system=engine.commitment_system,
        agents=engine.agents, outcome_memory=engine.outcome_memory,
    )
    assert restored.planning_records == []
    assert restored.plans[0].source_id == engine.plan_system.plans[0].source_id


def test_loading_terminal_source_with_unproven_active_plan_fails_closed(tmp_path):
    engine = town(tmp_path)
    item = accepted_social(engine, "meet", metadata={"location": "cafe"})
    engine.plan_system.ensure_commitment_plans(1)
    serialized = engine.plan_system.to_dict()
    engine.commitment_system.transition(
        item.id, "fulfilled", day=2, reason="external_authoritative_record",
        evidence={"activity_event_key": "external-proof"},
    )
    restored = type(engine.plan_system).from_dict(
        serialized, commitment_system=engine.commitment_system,
        agents=engine.agents, outcome_memory=engine.outcome_memory,
    )
    assert restored.plans[0].status == "abandoned"
    assert restored.plans[0].steps[0].status == "pending"


def test_pair_context_exposes_lifecycle_without_private_plan_details(tmp_path):
    engine = town(tmp_path)
    item = accepted_social(engine, "meet", metadata={"location": "cafe"})
    engine.plan_system.ensure_commitment_plans(1)
    context = engine.prepare_conversation_context(
        "cafe", engine.agents[0], engine.agents[1], 1,
    )["context"]
    record = next(row for row in context["commitment_records"]
                  if row["commitment_id"] == item.id)
    assert record["status"] == "accepted"
    assert record["plan_stage"] == "pending"
    assert record["lifecycle_state"] == "pending"
    assert "plan_id" not in record and "step_id" not in record


def test_pair_context_distinguishes_preparation_and_active_repair(tmp_path):
    preparing = town(tmp_path / "preparing")
    transfer = accepted_transfer(preparing)
    preparing.plan_system.ensure_commitment_plans(1)
    context = preparing.prepare_conversation_context(
        "cafe", preparing.agents[0], preparing.agents[1], 1,
    )["context"]
    record = next(row for row in context["commitment_records"]
                  if row["commitment_id"] == transfer.id)
    assert record["lifecycle_state"] == "preparing"
    assert record["plan_stage"] == "preparing"

    repair = town(tmp_path / "repair")
    parent = accepted_social(
        repair, "help", metadata={"task": "review records", "location": "cafe"},
        due=1,
    )
    repair.commitment_system.transition(
        parent.id, "failed", day=2, reason="controlled_failure",
    )
    child = repair.commitment_system.create(
        proposer_id="agent_002", counterpart_id="agent_001",
        commitment_type="help", day=2, due_day=3,
        metadata={"task": "review records", "location": "cafe"},
        status="proposed", repair_of_commitment_id=parent.id,
    )
    repair.commitment_system.transition(
        child.id, "accepted", day=2, reason="accepted_repair",
    )
    repair.plan_system.ensure_commitment_plans(2)
    context = repair.prepare_conversation_context(
        "cafe", repair.agents[0], repair.agents[1], 2,
    )["context"]
    record = next(row for row in context["commitment_records"]
                  if row["commitment_id"] == child.id)
    assert record["lifecycle_state"] == "repair_successor_active"
    assert "repair for an earlier commitment" in record["text"].lower()
    for agent in repair.agents[:2]:
        assert any(
            memory.source_id == child.id
            and memory.event_type == "commitment_repair_accepted"
            for memory in agent.memory
        )
    run_actor(repair, 3, 8)
    assert child.status == "fulfilled"
    for agent in repair.agents[:2]:
        assert any(
            memory.source_id == child.id
            and memory.event_type == "commitment_repair_fulfilled"
            for memory in agent.memory
        )
