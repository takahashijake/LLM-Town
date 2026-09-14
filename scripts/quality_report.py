#!/usr/bin/env python3
"""Render the shared structured quality metrics for one simulation run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.quality_metrics import analyze_run_files  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report structured quality metrics for a simulation run."
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        help=(
            "Run directory containing save_state.json and logs/. "
            "This accepts a benchmark seed directory."
        ),
    )
    parser.add_argument("--conversations-path", type=Path)
    parser.add_argument("--events-path", type=Path)
    parser.add_argument("--state-path", type=Path)
    parser.add_argument("--arc-changes-path", type=Path)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the machine-readable metrics object.",
    )
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> dict[str, Path]:
    run_dir = args.run_dir
    return {
        "conversations_path": args.conversations_path
        or (
            run_dir / "logs" / "conversations" / "conversations.jsonl"
            if run_dir
            else Path("logs/conversations/conversations.jsonl")
        ),
        "events_path": args.events_path
        or (
            run_dir / "logs" / "events" / "events.jsonl"
            if run_dir
            else Path("logs/events/events.jsonl")
        ),
        "state_path": args.state_path
        or (run_dir / "save_state.json" if run_dir else Path("data/save_state.json")),
        "arc_changes_path": args.arc_changes_path
        or (
            run_dir / "logs" / "town_arc_changes.jsonl"
            if run_dir
            else Path("logs/town_arc_changes.jsonl")
        ),
    }


def print_metrics_report(metrics: dict, paths: dict[str, Path]) -> None:
    conversations = metrics["conversations"]
    print("=== LLM-Town Quality Report ===")
    print("\nRun metadata:")
    print(f"  Conversation log: {paths['conversations_path']}")
    print(f"  Saved state: {paths['state_path']}")
    print(f"  Total conversations: {conversations['total']}")

    print("\nAction distribution:")
    for action, count in sorted(
        conversations["action_counts"].items(),
        key=lambda item: (-item[1], item[0]),
    ):
        print(
            f"  {action}: {count} "
            f"({conversations['action_rates'][action]:.1%})"
        )

    print("\nRepetition summary:")
    print(f"  Repeated dialogue rate: {conversations['repetition_rate']:.1%}")
    if conversations["most_repeated_dialogues"]:
        print("  Most repeated dialogue lines:")
        for item in conversations["most_repeated_dialogues"]:
            print(f"    {item['count']}x: {item['dialogue']}")

    print("\nDaily event usage:")
    print(f"  Event-related conversations: {conversations['daily_event_related']}")
    print(f"  Daily event mention rate: {conversations['daily_event_rate']:.1%}")

    print("\nTown arc usage:")
    print(f"  Arc-related conversations: {conversations['town_arc_related']}")
    print(f"  Arc-related conversation rate: {conversations['town_arc_rate']:.1%}")
    arcs = metrics["town_arcs"]
    print(f"  Total arcs: {arcs['total']}")
    print(f"  Resolved arcs: {arcs['resolved']}")
    print(f"  Conversation-driven arc changes: {arcs['causal_changes']}")
    if arcs["change_arc_counts"]:
        print("  Changes by arc:")
        for name, count in arcs["change_arc_counts"].items():
            print(f"    {name}: {count}")
    if arcs["change_action_counts"]:
        print("  Changes by action:")
        for action, count in arcs["change_action_counts"].items():
            print(f"    {action}: {count}")

    intent = metrics["intent_followthrough"]
    print("\nIntent follow-through:")
    print(f"  Conversations with speaker intent: {intent['conversations_with_intent']}")
    print(f"  Target-agent rate: {intent['target_agent_rate']:.1%}")
    print(f"  Target-location rate: {intent['target_location_rate']:.1%}")
    print(f"  Intent-action compatibility: {intent['action_compatibility_rate']:.1%}")

    memory = metrics["memory"]
    print("\nMemory summary:")
    print(f"  Agents: {memory['agent_count']}")
    print(
        "  Average active memories per agent: "
        f"{memory['average_active_per_agent']:.1f}"
    )
    print(
        "  Average archived memories per agent: "
        f"{memory['average_archived_per_agent']:.1f}"
    )
    print(f"  Max active memories for one agent: {memory['max_active_per_agent']}")
    print(f"  Max archived memories for one agent: {memory['max_archived_per_agent']}")
    print("  Memory types:")
    for memory_type, count in memory["type_counts"].items():
        print(f"    {memory_type}: {count}")

    quality = metrics["quality"]
    print("\nQuality flags:")
    for name, check in quality["checks"].items():
        label = check["status"].upper()
        print(f"  {label} {name}: {check['expectation']} (value={check['value']})")
    print(
        f"  Passed {quality['passed']}/{quality['applicable']} applicable checks "
        f"({quality['pass_rate']:.1%})"
    )


def main() -> None:
    args = parse_args()
    paths = resolve_paths(args)
    metrics = analyze_run_files(**paths)

    if args.json:
        print(json.dumps(metrics, indent=2, sort_keys=True))
    else:
        print_metrics_report(metrics, paths)


if __name__ == "__main__":
    main()
