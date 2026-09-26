#!/usr/bin/env python3
"""Run the deterministic V4 strategy-execution evaluation."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.goal_strategy_execution_evaluation import (
    evaluate_goal_strategy_execution,
)


def main() -> int:
    result = evaluate_goal_strategy_execution()
    print("LLM-Town deterministic V4 strategy-execution evaluation")
    print(
        f"scenarios: {result['scenarios_passed']}/{result['scenario_count']} PASS "
        f"invariants: {result['invariants_passed']}/{result['invariant_count']} PASS"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
