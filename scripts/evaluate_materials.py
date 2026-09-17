#!/usr/bin/env python3
"""Run the deterministic V2 material ownership acceptance evaluation."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.material_evaluation import (  # noqa: E402
    run_material_evaluation,
    write_material_evaluation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs/material_evaluation.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="llm-town-materials-") as work_dir:
        document = run_material_evaluation(work_dir, project_root=PROJECT_ROOT)
    write_material_evaluation(document, args.output)
    material = document["material_diagnostics"]
    economy = document["economy_diagnostics"]
    print("LLM-Town deterministic material evaluation")
    print(f"result: {'PASS' if document['passed'] else 'FAIL'}")
    print(
        f"exchanges={material['exchange_count']} "
        f"consumptions={material['consumption_count']} "
        f"idempotency_rejections={material['idempotency_rejections']}"
    )
    print(
        f"currency conserved={economy['currency_conserved']}; "
        f"material conserved={material['material_conserved_with_consumption']}"
    )
    print(
        "exchange/ledger reconciled="
        f"{material['exchanges_reconcile_with_ledger']}"
    )
    print(f"structured result: {args.output.resolve()}")
    return 0 if document["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

