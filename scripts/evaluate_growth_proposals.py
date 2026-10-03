#!/usr/bin/env python3
"""Run the deterministic V6 Phase 1 proposal acceptance gate."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.growth_proposal_evaluation import evaluate_growth_proposals


if __name__ == "__main__":
    result = evaluate_growth_proposals()
    print("LLM-Town deterministic V6 Phase 1 growth-proposal evaluation")
    print(
        f"scenarios={result['scenarios_passed']}/{result['scenario_count']} "
        f"invariants={result['invariants_passed']}/{result['invariant_count']}"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)
