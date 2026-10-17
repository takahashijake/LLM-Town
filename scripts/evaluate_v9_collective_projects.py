#!/usr/bin/env python3
"""Model-free V9 evaluator and showcase; generated worlds stay outside Git."""
import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.collective_project_evaluation import evaluate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='dedicated directory for reports and generated saves')
    args = parser.parse_args()
    if args.output:
        result = evaluate(args.output)
    else:
        with TemporaryDirectory(prefix='llm-town-v9-') as directory:
            result = evaluate(Path(directory))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
