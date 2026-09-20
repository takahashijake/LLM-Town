#!/usr/bin/env python3
"""Run deterministic commitment-driven execution evaluation."""

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.commitment_execution_evaluation import (
    run_commitment_execution_evaluation, write_commitment_execution_evaluation,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=ROOT / "outputs/commitment_execution_evaluation.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="llm-town-commitment-execution-") as work:
        result = run_commitment_execution_evaluation(work, ROOT)
    write_commitment_execution_evaluation(result, args.output)
    print("LLM-Town deterministic commitment-execution evaluation")
    print(f"result: {'PASS' if result['passed'] else 'FAIL'}")
    print(f"hard invariants={sum(result['hard_invariants'].values())}/{len(result['hard_invariants'])}")
    print(f"structured result: {args.output.resolve()}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
