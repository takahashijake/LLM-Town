#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.long_horizon_planning_evaluation import evaluate_long_horizon_planning


if __name__ == "__main__":
    result = evaluate_long_horizon_planning()
    print("LLM-Town deterministic long-horizon planning evaluation")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)
