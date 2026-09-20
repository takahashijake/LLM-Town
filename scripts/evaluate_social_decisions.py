#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.social_decision_evaluation import run_social_decision_evaluation


def main() -> int:
    result = run_social_decision_evaluation()
    print("LLM-Town post-V2 deterministic social-decision evaluation")
    print(f"result: {result['result']}")
    print(f"hard invariants={result['hard_invariants_passed']}/{result['hard_invariants_total']}")
    print("structured result: outputs/social_decision_evaluation.json")
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
