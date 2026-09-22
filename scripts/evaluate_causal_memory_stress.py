#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.causal_memory_stress import analyze_stress_suite


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("states", nargs="+", type=Path)
    result = analyze_stress_suite(parser.parse_args().states)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)
