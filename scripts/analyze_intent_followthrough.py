#!/usr/bin/env python3
"""Inspect intent follow-through using the benchmark metric definitions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.quality_metrics import (  # noqa: E402
    analyze_intent_followthrough,
    load_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze agent intent follow-through.")
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="Run directory containing logs/ (including a benchmark seed directory).",
    )
    parser.add_argument("--conversations-path", type=Path)
    parser.add_argument("--events-path", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    conversations_path = args.conversations_path or (
        args.run_dir / "logs" / "conversations" / "conversations.jsonl"
        if args.run_dir
        else Path("logs/conversations/conversations.jsonl")
    )
    events_path = args.events_path or (
        args.run_dir / "logs" / "events" / "events.jsonl"
        if args.run_dir
        else Path("logs/events/events.jsonl")
    )
    return conversations_path, events_path


def _print_counts(title: str, counts: dict[str, int]) -> None:
    print(f"\n{title}:")
    for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {name}: {count}")


def _print_transitions(title: str, transitions: dict[str, dict[str, int]]) -> None:
    print(f"\n{title}:")
    rows = [
        (count, source, final)
        for source, final_counts in transitions.items()
        for final, count in final_counts.items()
    ]
    for count, source, final in sorted(rows, key=lambda item: (-item[0], item[1:])):
        print(f"  {source} -> {final}: {count}")


def print_report(metrics: dict) -> None:
    print("Intent follow-through report")
    print(
        "  Conversations with speaker intent: "
        f"{metrics['conversations_with_intent']}"
    )
    print(f"  Target-agent opportunities: {metrics['target_agent_opportunities']}")
    print(f"  Target-agent conversations: {metrics['target_agent_matches']}")
    print(
        "  Target-agent unavailable/skipped: "
        f"{metrics['target_agent_unavailable']}"
    )
    print(f"  Target-agent rate: {metrics['target_agent_rate']:.1%}")
    print(
        "  Target-location opportunities: "
        f"{metrics['target_location_opportunities']}"
    )
    print(f"  Target-location conversations: {metrics['target_location_matches']}")
    print(f"  Target-location rate: {metrics['target_location_rate']:.1%}")
    print(f"  Intent-compatible actions: {metrics['compatible_actions']}")
    print(
        "  Intent-action compatibility: "
        f"{metrics['action_compatibility_rate']:.1%}"
    )

    _print_counts("Intents", metrics["intent_counts"])
    for intent_type, counts in metrics["actions_by_intent"].items():
        _print_counts(f"Actions for {intent_type}", counts)

    pipeline = metrics["action_pipeline"]
    _print_counts("Suggested actions", pipeline["suggested_counts"])
    _print_counts("Parsed actions", pipeline["parsed_counts"])
    _print_counts("Inferred actions", pipeline["inferred_counts"])
    _print_counts("Final actions", pipeline["final_counts"])
    _print_transitions("Suggested -> final", pipeline["suggested_to_final"])
    _print_transitions("Parsed -> final", pipeline["parsed_to_final"])
    _print_transitions("Inferred -> final", pipeline["inferred_to_final"])
    _print_counts("Final action reasons", pipeline["final_reason_counts"])


def main() -> None:
    args = parse_args()
    conversations_path, events_path = resolve_paths(args)
    metrics = analyze_intent_followthrough(
        load_jsonl(conversations_path), load_jsonl(events_path)
    )
    if args.json:
        print(json.dumps(metrics, indent=2, sort_keys=True))
    else:
        print_report(metrics)


if __name__ == "__main__":
    main()
