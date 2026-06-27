import json
from collections import Counter
from pathlib import Path


CONVERSATIONS_PATH = Path("logs/conversations/conversations.jsonl")

ACTION_TAGS = {
    "chat",
    "compliment",
    "apologize",
    "offer_help",
    "ask_for_help",
    "argue",
    "insult",
    "storm_off",
    "confess_feelings",
    "share_rumor",
    "cooperate",
}

def print_arc_usage(records: list[dict]) -> None:
    arc_relevant_actions = {
        "cooperate",
        "offer_help",
        "ask_for_help",
        "share_rumor",
        "argue",
        "apologize",
    }

    arc_keywords = {
        "town_arc",
        "market",
        "business",
        "wealth",
        "community",
        "volunteer",
        "social",
        "knowledge",
        "rules",
        "learning",
    }

    arc_related = 0
    arc_action_counts = Counter()

    for record in records:
        tags = set(record.get("tags", []))
        action = record.get("action", "unknown")

        is_arc_related = bool(tags & arc_keywords)

        if is_arc_related:
            arc_related += 1

            if action in arc_relevant_actions:
                arc_action_counts[action] += 1

    rate = arc_related / len(records) if records else 0

    print("\nTown arc usage:")
    print(f"  Arc-related conversations: {arc_related}")
    print(f"  Arc-related conversation rate: {rate:.1%}")

    if arc_action_counts:
        print("  Arc-relevant actions:")
        for action, count in arc_action_counts.most_common():
            print(f"    {action}: {count}")
    else:
        print("  Arc-relevant actions: none")
        

def load_conversations(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"Could not find {path}. Run the simulation first."
        )

    records = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            records.append(json.loads(line))

    return records


def print_action_distribution(records: list[dict]) -> None:
    action_counts = Counter(
        record.get("action", "unknown")
        for record in records
    )

    total = sum(action_counts.values())

    print("\nAction distribution:")

    for action, count in action_counts.most_common():
        percentage = count / total if total else 0
        print(f"  {action}: {count} ({percentage:.1%})")


def print_repetition_summary(records: list[dict]) -> None:
    dialogue_counts = Counter(
        record.get("conversation", "").strip()
        for record in records
        if record.get("conversation", "").strip()
    )

    repeated = {
        dialogue: count
        for dialogue, count in dialogue_counts.items()
        if count > 1
    }

    repeated_total = sum(count - 1 for count in repeated.values())
    total = len(dialogue_counts)

    repeated_rate = repeated_total / len(records) if records else 0

    print("\nRepetition summary:")
    print(f"  Repeated dialogue rate: {repeated_rate:.1%}")

    if repeated:
        print("  Most repeated dialogue lines:")
        for dialogue, count in Counter(repeated).most_common(5):
            print(f"    {count}x: {dialogue}")


def print_daily_event_usage(records: list[dict]) -> None:
    event_related = 0

    for record in records:
        tags = record.get("tags", [])

        if "event" in tags:
            event_related += 1

    rate = event_related / len(records) if records else 0

    print("\nDaily event usage:")
    print(f"  Event-related conversations: {event_related}")
    print(f"  Daily event mention rate: {rate:.1%}")


def print_quality_flags(records: list[dict]) -> None:
    action_counts = Counter(
        record.get("action", "unknown")
        for record in records
    )

    total = len(records)

    if total == 0:
        print("\nQuality flags:")
        print("  No conversations found.")
        return

    chat_rate = action_counts["chat"] / total
    compliment_rate = action_counts["compliment"] / total

    dialogue_counts = Counter(
        record.get("conversation", "").strip()
        for record in records
        if record.get("conversation", "").strip()
    )

    repeated_total = sum(
        count - 1
        for count in dialogue_counts.values()
        if count > 1
    )

    repeated_rate = repeated_total / total

    event_related = sum(
        1
        for record in records
        if "event" in record.get("tags", [])
    )

    event_rate = event_related / total

    print("\nQuality flags:")

    if repeated_rate <= 0.05:
        print("  PASS repetition <= 5%")
    else:
        print("  WARN repetition > 5%")

    if 0.60 <= chat_rate <= 0.80:
        print("  PASS chat rate between 60% and 80%")
    else:
        print("  WARN chat rate outside 60%-80%")

    if 0.05 <= compliment_rate <= 0.15:
        print("  PASS compliment rate between 5% and 15%")
    else:
        print("  WARN compliment rate outside 5%-15%")

    if 0.20 <= event_rate <= 0.40:
        print("  PASS daily event mention rate between 20% and 40%")
    else:
        print("  WARN daily event mention rate outside 20%-40%")


def main() -> None:
    records = load_conversations(CONVERSATIONS_PATH)

    print("=== LLM-Town Quality Report ===")
    print(f"\nTotal conversations: {len(records)}")

    print_action_distribution(records)
    print_repetition_summary(records)
    print_daily_event_usage(records)
    print_arc_usage(records)
    print_quality_flags(records)


if __name__ == "__main__":
    main()
