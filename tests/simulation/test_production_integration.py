from src.behavior.activity import Activity
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


class RestockPlanner:
    def choose_activity(self, **_kwargs):
        return Activity("restock_market", "Restock market", "market",
                        "Configured merchant production", ["work", "production"])


def test_activity_system_runs_authoritative_restock_and_guard(tmp_path):
    engine = SimulationEngine(
        agents_path="data/agents.json", locations_path="data/locations.json",
        llm_client=FakeLLMClient(), state_path=tmp_path / "state.json",
        logs_dir=tmp_path / "logs",
    )
    market = "inventory:business:market_stall"
    buyer = engine.agents[0]
    engine.materials.purchase(
        engine.materials.inventory_for_agent(buyer.id).id,
        engine.economy.account_for_agent(buyer.id).id,
        "seller:market_stall", "prepared_meal", 1, day=1, hour=7,
        event_key="integration:deplete",
    )
    engine.activity_system.activity_planner = RestockPlanner()
    engine.activity_system.run_agent_activities(
        engine.agents, ["market"], 1, 8, None, {},
    )
    assert engine.materials.quantity(market, "prepared_meal") == 27
    assert len(engine.materials.production_records) == 1
    assert engine.materials.production_records[0].actor_id == "agent_004"
    # A later proposed shift is still legitimate work/wage behavior, but the
    # material target guard prevents another production mutation.
    engine.activity_system.run_agent_activities(
        engine.agents, ["market"], 1, 12, None, {},
    )
    assert len(engine.materials.production_records) == 1
    assert any(item["code"] == "target_stock_met"
               for item in engine.materials.rejected_operations)
    assert engine.materials.provenance_reconciles()

