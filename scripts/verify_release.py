#!/usr/bin/env python3
"""Run existing independent model-free gates; collect privacy-safe exit evidence."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def release_gates(output: Path) -> list[tuple[str, list[str], str | None, int]]:
    """Fixed repository commands and bounded deadlines; no input supplies code."""
    python = sys.executable
    return [
        ('compile', [python, '-m', 'compileall', '-q', 'src', 'scripts', 'tests'], None, 120),
        ('lint', [python, '-m', 'ruff', 'check', '--select', 'E9,F',
                  'src/simulation/state.py', 'src/analysis/benchmark.py',
                  'src/analysis/benchmark_assurance.py', 'scripts/verify_release.py',
                  'scripts/benchmark_simulation.py', 'tests/simulation/test_state_atomicity.py',
                  'tests/analysis/test_release_assurance.py', 'src/analysis/release_replay.py',
                  'scripts/evaluate_release_replay.py', 'tests/analysis/test_release_replay.py'], None, 120),
        ('javascript', ['node', '--check', 'src/analysis/observatory_assets/report.js'], None, 120),
        ('diff', ['git', 'diff', '--check'], None, 120),
        ('pytest', [python, '-m', 'pytest', '-q', f'--junitxml={output / "pytest.xml"}'], None, 3600),
        ('freeze-normal', [python, 'scripts/evaluate_v6_freeze.py', '--output', str(output / 'freeze-normal.json')], '1', 1800),
        ('freeze-comprehensive', [python, 'scripts/evaluate_v6_freeze.py', '--comprehensive', '--output', str(output / 'freeze-comprehensive.json')], '77', 3600),
        ('v8', [python, 'scripts/showcase_v8.py', '--output', str(output / 'v8')], '1', 600),
        ('v9', [python, 'scripts/evaluate_v9_collective_projects.py', '--output', str(output / 'v9')], '77', 600),
        ('v10-generate', [python, 'scripts/showcase_town.py', '--output', str(output / 'v10')], '1', 600),
        ('v10-replay', [python, 'scripts/showcase_town.py', '--verify', str(output / 'v10')], '77', 600),
        ('fresh-process-replay', [python, 'scripts/evaluate_release_replay.py', '--output', str(output / 'replay.json')], '1', 1800),
        ('browser', [python, 'scripts/check_observatory_browser.py', '--report', str(output / 'v10/index.html')], None, 180),
    ]


def verify_release(output: Path, *, selected: tuple[str, ...] = ()) -> dict:
    """Continue independent gates after failures and return a durable exit summary."""
    output = output.resolve()
    gates = release_gates(output)
    unknown = set(selected) - {name for name, *_ in gates}
    if unknown:
        raise ValueError(f'unknown release gates: {sorted(unknown)}')
    output.mkdir(parents=True, exist_ok=False)
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    dirty = bool(subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout)
    report = {'schema_version': 1, 'kind': 'release-assurance', 'revision': revision,
              'dirty': dirty, 'python': platform.python_version(),
              'platform': platform.platform(), 'scope': 'selected' if selected else 'full',
              'status': 'RUNNING', 'gates': []}
    summary = output / 'release.json'
    for name, command, seed, timeout in gates:
        if selected and name not in selected:
            continue
        started = time.perf_counter()
        env = dict(os.environ)
        if seed is not None:
            env['PYTHONHASHSEED'] = seed
        # Local logs may contain private test diagnostics. CI must upload only
        # release.json and explicitly allowlisted evaluator reports.
        with (output / f'{name}.log').open('w') as log:
            try:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=timeout, check=False)
                status = 'PASS' if result.returncode == 0 else 'FAIL'
                code = result.returncode
            except subprocess.TimeoutExpired:
                status, code = 'TIMEOUT', None
            except OSError:
                status, code = 'UNAVAILABLE', None
        report['gates'].append({'name': name, 'status': status, 'exit_code': code,
                                'hash_seed': env.get('PYTHONHASHSEED'),
                                'timeout_seconds': timeout,
                                'elapsed_seconds': round(time.perf_counter() - started, 3),
                                'command': command})
        summary.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
        print(f'{name}: {status}', flush=True)
    report['status'] = 'PASS' if all(g['status'] == 'PASS' for g in report['gates']) else 'FAIL'
    summary.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New directory; never reused.')
    parser.add_argument('--gate', action='append', default=[], help='Optional gate subset, explicitly recorded.')
    args = parser.parse_args()
    try:
        report = verify_release(args.output, selected=tuple(args.gate))
    except (ValueError, FileExistsError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
