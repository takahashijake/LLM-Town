from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def test_engine_uses_injected_state_and_log_paths(tmp_path):
    state_path = tmp_path / "state" / "checkpoint.json"
    logs_dir = tmp_path / "experiment-logs"

    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        llm_client=FakeLLMClient(),
        state_path=state_path,
        logs_dir=logs_dir,
    )

    assert engine.state.path == state_path
    assert engine.logger.logs_dir == logs_dir
    assert engine.logger.events_file == logs_dir / "events" / "events.jsonl"
    assert engine.logger.conversations_file == (
        logs_dir / "conversations" / "conversations.jsonl"
    )
    assert engine.town_arc_system.arc_changes_path == (
        logs_dir / "town_arc_changes.jsonl"
    )
