#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.commitment_semantics_evaluation import run_commitment_semantics_evaluation, write_commitment_semantics_evaluation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/commitment_semantics_evaluation.json")
    args = parser.parse_args()
    result = run_commitment_semantics_evaluation(ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_commitment_semantics_evaluation(result, args.output)
    print("LLM-Town deterministic commitment-semantics evaluation")
    print(f"result: {result['result']}")
    print(f"examples={result['corpus']['examples']}")
    print(f"structured result: {args.output.resolve()}")
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
