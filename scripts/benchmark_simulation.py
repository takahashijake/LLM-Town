#!/usr/bin/env python3
"""Run reproducible, isolated LLM-Town simulation benchmarks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.benchmark import (  # noqa: E402
    BenchmarkConfig,
    default_output_dir,
    print_summary,
    run_benchmark,
    write_comparison,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run isolated simulation seeds and write structured metrics."
    )
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--hours", type=int, nargs="+", default=[8, 12, 18, 22])
    parser.add_argument(
        "--fake-llm",
        action="store_true",
        help="Use the deterministic FakeLLMClient.",
    )
    parser.add_argument(
        "--model-name",
        default="Qwen/Qwen2.5-3B-Instruct",
        help="Hugging Face model used when --fake-llm is omitted.",
    )
    parser.add_argument("--max-new-tokens", type=int, default=150)
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--agents-path", default="data/agents.json")
    parser.add_argument("--locations-path", default="data/locations.json")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="New suite directory. Existing paths are rejected.",
    )
    parser.add_argument(
        "--compare-to",
        type=Path,
        help="Existing benchmark.json (or its directory) to compare against.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = BenchmarkConfig(
        days=args.days,
        seeds=tuple(args.seeds),
        hours=tuple(args.hours),
        fake_llm=args.fake_llm,
        model_name=args.model_name,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        agents_path=args.agents_path,
        locations_path=args.locations_path,
    )
    output_dir = args.output_dir or default_output_dir(PROJECT_ROOT)

    try:
        document = run_benchmark(
            config=config,
            output_dir=output_dir,
            project_root=PROJECT_ROOT,
        )
        print_summary(document, output_dir)
        if args.compare_to:
            write_comparison(document, args.compare_to, output_dir)
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        print(f"benchmark error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
