#!/usr/bin/env python3
"""Run the deterministic social-commitment acceptance evaluation."""

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.commitment_evaluation import run_commitment_evaluation, write_commitment_evaluation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/commitment_evaluation.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="llm-town-commitments-") as work:
        result = run_commitment_evaluation(work, ROOT)
    write_commitment_evaluation(result, args.output)
    print("LLM-Town deterministic social-commitment evaluation")
    print(f"result: {'PASS' if result['passed'] else 'FAIL'}")
    print(f"hard invariants={sum(result['hard_invariants'].values())}/{len(result['hard_invariants'])}")
    print(f"structured result: {args.output.resolve()}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
