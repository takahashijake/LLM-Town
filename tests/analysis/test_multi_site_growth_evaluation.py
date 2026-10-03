from src.analysis.multi_site_growth_evaluation import evaluate_multi_site_growth


def test_multi_site_growth_evaluation_passes():
    result = evaluate_multi_site_growth()
    assert result["passed"], result["diagnostics"]
