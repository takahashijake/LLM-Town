from src.analysis.goal_composite_dependency_evaluation import (
    evaluate_goal_composite_dependencies,
)


def test_goal_composite_dependency_evaluation_passes_with_named_coverage():
    result = evaluate_goal_composite_dependencies()
    assert result["passed"], result["diagnostics"]
    assert result["scenario_count"] >= 30
    assert result["invariant_count"] >= 7
    assert result["scenarios"]["composite_strategy_runtime_selectable"]
    assert result["scenarios"]["retained_ownership_and_later_event_permit_progress"]
    assert result["scenarios"]["malformed_composite_fails_closed"]
    assert result["scenarios"]["due_v3_commitment_preempts_goal_activity"]
    assert result["invariants"]["ordered_dependency_bound_holds"]
