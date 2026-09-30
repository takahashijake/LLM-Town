from src.analysis.v4_freeze_evaluation import evaluate_v4_freeze


def test_v4_freeze_evaluation_passes_with_integrated_coverage():
    result = evaluate_v4_freeze()
    assert result["passed"], result["diagnostics"]
    assert result["scenario_count"] >= 50
    assert result["scenarios_passed"] == result["scenario_count"]
    assert result["invariant_count"] >= 14
    assert result["invariants_passed"] == result["invariant_count"]
