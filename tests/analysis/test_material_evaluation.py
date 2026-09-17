from src.analysis.material_evaluation import run_material_evaluation


def test_material_evaluation_passes_and_is_deterministic(tmp_path):
    first = run_material_evaluation(tmp_path / "one")
    second = run_material_evaluation(tmp_path / "two")
    assert first == second
    assert first["passed"] is True
    assert all(first["invariants"].values())
    assert first["material_diagnostics"]["exchange_count"] == 1
    assert first["material_diagnostics"]["consumption_count"] == 1
    assert first["material_diagnostics"]["idempotency_rejections"] == 2
    assert first["failed_purchase"]["no_partial_mutation"] is True

