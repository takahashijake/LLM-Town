import json

from src.analysis.causal_memory_stress import analyze_stress_state


def test_stress_inspector_reports_bounded_empty_state(fake_engine, tmp_path):
    path = tmp_path / "state.json"
    fake_engine.state.path = path
    fake_engine.state.save(fake_engine, 1, 8)
    result = analyze_stress_state(path)
    assert result["passed"], json.dumps(result, indent=2)
