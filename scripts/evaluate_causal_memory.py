#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.causal_memory_evaluation import evaluate_causal_memory


if __name__ == "__main__":
    result = evaluate_causal_memory()
    print("LLM-Town deterministic causal-memory evaluation")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)
