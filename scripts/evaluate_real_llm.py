#!/usr/bin/env python3
"""Run one isolated real-model simulation and produce auditable artifacts."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.benchmark import BenchmarkConfig  # noqa: E402
from src.analysis.real_llm_evaluation import run_real_llm_evaluation  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a controlled real-LLM evaluation with review artifacts."
    )
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--hours", type=int, nargs="+", default=[8, 12, 18, 22])
    parser.add_argument("--model-name", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--max-new-tokens", type=int, default=150)
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--max-conversation-turns", type=int, default=4)
    parser.add_argument("--agents-path", default="data/agents.json")
    parser.add_argument("--locations-path", default="data/locations.json")
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def default_output_dir() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return PROJECT_ROOT / "outputs" / "real_llm_evaluations" / f"evaluation-{timestamp}"


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir or default_output_dir()
    config = BenchmarkConfig(
        days=args.days,
        seeds=(args.seed,),
        hours=tuple(args.hours),
        fake_llm=False,
        model_name=args.model_name,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        agents_path=args.agents_path,
        locations_path=args.locations_path,
        max_conversation_turns=args.max_conversation_turns,
    )
    try:
        document = run_real_llm_evaluation(
            config, output_dir, project_root=PROJECT_ROOT
        )
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        print(f"evaluation error: {error}", file=sys.stderr)
        return 2

    dialogue = document["dialogue_evaluation"]
    health = dialogue["response_health"]
    print("LLM-Town real-LLM evaluation")
    print(f"Model: {document['model']['identifier']}")
    print(f"Conversations: {dialogue['conversation_count']}")
    print(
        "Exact / near repetition: "
        f"{dialogue['dialogue_repetition']['exact_repetition_rate']:.1%} / "
        f"{dialogue['dialogue_repetition']['near_repetition_rate']:.1%}"
    )
    print(f"Action parsing success: {health['action_parsing_success_rate']:.1%}")
    print(f"Intent/action compatibility: {dialogue['intent_action_compatibility']:.1%}")
    print(f"Metadata: {output_dir.resolve() / 'metadata.json'}")
    print(f"Metrics: {output_dir.resolve() / 'metrics.json'}")
    print(f"Transcript: {output_dir.resolve() / 'transcript.txt'}")
    print(f"Human review: {output_dir.resolve() / 'review.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
