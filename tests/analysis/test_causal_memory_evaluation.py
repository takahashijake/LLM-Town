from src.analysis.causal_memory_evaluation import evaluate_causal_memory


def test_causal_memory_evaluation_passes():
    result = evaluate_causal_memory()
    assert result["passed"], result
    assert result["scenario_count"] == 12
    assert result["scenarios_passed"] == 12
    assert result["invariant_count"] == 14
    assert result["invariants_passed"] == 14
    assert result["diagnostics"] == {
        "failed_scenarios": [], "failed_invariants": [],
    }
