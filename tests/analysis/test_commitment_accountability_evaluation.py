from src.analysis.commitment_accountability_evaluation import evaluate_commitment_accountability


def test_commitment_accountability_evaluator_passes():
    result = evaluate_commitment_accountability()
    assert result["passed"]
    assert result["funnel"]["false_fulfillment"] == 0
    assert all(result["scenarios"].values())
    assert all(result["invariants"].values())
