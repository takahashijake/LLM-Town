from src.analysis.goal_strategy_dependency_evaluation import (
    evaluate_goal_strategy_dependencies,
)


def test_goal_strategy_dependency_evaluation_passes_with_named_coverage():
    result = evaluate_goal_strategy_dependencies()
    assert result["passed"], result["diagnostics"]
    assert result["scenario_count"] >= 10
    assert result["invariant_count"] >= 6
    assert result["scenarios"]["opportunity_absence_blocks_execution"]
    assert result["scenarios"]["exact_execution_after_opportunity_advances"]
    assert result["scenarios"]["due_commitment_preempts_goal_dependency"]
