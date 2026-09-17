#!/usr/bin/env python3
"""Run the deterministic V2 economy acceptance evaluation."""

from __future__ import annotations

import argparse
import tempfile
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.economy_evaluation import (  # noqa: E402
    run_economy_evaluation,
    write_economy_evaluation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs/economy_evaluation.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="llm-town-economy-") as work_dir:
        document = run_economy_evaluation(work_dir, project_root=PROJECT_ROOT)
    write_economy_evaluation(document, args.output)
    diagnostics = document["diagnostics"]
    print("LLM-Town deterministic economy evaluation")
    print(f"result: {'PASS' if document['passed'] else 'FAIL'}")
    print(
        f"wages: {diagnostics['wage_payment_count']} payments / "
        f"{diagnostics['wages_paid']} credits"
    )
    print(
        f"currency: {diagnostics['total_currency']} credits; "
        f"conserved={diagnostics['currency_conserved']}"
    )
    print(f"ledger reconstructs balances={diagnostics['ledger_reconstructs_balances']}")
    print(f"structured result: {args.output.resolve()}")
    return 0 if document["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

