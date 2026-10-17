"""Release runner uses real engines while retaining the caller's RNG contract."""
import json
import os
import random
import subprocess
import sys

import pytest

from src.analysis.growth_audits import authoritative_signature
from src.analysis.procedural_institution_evaluation import _engine, _horizon, _run
from src.analysis.release_replay import evaluate_release_replay
from src.analysis.v6_freeze_evaluation import MultiBranchProvider, write_config


def test_real_horizon_continuation_is_independent_of_caller_and_other_engines(tmp_path):
    """V10's capacity-tail correction also holds with actual growth authority."""
    config = write_config(tmp_path)
    caller = random.getstate()
    try:
        expected = _horizon(tmp_path, 'expected', config, (2,), MultiBranchProvider())
        captures = []
        for index, seed in enumerate((1, 77)):
            random.seed(seed)
            before = random.getstate()
            continuation = []
            town = _horizon(tmp_path, f'partial-{index}', config, (1,), MultiBranchProvider(),
                            rng_checkpoint=continuation)
            assert random.getstate() == before
            # Another real engine runs between prefix and continuation.
            _horizon(tmp_path, f'interference-{index}', config, (3,), MultiBranchProvider())
            town = _engine(tmp_path, f'partial-{index}', config, MultiBranchProvider(), load=True)
            random.setstate(continuation[0])
            _run(town, 1)
            captures.append(authoritative_signature(town))
        assert captures[0] == captures[1] == authoritative_signature(expected)
    finally:
        random.setstate(caller)


def test_unknown_scenario_is_rejected_before_any_worker_runs():
    with pytest.raises(ValueError, match='unknown release replay scenario'):
        evaluate_release_replay(scenarios=('untrusted-command',))


@pytest.mark.integration
def test_legacy_replay_matrix_runs_in_fresh_processes_and_preserves_caller(tmp_path):
    before = random.getstate()
    result = evaluate_release_replay(scenarios=('legacy',))
    assert random.getstate() == before
    assert result['status'] == 'PASS', result['checks']
    assert len(result['runs']) == 4
    assert {r['hash_seed'] for r in result['runs']} == {'1', '77'}
    assert len({json.dumps(r['signatures'], sort_keys=True) for r in result['runs']}) == 1
    assert 'harness RNG sidecar' in result['rng_contract']
    assert all(r['observations']['save_bytes'] > 0 for r in result['runs'])


def test_replay_cli_refuses_existing_output_before_work(tmp_path):
    path = tmp_path / 'report.json'
    path.write_text('preserve')
    result = subprocess.run([sys.executable, 'scripts/evaluate_release_replay.py', '--output', str(path)],
                            capture_output=True, timeout=10, env={**os.environ, 'PYTHONHASHSEED': '1'})
    assert result.returncode == 2 and path.read_text() == 'preserve'
    assert list(tmp_path.iterdir()) == [path]
