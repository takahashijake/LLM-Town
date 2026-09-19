#!/usr/bin/env python3
"""Run the deterministic justice acceptance evaluation."""

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.justice_evaluation import run_justice_evaluation, write_justice_evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/justice_evaluation.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="llm-town-justice-") as work:
        result = run_justice_evaluation(work, project_root=ROOT)
    write_justice_evaluation(result, args.output)
    print("LLM-Town deterministic justice evaluation")
    print(f"result: {'PASS' if result['passed'] else 'FAIL'}")
    print(f"rule: {result['rule_version']}")
    print(f"hard invariants={all(result['invariants'].values())}")
    print(f"structured result: {args.output.resolve()}")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
