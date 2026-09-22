#!/usr/bin/env python3
"""Run deterministic, cached, or opt-in live grounded-dialogue evaluation."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
import hashlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis.grounded_dialogue_evaluation import evaluate_cached_fixture, evaluate_grounded_dialogue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cached", type=Path)
    parser.add_argument("--live-model", choices=["3b", "7b"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.live_model:
        model = {"3b": "Qwen/Qwen2.5-3B-Instruct", "7b": "Qwen/Qwen2.5-7B-Instruct"}[args.live_model]
        if not args.output:
            parser.error("--live-model requires --output")
        command = [sys.executable, str(ROOT / "scripts/evaluate_causal_memory_real.py"),
                   "--model-name", model, "--output", str(args.output)]
        status = subprocess.call(command)
        if status == 0:
            artifact = json.loads(args.output.read_text())
            artifact.update({
                "model_configuration": {"max_new_tokens": 120, "temperature": 0.4, "top_p": 0.9},
                "commit_sha": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "seed": [42, 73], "scenario_version": "grounded-dialogue-live-v1",
                "prompt_context_hash": hashlib.sha256(json.dumps([
                    {"outcome": row["outcome"], "historical_recall": row["historical_recall"],
                     "context_memories": row["context_memories"]}
                    for row in artifact["records"]
                ], sort_keys=True).encode()).hexdigest(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "parser_version": "envelope-v1", "validator_version": "grounding-v1",
            })
            args.output.write_text(json.dumps(artifact, indent=2) + "\n")
        raise SystemExit(status)
    result = evaluate_cached_fixture(json.loads(args.cached.read_text())) if args.cached else evaluate_grounded_dialogue()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result.get("valid", result.get("passed", False)) else 1)


if __name__ == "__main__":
    main()
