#!/usr/bin/env python3
"""Run the whole-V2 deterministic acceptance evaluation."""

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.v2_evaluation import run_v2_evaluation, write_v2_evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/v2_evaluation.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="llm-town-v2-") as work:
        result = run_v2_evaluation(work, project_root=ROOT)
    write_v2_evaluation(result, args.output)
    print("LLM-Town whole-V2 deterministic evaluation")
    print(f"result: {'PASS' if result['passed'] else 'FAIL'}")
    print(f"hard invariants={sum(result['hard_invariants'].values())}/{len(result['hard_invariants'])}")
    print(f"long horizon={result['long_horizon']['days']} days")
    print(f"structured result: {args.output.resolve()}")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
