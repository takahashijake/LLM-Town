from src.analysis.batched_social_evaluation import evaluate_batched_social


def test_batched_social_evaluator_proves_hard_invariants():
    result = evaluate_batched_social()
    assert result["passed"]
    assert result["invariants"] == "11/11 PASS"
    assert result["details"]["repair_batches"] == [
        ["primary", "primary"], ["grounding_retry"],
    ]
    assert result["scaling"]["64"]["sessions"] == 32
