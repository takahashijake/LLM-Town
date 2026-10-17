"""Release gate isolation and real benchmark persistence observations."""
import json
from pathlib import Path
import subprocess

import pytest

from scripts.verify_release import verify_release, release_gates
from src.analysis.benchmark import BenchmarkConfig, run_benchmark


@pytest.mark.parametrize('failure', ['exit', 'timeout', 'unavailable'])
def test_release_runner_keeps_independent_gates_after_failure(tmp_path, monkeypatch, failure):
    original = subprocess.run
    calls = []
    def run(command, **kwargs):
        if command[0] in ('git', 'uname'):
            return original(command, **kwargs)
        calls.append(command)
        if len(calls) == 1:
            if failure == 'timeout':
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            if failure == 'unavailable':
                raise FileNotFoundError('tool unavailable')
            return subprocess.CompletedProcess(command, 1)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(subprocess, 'run', run)
    report = verify_release(tmp_path / 'gates', selected=('compile', 'javascript'))
    assert report['status'] == 'FAIL' and report['scope'] == 'selected'
    assert report['gates'][0]['status'] == {'exit': 'FAIL', 'timeout': 'TIMEOUT', 'unavailable': 'UNAVAILABLE'}[failure]
    assert report['gates'][1]['status'] == 'PASS' and len(calls) == 2
    assert json.loads((tmp_path / 'gates/release.json').read_text()) == report


def test_unknown_gate_and_existing_output_never_write(tmp_path):
    with pytest.raises(ValueError):
        verify_release(tmp_path / 'unknown', selected=('invented',))
    assert not (tmp_path / 'unknown').exists()
    (tmp_path / 'important').write_text('keep')
    with pytest.raises(FileExistsError):
        verify_release(tmp_path, selected=('compile',))
    assert (tmp_path / 'important').read_text() == 'keep'


def test_release_matrix_retains_all_required_gates_and_hash_seeds(tmp_path):
    gates = {name: (cmd, seed, deadline) for name, cmd, seed, deadline in release_gates(tmp_path)}
    assert set(gates) == {'compile', 'lint', 'javascript', 'diff', 'pytest', 'freeze-normal',
                          'freeze-comprehensive', 'v8', 'v9', 'v10-generate', 'v10-replay', 'browser', 'fresh-process-replay'}
    assert gates['freeze-normal'][1] == gates['v10-generate'][1] == '1'
    assert gates['freeze-comprehensive'][1] == gates['v10-replay'][1] == '77'
    assert gates['fresh-process-replay'][1] == '1'
    assert gates['fresh-process-replay'][0][1] == 'scripts/evaluate_release_replay.py'
    assert '--comprehensive' in gates['freeze-comprehensive'][0]
    assert all(0 < deadline <= 3600 for _, _, deadline in gates.values())


@pytest.mark.parametrize('profile', ['legacy', 'v6', 'v9'])
def test_actual_benchmark_profiles_reconstruct_and_retain_history(tmp_path, profile):
    result = run_benchmark(BenchmarkConfig(days=2, seeds=(11,), hours=(8,),
                           fake_llm=True, assurance_profile=profile), tmp_path / profile)
    observation = result['runs'][0]['assurance']
    assert observation['reconstruction_matches'] and observation['inspection_preserves_input']
    samples = observation['daily_samples']
    assert [row['day'] for row in samples] == [1, 2]
    assert samples[1]['activities'] > samples[0]['activities']
    assert observation['save_count'] >= 2 and observation['save_seconds'] >= 0
    save = json.loads((tmp_path / profile / 'seed-11/save_state.json').read_text())
    assert ('v9_random_state' in save) == (profile == 'v9')
    assert not {'memory', 'recent_dialogues', 'reason'} & observation.keys()
    public = json.loads((tmp_path / profile / 'assurance.json').read_text())
    assert public['runs'][0]['assurance'] == observation
    assert 'metrics' not in public['runs'][0]
    assert not {'agents', 'reputation_beliefs', 'artifacts', 'aggregate'} & public.keys()


@pytest.mark.parametrize('config', [
    BenchmarkConfig(days=401, seeds=(11,), fake_llm=True, assurance_profile='v9'),
    BenchmarkConfig(days=2, seeds=(11,), assurance_profile='v9'),
    BenchmarkConfig(days=2, seeds=(11,), fake_llm=True, assurance_profile='unknown'),
])
def test_profile_validation_rejects_unbounded_or_model_work_before_writes(tmp_path, config):
    output = tmp_path / 'not-created'
    with pytest.raises(ValueError):
        run_benchmark(config, output)
    assert not output.exists()


@pytest.mark.integration
@pytest.mark.parametrize('hash_seed', ['1', '77'])
def test_legacy_fresh_process_continuation_with_explicit_rng_witness(tmp_path, hash_seed):
    """Legacy saves omit RNG by contract; evaluator witnesses supply its stream."""
    from contextlib import redirect_stdout
    from io import StringIO
    import os
    import random
    import sys
    from src.analysis.collective_project_evaluation import engine, authoritative_signature
    from src.analysis.observatory import checkpoint, fingerprint
    config = tmp_path / 'config.json'
    config.write_text(Path('data/town_growth.json').read_text())
    caller = random.getstate()
    try:
        random.seed(23)
        town = engine(tmp_path, 'legacy', config)
        with redirect_stdout(StringIO()):
            town.run(3, [8])
        witness = {'version': 1, 'state': random.getstate()}
        (tmp_path / 'rng.json').write_text(json.dumps(witness))
        saved_bytes = town.state.path.read_bytes()
        assert 'v9_random_state' not in json.loads(saved_bytes)
        random.seed(23)
        town = engine(tmp_path, 'uninterrupted', config)
        with redirect_stdout(StringIO()):
            town.run(8, [8])
        expected = {'authority': authoritative_signature(town),
                    'public': fingerprint(checkpoint(town.state.path))}
        code = '''
import json, random, sys
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
from src.analysis.collective_project_evaluation import engine, authoritative_signature
from src.analysis.observatory import checkpoint, fingerprint
from src.simulation.project_random_state import restore_project_random_state
root = Path(sys.argv[1])
random.seed(987654)
town = engine(root, 'legacy', root / 'config.json', load=True)
restore_project_random_state(json.loads((root / 'rng.json').read_text()))
with redirect_stdout(StringIO()): town.run(5, [8])
print(json.dumps({'authority': authoritative_signature(town), 'public': fingerprint(checkpoint(town.state.path))}))
'''
        result = subprocess.run([sys.executable, '-c', code, str(tmp_path)],
                                env={**os.environ, 'PYTHONHASHSEED': hash_seed},
                                capture_output=True, text=True, timeout=120, check=True)
        assert json.loads(result.stdout) == expected
    finally:
        random.setstate(caller)
