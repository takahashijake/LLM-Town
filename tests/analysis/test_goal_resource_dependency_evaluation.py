from src.analysis.goal_resource_dependency_evaluation import (
    evaluate_goal_resource_dependencies,
)


def test_goal_resource_dependency_evaluation_passes_with_named_coverage():
    result = evaluate_goal_resource_dependencies()
    assert result["passed"], result["diagnostics"]
    assert result["scenario_count"] >= 12
    assert result["invariant_count"] >= 8
    assert result["scenarios"]["authoritative_purchase_succeeded"]
    assert result["scenarios"]["goal_progressed"]
    assert result["invariants"]["no_progress_from_preparation"]
    assert result["invariants"]["v3_commitment_priority_preserved"]
