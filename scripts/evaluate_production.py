#!/usr/bin/env python3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.production_evaluation import run_production_evaluation  # noqa: E402


if __name__ == "__main__":
    result = run_production_evaluation()
    print("LLM-Town deterministic production/provenance evaluation")
    print(f"result: {'PASS' if result['passed'] else 'FAIL'}")
    print(f"production={result['production_id']} output_lot={result['output_lot_id']}")
    print("structured result: outputs/production_evaluation.json")
    raise SystemExit(0 if result["passed"] else 1)
