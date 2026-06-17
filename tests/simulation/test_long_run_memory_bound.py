from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def test_fake_long_run_keeps_memory_bounded():
    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )

    engine.run(days=50, hours=[8, 12, 18, 22])

    for agent in engine.agents:
        assert len(agent.memory) <= 200
        assert len(agent.memory_archive) <= 500