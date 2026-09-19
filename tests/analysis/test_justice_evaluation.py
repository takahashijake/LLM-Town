from src.analysis.justice_evaluation import run_justice_evaluation, write_justice_evaluation


def test_justice_evaluation_passes_and_writes_json(tmp_path):
    result = run_justice_evaluation(tmp_path / "work")
    assert result["passed"]
    assert all(result["invariants"].values())
    output = tmp_path / "justice.json"
    write_justice_evaluation(result, output)
    assert output.exists()
