#!/usr/bin/env python3
"""Run the deterministic whole-V4 freeze-candidate evaluation."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.v4_freeze_evaluation import evaluate_v4_freeze


def main() -> int:
    result = evaluate_v4_freeze()
    print("LLM-Town deterministic V4 freeze evaluation")
    print(
        f"scenarios={result['scenarios_passed']}/{result['scenario_count']} "
        f"invariants={result['invariants_passed']}/{result['invariant_count']}"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
