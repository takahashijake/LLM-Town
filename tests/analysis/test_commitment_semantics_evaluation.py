from src.analysis.commitment_semantics_evaluation import run_commitment_semantics_evaluation


def test_commitment_semantics_golden_evaluation_passes():
    result = run_commitment_semantics_evaluation(".")
    assert result["result"] == "PASS", result["failures"]
    assert 40 <= result["corpus"]["examples"] <= 60
    assert result["metrics"]["commitment_creation_precision"] == 1.0
    assert result["metrics"]["clear_acceptance_recall"] == 1.0
    assert result["metrics"]["false_commitment_creation_rate"] == 0.0
