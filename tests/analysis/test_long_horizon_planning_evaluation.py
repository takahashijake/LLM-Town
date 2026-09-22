from src.analysis.long_horizon_planning_evaluation import evaluate_long_horizon_planning


def test_long_horizon_planning_evaluation_passes():
    result = evaluate_long_horizon_planning()
    assert result["passed"]
    assert all(result["scenarios"].values())
    assert all(result["invariants"].values())
