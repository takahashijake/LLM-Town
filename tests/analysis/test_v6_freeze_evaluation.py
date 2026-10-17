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


def test_actual_horizon_continuation_is_independent_of_intervening_engine(tmp_path):
    """Real legacy engines must resume the horizon witness, not the caller RNG."""
    import random
    from src.analysis.procedural_institution_evaluation import _horizon, _run, _engine
    from src.analysis.v6_freeze_evaluation import MultiBranchProvider, write_config
    from src.analysis.growth_audits import authoritative_signature
    config = write_config(tmp_path)
    original = random.getstate()
    results = []
    try:
        for caller_seed in (1, 77):
            random.seed(caller_seed)
            caller = random.getstate()
            captured = []
            town = _horizon(tmp_path, f'world-{caller_seed}', config, (2,),
                            MultiBranchProvider(), rng_checkpoint=captured)
            assert random.getstate() == caller
            # A separate engine consumes arbitrary process RNG between runs.
            _horizon(tmp_path, f'interference-{caller_seed}', config, (1,), MultiBranchProvider())
            random.random()
            town = _engine(tmp_path, f'world-{caller_seed}', config, MultiBranchProvider(), load=True)
            random.setstate(captured[0])
            _run(town, 2)
            results.append(authoritative_signature(town))
        assert results[0] == results[1]
    finally:
        random.setstate(original)
