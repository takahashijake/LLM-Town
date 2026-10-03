from src.analysis.commerce_growth_evaluation import evaluate_commerce_growth


def test_commerce_growth_evaluation_passes():
    result = evaluate_commerce_growth()
    assert result["passed"], result["diagnostics"]

