#!/usr/bin/env python3
"""Run deterministic V4 Phase 6 goal-delegation checks."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.goal_delegation_evaluation import evaluate_goal_delegation


def main() -> int:
    result = evaluate_goal_delegation()
    print("LLM-Town deterministic V4 goal-delegation evaluation")
    print(
        f"scenarios: {result['scenarios_passed']}/{result['scenario_count']} "
        f"{'PASS' if result['scenarios_passed'] == result['scenario_count'] else 'FAIL'} "
        f"invariants: {result['invariants_passed']}/{result['invariant_count']} "
        f"{'PASS' if result['invariants_passed'] == result['invariant_count'] else 'FAIL'}"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
