#!/usr/bin/env python3
"""Run independent model-free release gates; retain safe status separately from local logs."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Gate:
    name: str
    command: tuple[str, ...]
    hash_seed: str = '1'
    requires: tuple[str, ...] = ()
    timeout: int = 3600


def release_gates(root: Path) -> tuple[Gate, ...]:
    """Keep each existing evaluator independently executable and independently reported."""
    python = sys.executable
    return (
        Gate('compile', (python, '-m', 'compileall', '-q', 'src', 'scripts', 'tests')),
        Gate('lint', (python, '-m', 'ruff', 'check', '--select', 'E9,F',
                      'src/analysis/release_replay.py', 'src/simulation/state.py',
                      'scripts/evaluate_release_replay.py', 'scripts/verify_release.py',
                      'tests/analysis/test_release_replay.py', 'tests/simulation/test_atomic_save.py',
                      'tests/analysis/test_collective_project_evaluation.py')),
        Gate('javascript', ('node', '--check', 'src/analysis/observatory_assets/report.js')),
        Gate('diff', ('git', 'diff', '--check')),
        Gate('pytest', (python, '-m', 'pytest', '-q', f'--junitxml={root / "pytest.xml"}')),
        Gate('freeze-normal', (python, 'scripts/evaluate_v6_freeze.py', '--output', str(root / 'freeze-normal.json'))),
        Gate('freeze-comprehensive', (python, 'scripts/evaluate_v6_freeze.py', '--comprehensive',
                                    '--output', str(root / 'freeze-comprehensive.json')), '77'),
        Gate('v8', (python, 'scripts/showcase_v8.py', '--output', str(root / 'v8'))),
        Gate('v9', (python, 'scripts/evaluate_v9_collective_projects.py', '--output', str(root / 'v9')), '77'),
        Gate('v10', (python, 'scripts/showcase_town.py', '--output', str(root / 'v10'))),
        Gate('v10-replay', (python, 'scripts/showcase_town.py', '--verify', str(root / 'v10')), '77', ('v10',)),
        Gate('browser', (python, 'scripts/check_observatory_browser.py', '--report', str(root / 'v10/index.html')),
             requires=('v10',)),
        Gate('replay-matrix', (python, 'scripts/evaluate_release_replay.py', '--output', str(root / 'replay.json'))),
        Gate('stability', (python, 'scripts/evaluate_release_replay.py', '--scenario', 'procedural',
                           '--long-horizon', '--output', str(root / 'stability.json'))),
    )


def run_gates(root: Path, gates: tuple[Gate, ...]) -> dict:
    """Continue independent gates after failures; never publish uncontrolled logs."""
    root.mkdir(parents=True, exist_ok=False)
    results = {}
    for gate in gates:
        if any(results[name]['status'] != 'PASS' for name in gate.requires):
            results[gate.name] = {'status': 'SKIP', 'reason': 'prerequisite_failed'}
        else:
            started = time.perf_counter()
            with (root / f'{gate.name}.log').open('x') as log:
                try:
                    result = subprocess.run(gate.command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                        timeout=gate.timeout, env={**os.environ, 'PYTHONHASHSEED': gate.hash_seed})
                    code = result.returncode
                except subprocess.TimeoutExpired:
                    code = 124
                except OSError:
                    code = 127
            results[gate.name] = {'status': 'PASS' if code == 0 else 'FAIL', 'returncode': code,
                                  'hash_seed': gate.hash_seed, 'seconds': time.perf_counter() - started}
        report = {'schema_version': 1, 'kind': 'release_verification',
                  'status': 'PASS' if all(r['status'] == 'PASS' for r in results.values()) else 'FAIL',
                  'gates': results, 'completed': len(results), 'expected': len(gates)}
        (root / 'release.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        print(f"{gate.name}: {results[gate.name]['status']}", flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new directory; logs are local/private')
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists():
        parser.error('output must be a new directory')
    report = run_gates(root, release_gates(root))
    print(f'Status report: {root / "release.json"}')
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
