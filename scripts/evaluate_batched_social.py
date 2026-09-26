#!/usr/bin/env python3
"""Run deterministic batched-social acceptance evaluation."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.batched_social_evaluation import evaluate_batched_social


def main() -> int:
    result = evaluate_batched_social()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
