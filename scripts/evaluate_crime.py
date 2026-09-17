#!/usr/bin/env python3
"""Run the deterministic crime/evidence acceptance evaluation."""

import argparse
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.crime_evaluation import (  # noqa: E402
    run_crime_evaluation,
    write_crime_evaluation,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs/crime_evaluation.json",
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="llm-town-crime-") as work_dir:
        result = run_crime_evaluation(work_dir, project_root=PROJECT_ROOT)
    write_crime_evaluation(result, args.output)
    counts = result["counts"]
    print("LLM-Town deterministic crime/evidence evaluation")
    print(f"result: {'PASS' if result['passed'] else 'FAIL'}")
    print(
        f"incidents={counts['incidents_created']} "
        f"unauthorized_transfers={counts['unauthorized_transfers']} "
        f"stolen_value={counts['stolen_value']}"
    )
    print(
        f"witnesses={counts['actual_witnesses']} "
        f"direct_evidence={counts['direct_evidence']} "
        f"hearsay={counts['hearsay_records']}"
    )
    print(f"hard invariants={all(result['invariants'].values())}")
    print(f"structured result: {args.output.resolve()}")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
