#!/usr/bin/env python3
"""Run the deterministic V6 Phase 4 acceptance gate."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.procedural_commerce_evaluation import (
    evaluate_procedural_commerce,
)


if __name__ == "__main__":
    result = evaluate_procedural_commerce()
    print("LLM-Town deterministic V6 Phase 4 procedural-commerce evaluation")
    if "scenario_count" in result:
        print(f"scenarios={result['scenarios_passed']}/{result['scenario_count']} "
              f"invariants={result['invariants_passed']}/{result['invariant_count']}")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)
