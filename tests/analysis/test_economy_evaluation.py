from src.analysis.economy_evaluation import run_economy_evaluation


def test_economy_evaluation_passes_and_is_deterministic(tmp_path):
    first = run_economy_evaluation(tmp_path / "one")
    second = run_economy_evaluation(tmp_path / "two")
    assert first == second
    assert first["passed"] is True
    assert all(first["invariants"].values())
    assert first["diagnostics"]["wage_payment_count"] == 4
    assert first["diagnostics"]["rejected_transaction_count"] == 1

