import json

from src.analysis.v2_evaluation import run_v2_evaluation, write_v2_evaluation


def test_whole_v2_evaluation_passes_and_writes_machine_readable_result(tmp_path):
    result = run_v2_evaluation(tmp_path / "work")
    assert result["passed"]
    assert all(result["hard_invariants"].values())
    assert result["long_horizon"]["days"] == 30
    output = tmp_path / "v2.json"
    write_v2_evaluation(result, output)
    assert json.loads(output.read_text()) == result
