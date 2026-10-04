from src.analysis.procedural_institution_evaluation import (
    evaluate_procedural_institutions,
)


def test_procedural_institution_evaluation_passes():
    result = evaluate_procedural_institutions()
    assert result["passed"], result["diagnostics"]
