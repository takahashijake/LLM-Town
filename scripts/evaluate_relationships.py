#!/usr/bin/env python3
"""Run the controlled Prompt 5 relationship benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.relationship_evaluation import run_relationship_evaluation  # noqa: E402
from src.llm.client import TransformersLLMClient  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--real-llm", action="store_true")
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--max-new-tokens", type=int, default=120)
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    llm = None
    identifier = "deterministic-policy"
    if args.real_llm:
        import torch

        torch.manual_seed(args.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(args.seed)
        identifier = args.model
        llm = TransformersLLMClient(
            model_name=args.model,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
        )
    result = run_relationship_evaluation(
        args.output_dir,
        project_root=Path(__file__).resolve().parents[1],
        llm=llm,
        model_identifier=identifier,
        seed=args.seed,
    )
    print(json.dumps(result["metrics"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
