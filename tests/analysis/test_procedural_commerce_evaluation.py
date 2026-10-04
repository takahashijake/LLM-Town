import pytest

from src.analysis.procedural_commerce_evaluation import evaluate_procedural_commerce


@pytest.mark.integration
def test_procedural_commerce_evaluation_passes():
    result = evaluate_procedural_commerce()
    assert result["passed"], result["diagnostics"]
