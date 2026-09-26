from src.analysis.goal_strategy_execution_evaluation import (
    evaluate_goal_strategy_execution,
)


def test_goal_strategy_execution_evaluation_passes_with_required_coverage():
    result = evaluate_goal_strategy_execution()
    assert result["passed"], result["diagnostics"]
    assert result["scenario_count"] >= 12
    assert result["invariant_count"] >= 15
    assert result["scenarios_passed"] == result["scenario_count"]
    assert result["invariants_passed"] == result["invariant_count"]
