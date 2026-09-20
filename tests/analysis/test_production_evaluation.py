from src.analysis.production_evaluation import run_production_evaluation


def test_production_evaluation_passes_and_is_deterministic(tmp_path):
    first = run_production_evaluation(tmp_path / "one")
    second = run_production_evaluation(tmp_path / "two")
    assert first["passed"]
    assert first == second

