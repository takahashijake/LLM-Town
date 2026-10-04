import pytest

from src.analysis.v6_freeze_evaluation import evaluate_v6_freeze


@pytest.mark.integration
def test_v6_freeze_passes():
    result = evaluate_v6_freeze()
    assert result['passed'], result['diagnostics']['failed']
    assert result['replay_checkpoint_count'] >= 20
    assert result['mutation_count'] >= 500
