#!/usr/bin/env python3
"""Evaluate fresh-process release replay; --long-horizon observes 390-day growth."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.release_replay import SCENARIOS, evaluate_release_replay, worker  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--long-horizon', action='store_true')
    parser.add_argument('--scenario', choices=SCENARIOS)
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--days', type=int, default=30, help=argparse.SUPPRESS)
    parser.add_argument('--resume', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('output must be a new file')
    if args.worker:
        if not args.scenario or not 1 <= args.days <= 390:
            parser.error('worker requires a scenario and bounded days')
        result = worker(args.worker, args.scenario, args.days, args.resume)
    else:
        scenarios = (args.scenario,) if args.scenario else tuple(SCENARIOS)
        result = evaluate_release_replay(long_horizon=args.long_horizon, scenarios=scenarios)
    encoded = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as handle:
            handle.write(encoded)
    print(encoded)
    return int(result.get('status') == 'FAIL')


if __name__ == '__main__':
    raise SystemExit(main())
