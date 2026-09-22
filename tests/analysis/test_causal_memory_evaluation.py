from src.analysis.causal_memory_evaluation import evaluate_causal_memory


def test_causal_memory_evaluation_passes():
    result = evaluate_causal_memory()
    assert result["passed"], result
