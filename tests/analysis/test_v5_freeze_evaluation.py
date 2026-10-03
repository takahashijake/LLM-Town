from src.analysis.v5_freeze_evaluation import evaluate_v5_freeze


def test_v5_freeze_evaluation_passes():
    result = evaluate_v5_freeze()
    assert result["passed"], result["diagnostics"]
