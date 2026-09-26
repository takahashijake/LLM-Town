from src.analysis.goal_planning_evaluation import evaluate_goal_planning


def test_goal_planning_evaluation_passes_with_required_coverage():
    result = evaluate_goal_planning()
    assert result["passed"], result["diagnostics"]
    assert result["scenario_count"] >= 24
    assert result["invariant_count"] >= 10
    assert result["scenarios_passed"] == result["scenario_count"]
    assert result["invariants_passed"] == result["invariant_count"]
