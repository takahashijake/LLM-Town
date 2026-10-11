import pytest

from src.analysis.v6_freeze_evaluation import evaluate_v6_freeze


@pytest.mark.integration
def test_v6_freeze_passes():
    result = evaluate_v6_freeze()
    assert result['passed'], result['diagnostics']['failed']
    assert result['replay_checkpoint_count'] >= 20
    assert result['mutation_count'] >= 500


def test_horizon_preserves_caller_and_captures_actual_continuation(monkeypatch, tmp_path):
    import random
    from src.analysis import procedural_institution_evaluation as helpers
    captured = []
    def run(town, days):
        town.extend(random.randrange(1000) for _ in range(days))
    monkeypatch.setattr(helpers, '_engine', lambda *args, **kwargs: [])
    monkeypatch.setattr(helpers, '_run', run)
    original = random.getstate()
    try:
        trajectories = []
        for seed in (1, 77):
            random.seed(seed)
            caller = random.getstate()
            town = helpers._horizon(tmp_path, 'fixture', tmp_path/'config', (5,), None,
                                    rng_checkpoint=captured)
            assert random.getstate() == caller
            random.setstate(captured[-1])
            run(town, 5)
            trajectories.append(town)
        expected = random.Random(23)
        assert trajectories[0] == trajectories[1] == [expected.randrange(1000) for _ in range(10)]
        assert captured[0] == captured[1]
    finally:
        random.setstate(original)


def test_failed_horizon_does_not_publish_rng_checkpoint(monkeypatch, tmp_path):
    import random
    from src.analysis import procedural_institution_evaluation as helpers
    captured = []
    def failed(*args):
        random.random()
        raise ValueError('failed trajectory')
    monkeypatch.setattr(helpers, '_engine', lambda *args, **kwargs: [])
    monkeypatch.setattr(helpers, '_run', failed)
    original = random.getstate()
    with pytest.raises(ValueError):
        helpers._horizon(tmp_path, 'fixture', tmp_path/'config', (5,), None, rng_checkpoint=captured)
    assert not captured and random.getstate() == original
