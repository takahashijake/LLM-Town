from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def test_simulation_runs_one_day_with_fake_llm():
    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )

    engine.run(days=1, hours=[8])

    assert len(engine.agents) > 0
    assert len(engine.activity_records) > 0