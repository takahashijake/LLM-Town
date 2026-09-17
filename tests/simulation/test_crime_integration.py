from src.behavior.activity import Activity
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def build_engine(tmp_path):
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        llm_client=FakeLLMClient(),
        state_path=tmp_path / "state.json",
        logs_dir=tmp_path / "logs",
    )


def test_normal_activity_pipeline_can_trigger_validated_theft(tmp_path):
    engine = build_engine(tmp_path)
    activities = {
        "agent_001": Activity("read", "Read", "library", "Study", ["knowledge"]),
        "agent_002": Activity(
            "attempt_theft",
            "Attempt to take unattended trade supplies",
            "market",
            "Narrow configured theft route",
            ["unauthorized_take"],
        ),
        "agent_003": Activity("read", "Read", "library", "Study", ["knowledge"]),
        "agent_004": Activity(
            "pursue_business", "Work at market", "market", "Merchant work", ["work"]
        ),
    }

    class PerAgentPlanner:
        def choose_activity(self, *, agent, **_kwargs):
            return activities[agent.id]

    engine.activity_system.activity_planner = PerAgentPlanner()
    source_before = engine.materials.quantity(
        "inventory:agent:agent_004", "trade_materials"
    )
    engine.run_agent_activities(day=4, hour=12)

    assert len(engine.crime.incidents) == 1
    assert engine.materials.quantity(
        "inventory:agent:agent_004", "trade_materials"
    ) == source_before - 1
    assert engine.materials.quantity(
        "inventory:agent:agent_002", "trade_materials"
    ) == 1
    assert engine.materials.exchanges == []
    assert engine.economy.diagnostics()["currency_conserved"]


def test_planner_exposes_theft_only_to_narrow_configured_personality(tmp_path):
    engine = build_engine(tmp_path)
    location_ids = [location.id for location in engine.locations]
    ethan = next(agent for agent in engine.agents if agent.id == "agent_002")
    maya = next(agent for agent in engine.agents if agent.id == "agent_001")
    ethan.needs = {"social": 80, "wealth": 5, "knowledge": 80}
    maya.needs = {"social": 80, "wealth": 5, "knowledge": 80}

    ethan_candidates = engine.activity_planner.get_candidate_activities(
        ethan, location_ids
    )
    maya_candidates = engine.activity_planner.get_candidate_activities(maya, location_ids)
    assert any(activity.id == "attempt_theft" for activity in ethan_candidates)
    assert not any(activity.id == "attempt_theft" for activity in maya_candidates)

