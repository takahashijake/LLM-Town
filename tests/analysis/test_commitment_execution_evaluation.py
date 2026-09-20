from src.analysis.commitment_execution_evaluation import run_commitment_execution_evaluation


def test_commitment_execution_evaluation_passes(tmp_path):
    result = run_commitment_execution_evaluation(tmp_path, ".")
    assert result["passed"]
    assert result["metrics"]["fulfilled"] == 3
    assert result["metrics"]["expired"] == 1
    assert all(result["hard_invariants"].values())
