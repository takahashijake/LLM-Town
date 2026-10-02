from src.analysis.location_growth_evaluation import evaluate_location_growth


def test_location_growth_evaluation_passes_with_integrated_replay_coverage():
    result = evaluate_location_growth()
    assert result["passed"], result["diagnostics"]
    assert result["scenario_count"] >= 30
    assert result["scenarios_passed"] == result["scenario_count"]
    assert result["invariant_count"] >= 15
    assert result["invariants_passed"] == result["invariant_count"]
