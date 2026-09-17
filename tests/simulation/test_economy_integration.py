import json
import pytest

from src.behavior.activity import Activity
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.materials import MaterialError


def build_engine(tmp_path, *, load_state=False):
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=load_state,
        llm_client=FakeLLMClient(),
        state_path=tmp_path / "state.json",
        logs_dir=tmp_path / "logs",
    )


def test_engine_initializes_employment_for_all_v1_agents(tmp_path):
    engine = build_engine(tmp_path)
    assert len(engine.economy.employments) == 4
    assert {
        job.agent_id for job in engine.economy.employments.values()
    } == {agent.id for agent in engine.agents}
    assert all(
        job.title == next(agent.occupation for agent in engine.agents if agent.id == job.agent_id)
        for job in engine.economy.employments.values()
    )


def test_configured_jobs_match_explicit_planner_work_activities(tmp_path):
    engine = build_engine(tmp_path)
    location_ids = [location.id for location in engine.locations]
    for agent in engine.agents:
        job = engine.economy.employment_for_agent(agent.id)
        candidates = engine.activity_planner.get_candidate_activities(
            agent, location_ids
        )
        assert any(
            activity.id in job.qualifying_activity_ids and "work" in activity.tags
            for activity in candidates
        )
    maya = next(agent for agent in engine.agents if agent.id == "agent_001")
    maya.needs = {"social": 0, "wealth": 50, "knowledge": 50}
    candidates = engine.activity_planner.get_candidate_activities(maya, location_ids)
    assert any(
        activity.id == "buy_meal" and "purchase" in activity.tags
        for activity in candidates
    )
    assert any(
        activity.id == "eat_meal" and "consume" in activity.tags
        for activity in candidates
    )


def test_engine_state_round_trip_preserves_economy_and_blocks_repayment(tmp_path):
    engine = build_engine(tmp_path)
    maya = next(agent for agent in engine.agents if agent.id == "agent_001")
    work = Activity(
        "investigate_story",
        "Investigate a possible story",
        "town_square",
        "Assigned reporting shift",
        ["journalism", "work"],
    )
    engine.economy.process_activity(maya, work, day=2, hour=8)
    engine.state.save(engine, 2, 8, day_complete=False)

    resumed = build_engine(tmp_path, load_state=True)
    before = resumed.economy.to_dict()
    resumed_maya = next(agent for agent in resumed.agents if agent.id == "agent_001")
    assert resumed.economy.process_activity(resumed_maya, work, day=2, hour=12) is None
    assert resumed.economy.to_dict()["ledger"] == before["ledger"]
    assert resumed.economy.get_account("account:agent:agent_001").balance == 125


def test_v1_state_without_economy_initializes_deterministically(tmp_path):
    engine = build_engine(tmp_path)
    engine.state.save(engine, 1, 8)
    state_path = tmp_path / "state.json"
    legacy = json.loads(state_path.read_text())
    legacy.pop("economy")
    legacy.pop("materials")
    legacy.pop("crime")
    state_path.write_text(json.dumps(legacy))

    first = build_engine(tmp_path, load_state=True)
    expected = first.economy.to_dict()
    # Loading the same legacy payload again produces the same starting economy.
    state_path.write_text(json.dumps(legacy))
    second = build_engine(tmp_path, load_state=True)
    assert second.economy.to_dict() == expected
    assert second.economy.diagnostics()["currency_conserved"] is True


def test_phase_one_state_without_materials_initializes_safely(tmp_path):
    engine = build_engine(tmp_path)
    engine.state.save(engine, 1, 8)
    state_path = tmp_path / "state.json"
    phase_one = json.loads(state_path.read_text())
    phase_one.pop("materials")
    phase_one.pop("crime")
    state_path.write_text(json.dumps(phase_one))

    resumed = build_engine(tmp_path, load_state=True)
    assert len(resumed.materials.goods) == 4
    assert len(resumed.materials.sellers) == 1
    assert resumed.materials.diagnostics()["material_conserved_with_consumption"]


def test_material_purchase_persists_and_cannot_replay_after_resume(tmp_path):
    engine = build_engine(tmp_path)
    maya = next(agent for agent in engine.agents if agent.id == "agent_001")
    inventory = engine.materials.inventory_for_agent(maya.id)
    account = engine.economy.account_for_agent(maya.id)
    exchange = engine.materials.purchase(
        inventory.id,
        account.id,
        "seller:market_stall",
        "prepared_meal",
        1,
        day=1,
        hour=8,
        event_key="purchase:resume-test",
    )
    engine.state.save(engine, 1, 8, day_complete=False)

    resumed = build_engine(tmp_path, load_state=True)
    assert resumed.materials.quantity(inventory.id, "prepared_meal") == 1
    assert resumed.materials.exchanges[0].id == exchange.id
    before_balance = resumed.economy.get_account(account.id).balance
    with pytest.raises(MaterialError) as error:
        resumed.materials.purchase(
            inventory.id,
            account.id,
            "seller:market_stall",
            "prepared_meal",
            1,
            day=1,
            hour=12,
            event_key="purchase:resume-test",
        )
    assert error.value.code == "duplicate_event"
    assert resumed.economy.get_account(account.id).balance == before_balance
    assert resumed.materials.quantity(inventory.id, "prepared_meal") == 1


def test_material_consumption_persists_and_cannot_replay_after_resume(tmp_path):
    engine = build_engine(tmp_path)
    maya = next(agent for agent in engine.agents if agent.id == "agent_001")
    inventory = engine.materials.inventory_for_agent(maya.id)
    account = engine.economy.account_for_agent(maya.id)
    engine.materials.purchase(
        inventory.id,
        account.id,
        "seller:market_stall",
        "prepared_meal",
        1,
        day=1,
        hour=8,
        event_key="purchase:consumption-resume",
    )
    engine.materials.consume(
        maya,
        inventory.id,
        "prepared_meal",
        1,
        day=1,
        hour=12,
        activity_id="eat_meal",
        event_key="consume:resume-test",
    )
    engine.state.save(engine, 1, 12, day_complete=False)

    resumed = build_engine(tmp_path, load_state=True)
    resumed_maya = next(agent for agent in resumed.agents if agent.id == maya.id)
    need_before = resumed_maya.needs["social"]
    with pytest.raises(MaterialError) as error:
        resumed.materials.consume(
            resumed_maya,
            inventory.id,
            "prepared_meal",
            1,
            day=1,
            hour=18,
            activity_id="eat_meal",
            event_key="consume:resume-test",
        )
    assert error.value.code == "duplicate_event"
    assert resumed.materials.quantity(inventory.id, "prepared_meal") == 0
    assert resumed_maya.needs["social"] == need_before
    assert len(resumed.materials.consumptions) == 1


def test_activity_system_can_trigger_configured_purchase(tmp_path):
    engine = build_engine(tmp_path)
    maya = next(agent for agent in engine.agents if agent.id == "agent_001")
    activity = Activity(
        "buy_meal",
        "Buy a prepared meal",
        "market",
        "Normal purchase activity",
        ["purchase"],
    )

    class FixedPlanner:
        def choose_activity(self, **kwargs):
            return activity

    engine.activity_system.activity_planner = FixedPlanner()
    engine.activity_system.run_agent_activities(
        agents=[maya],
        location_ids=["market"],
        day=1,
        hour=8,
        current_daily_event=None,
        agent_intents={},
    )
    assert len(engine.materials.exchanges) == 1
    assert engine.materials.quantity(
        "inventory:agent:agent_001", "prepared_meal"
    ) == 1


def test_activity_system_is_the_engine_wage_integration_point(tmp_path):
    engine = build_engine(tmp_path)
    maya = next(agent for agent in engine.agents if agent.id == "agent_001")
    work = Activity(
        "investigate_story",
        "Investigate a possible story",
        "town_square",
        "Assigned reporting shift",
        ["journalism", "work"],
    )

    class FixedPlanner:
        def choose_activity(self, **kwargs):
            return work

    engine.activity_system.activity_planner = FixedPlanner()
    engine.run_agent_activities(day=1, hour=8)
    wages = [item for item in engine.economy.ledger if item.transaction_type == "wage"]
    assert len(wages) == 1
    assert dict(wages[0].metadata)["agent_id"] == maya.id
    assert engine.activity_records[0]["activity_id"] == "investigate_story"
