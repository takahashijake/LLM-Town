#!/usr/bin/env python3
"""Run deterministic Phase-3 commitment accountability scenarios."""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.commitment_accountability_evaluation import evaluate_commitment_accountability


if __name__ == "__main__":
    result = evaluate_commitment_accountability()
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)
