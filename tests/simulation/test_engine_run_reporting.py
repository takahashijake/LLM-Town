from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def test_run_prints_final_summary_once_for_multi_day_run(capsys):
    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )

    engine.run(days=3, hours=[8])

    output = capsys.readouterr().out

    assert output.count("Simulation finished.") == 1
    assert output.count("=== Final Relationships ===") == 1
    assert output.count("=== Town Summary ===") == 1
    