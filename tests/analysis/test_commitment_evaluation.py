from src.analysis.commitment_evaluation import run_commitment_evaluation


def test_commitment_evaluation_passes_and_emits_required_metrics(tmp_path):
    result = run_commitment_evaluation(tmp_path, ".")
    assert result["passed"]
    assert all(result["hard_invariants"].values())
    assert result["metrics"]["persistence_round_trip_success"]
    assert result["metrics"]["duplicate_mutation_attempts"] == 1
    assert result["metrics"]["illegal_state_transition_attempts"] == 1
