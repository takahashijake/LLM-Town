from src.analysis.institution_growth_evaluation import evaluate_institution_growth


def test_institution_growth_evaluation_passes():
    result = evaluate_institution_growth()
    assert result["passed"], result["diagnostics"]
