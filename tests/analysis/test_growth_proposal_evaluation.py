from src.analysis.growth_proposal_evaluation import evaluate_growth_proposals


def test_growth_proposal_evaluation_passes():
    result = evaluate_growth_proposals()
    assert result["passed"], result["diagnostics"]
    assert result["scenarios_passed"] == result["scenario_count"]
    assert result["invariants_passed"] == result["invariant_count"]
