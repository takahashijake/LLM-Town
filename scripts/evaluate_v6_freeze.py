#!/usr/bin/env python3
"""Run the model-free V6 release assurance gate."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.v6_freeze_evaluation import evaluate_v6_freeze


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comprehensive', action='store_true',
                        help='also continue every checkpoint independently')
    parser.add_argument('--output', type=Path, help='write structured diagnostics')
    args = parser.parse_args()
    result = evaluate_v6_freeze(comprehensive=args.comprehensive)
    print(f"V6 FREEZE: {'PASS' if result['passed'] else 'FAIL'}")
    for label, passed, count in (
        ('scenarios', 'scenarios_passed', 'scenario_count'),
        ('invariants', 'invariants_passed', 'invariant_count'),
        ('replay checkpoints', 'replay_checkpoints_passed', 'replay_checkpoint_count'),
        ('adversarial mutations rejected', 'mutations_rejected', 'mutation_count'),
    ):
        print(f'{label}: {result[passed]}/{result[count]}')
    encoded = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
