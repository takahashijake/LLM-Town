from src.analysis.population_growth_evaluation import evaluate_population_growth


def test_population_growth_evaluation_passes_with_long_horizon_coverage():
    result = evaluate_population_growth()
    assert result["passed"], result["diagnostics"]
    assert result["scenario_count"] >= 40
    assert result["scenarios_passed"] == result["scenario_count"]
    assert result["invariant_count"] >= 12
    assert result["invariants_passed"] == result["invariant_count"]
