from src.analysis.v3_freeze_evaluation import evaluate_v3_freeze


def test_v3_freeze_evaluation_passes_with_required_coverage():
    result = evaluate_v3_freeze()
    assert result["passed"], result["diagnostics"]
    assert result["scenario_count"] >= 22
    assert result["scenarios_passed"] == result["scenario_count"]
    assert result["invariants_passed"] == result["invariant_count"]
