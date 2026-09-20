import pytest

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def town(tmp_path, load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=tmp_path / "state.json",
        logs_dir=tmp_path / ("loaded-logs" if load else "logs"),
    )


def accepted(system, *, kind, proposer="agent_001", actor="agent_004", due=2, metadata=None):
    item = system.create(
        proposer_id=proposer, counterpart_id=actor, commitment_type=kind,
        day=1, due_day=due, metadata=metadata or {}, status="proposed",
    )
    system.transition(item.id, "accepted", day=1, reason="accepted")
    return item


def test_candidate_generation_priority_is_monotonic_and_bounded(tmp_path):
    engine = town(tmp_path)
    item = accepted(engine.commitment_system, kind="help", due=5,
                    metadata={"task": "repair fence"})
    values = [engine.commitment_system.urgency(item, day) for day in (1, 4, 5)]
    assert values[0] < values[1] <= values[2] <= 1.0
    candidate = engine.commitment_system.opportunities_for_agent("agent_004", day=5)[0]
    assert candidate.commitment_id == item.id
    assert candidate.provenance == f"commitment:{item.id}"


@pytest.mark.parametrize("status", ["declined", "cancelled", "expired", "fulfilled"])
def test_terminal_commitments_have_no_candidates(tmp_path, status):
    engine = town(tmp_path)
    item = engine.commitment_system.create(
        proposer_id="agent_001", counterpart_id="agent_004", commitment_type="help",
        day=1, due_day=1, metadata={"task": "repair fence"}, status="proposed",
    )
    if status == "declined":
        engine.commitment_system.transition(item.id, status, day=1, reason=status)
    else:
        engine.commitment_system.transition(item.id, "accepted", day=1, reason="accepted")
        evidence = {"activity_event_key": "test:activity"} if status == "fulfilled" else None
        engine.commitment_system.transition(item.id, status, day=2, reason=status, evidence=evidence)
    assert engine.commitment_system.opportunities_for_agent("agent_004", day=2) == []


def test_transfer_feasibility_and_authoritative_execution(tmp_path, monkeypatch):
    engine = town(tmp_path)
    item = accepted(
        engine.commitment_system, kind="transfer", due=2,
        metadata={"good_id": "trade_materials", "quantity": 1},
    )
    opportunity = engine.commitment_system.opportunities_for_agent("agent_004", day=2)[0]
    assert opportunity.feasibility == "feasible"
    monkeypatch.setattr("src.behavior.planner.random.random", lambda: 0.0)
    engine.activity_system.run_agent_activities(
        agents=[engine.agents[3]], location_ids=[location.id for location in engine.locations],
        day=2, hour=8, current_daily_event=None, agent_intents={},
    )
    assert item.status == "fulfilled"
    record = engine.commitment_system.execution_records[0]
    assert record["source_commitment_id"] == item.id
    assert record["material_transfer_id"]
    assert engine.activity_records[-1]["source_commitment_id"] == item.id
    engine.materials._validate_history()


def test_transfer_without_resource_remains_active_then_expires(tmp_path):
    engine = town(tmp_path)
    item = accepted(
        engine.commitment_system, kind="transfer", proposer="agent_002",
        actor="agent_001", due=2,
        metadata={"good_id": "trade_materials", "quantity": 1},
    )
    candidate = engine.commitment_system.opportunities_for_agent("agent_001", day=2)[0]
    assert candidate.feasibility == "temporarily_infeasible"
    assert candidate.infeasibility_reason == "resource_unavailable"
    assert item.status == "accepted"
    engine.commitment_system.expire_due(day=3)
    assert item.status == "expired"
    assert not engine.commitment_system.execution_records


@pytest.mark.parametrize("kind,metadata,location", [
    ("help", {"task": "repair fence"}, "town_square"),
    ("meet", {"location": "cafe"}, "cafe"),
])
def test_help_and_meet_execute_with_activity_provenance(
    tmp_path, monkeypatch, kind, metadata, location,
):
    engine = town(tmp_path)
    proposer, actor = engine.agents[0], engine.agents[3]
    proposer.location_id = actor.location_id = location
    item = accepted(engine.commitment_system, kind=kind, due=2, metadata=metadata)
    monkeypatch.setattr("src.behavior.planner.random.random", lambda: 0.0)
    engine.activity_system.run_agent_activities(
        agents=[actor], location_ids=[place.id for place in engine.locations],
        day=2, hour=8, current_daily_event=None, agent_intents={},
    )
    assert item.status == "fulfilled"
    assert item.evidence[-1]["source_commitment_id"] == item.id
    assert engine.commitment_system.execution_records[0]["commitment_type"] == kind


def test_meet_counterpart_unavailable_is_temporary(tmp_path):
    engine = town(tmp_path)
    engine.agents[0].location_id = "library"
    item = accepted(engine.commitment_system, kind="meet", due=2,
                    metadata={"location": "cafe"})
    candidate = engine.commitment_system.opportunities_for_agent("agent_004", day=2)[0]
    assert candidate.feasibility == "temporarily_infeasible"
    assert candidate.infeasibility_reason == "counterpart_unavailable"
    assert item.status == "accepted"


def test_missing_counterpart_is_impossible(tmp_path):
    engine = town(tmp_path)
    item = accepted(engine.commitment_system, kind="help", proposer="missing", due=2,
                    metadata={"task": "repair fence"})
    candidate = engine.commitment_system.opportunities_for_agent("agent_004", day=2)[0]
    assert candidate.feasibility == "impossible"
    assert candidate.infeasibility_reason == "missing_agent"
    assert item.status == "accepted"


def test_commitment_pressure_does_not_force_selection(tmp_path, monkeypatch):
    engine = town(tmp_path)
    actor = engine.agents[3]
    accepted(engine.commitment_system, kind="help", due=2,
             metadata={"task": "repair fence"})
    monkeypatch.setattr("src.behavior.planner.random.random", lambda: 0.99)
    activity = engine.activity_planner.choose_activity(
        agent=actor, location_ids=[place.id for place in engine.locations],
        current_day=2, hour=8,
        commitment_opportunities=engine.commitment_system.opportunities_for_agent(
            actor.id, day=2, tick=8,
        ),
    )
    assert activity.source_commitment_id is None


def test_save_load_preserves_execution_provenance_and_no_duplicate(tmp_path, monkeypatch):
    engine = town(tmp_path)
    item = accepted(
        engine.commitment_system, kind="transfer", due=2,
        metadata={"good_id": "trade_materials", "quantity": 1},
    )
    monkeypatch.setattr("src.behavior.planner.random.random", lambda: 0.0)
    engine.activity_system.run_agent_activities(
        agents=[engine.agents[3]], location_ids=[place.id for place in engine.locations],
        day=2, hour=8, current_daily_event=None, agent_intents={},
    )
    engine.state.save(engine, 2, 8)
    resumed = town(tmp_path, load=True)
    assert resumed.commitment_system.execution_records == engine.commitment_system.execution_records
    assert resumed.commitment_system.opportunities_for_agent("agent_004", day=2) == []
    assert resumed.commitment_system.get(item.id).status == "fulfilled"
    assert all(resumed.commitment_system.validate_invariants().values())
