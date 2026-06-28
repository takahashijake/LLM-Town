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

def print_story_summary(path: Path = Path("logs/town_arc_changes.jsonl")) -> None:
    print("\nStory summary:")

    if not path.exists():
        print("  No town arc change log found.")
        return

    records = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        print("  No conversation-driven story changes recorded.")
        return

    records_by_arc = {}

    for record in records:
        records_by_arc.setdefault(record["arc_name"], []).append(record)

    for arc_name, arc_records in records_by_arc.items():
        progress_changes = sum(
            1
            for record in arc_records
            if record["new_progress"] > record["old_progress"]
        )

        tension_increases = sum(
            1
            for record in arc_records
            if record["new_tension"] > record["old_tension"]
        )

        tension_decreases = sum(
            1
            for record in arc_records
            if record["new_tension"] < record["old_tension"]
        )

        actions = Counter(record["action"] for record in arc_records)
        top_action = actions.most_common(1)[0][0]

        print(
            f"  {arc_name}: {len(arc_records)} conversation-driven changes; "
            f"progress advanced {progress_changes} times, "
            f"tension rose {tension_increases} times, "
            f"and tension eased {tension_decreases} times. "
            f"Most common driver: {top_action}."
        )

        
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
        
def print_run_metadata(
    conversations_path: Path = CONVERSATIONS_PATH,
    state_path: Path = Path("data/save_state.json"),
    arc_changes_path: Path = Path("logs/town_arc_changes.jsonl"),
) -> None:
    print("\nRun metadata:")

    print(f"  Conversation log: {conversations_path}")
    print(f"  Conversation log exists: {conversations_path.exists()}")

    print(f"  Saved state: {state_path}")
    print(f"  Saved state exists: {state_path.exists()}")

    print(f"  Town arc change log: {arc_changes_path}")
    print(f"  Town arc change log exists: {arc_changes_path.exists()}")

    if not state_path.exists():
        print("  Current day: unknown")
        print("  Current hour: unknown")
        print("  Agents: unknown")
        return

    with state_path.open("r", encoding="utf-8") as file:
        state = json.load(file)

    agents = state.get("agents", [])

    print(f"  Current day: {state.get('current_day', 'unknown')}")
    print(f"  Current hour: {state.get('current_hour', 'unknown')}")
    print(f"  Agents: {len(agents)}")
    
def print_town_arc_change_summary(path: Path = Path("logs/town_arc_changes.jsonl")) -> None:
    print("\nTown arc causal changes:")

    if not path.exists():
        print("  No town arc change log found.")
        return

    records = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if line:
                records.append(json.loads(line))

    if not records:
        print("  Total conversation-driven arc changes: 0")
        return

    arc_counts = Counter(record["arc_name"] for record in records)
    action_counts = Counter(record["action"] for record in records)

    progress_increases = sum(
        1
        for record in records
        if record["new_progress"] > record["old_progress"]
    )

    tension_increases = sum(
        1
        for record in records
        if record["new_tension"] > record["old_tension"]
    )

    tension_decreases = sum(
        1
        for record in records
        if record["new_tension"] < record["old_tension"]
    )

    print(f"  Total conversation-driven arc changes: {len(records)}")
    print(f"  Progress increases: {progress_increases}")
    print(f"  Tension increases: {tension_increases}")
    print(f"  Tension decreases: {tension_decreases}")

    print("  Changes by arc:")
    for arc_name, count in arc_counts.most_common():
        print(f"    {arc_name}: {count}")

    print("  Changes by action:")
    for action, count in action_counts.most_common():
        print(f"    {action}: {count}")
        
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

def print_memory_summary(path: Path = Path("data/save_state.json")) -> None:
    print("\nMemory summary:")

    if not path.exists():
        print("  No saved state found.")
        return

    with path.open("r", encoding="utf-8") as file:
        state = json.load(file)

    agents = state.get("agents", [])

    if not agents:
        print("  No agents found in saved state.")
        return

    active_memory_counts = []
    archived_memory_counts = []
    memory_type_counts = Counter()

    for agent in agents:
        active_memories = agent.get("memory", [])
        archived_memories = agent.get("memory_archive", [])

        active_memory_counts.append(len(active_memories))
        archived_memory_counts.append(len(archived_memories))

        for memory in active_memories + archived_memories:
            memory_type_counts[memory.get("type", "unknown")] += 1

    avg_active = sum(active_memory_counts) / len(active_memory_counts)
    avg_archived = sum(archived_memory_counts) / len(archived_memory_counts)
    max_active = max(active_memory_counts)
    max_archived = max(archived_memory_counts)

    print(f"  Agents: {len(agents)}")
    print(f"  Average active memories per agent: {avg_active:.1f}")
    print(f"  Average archived memories per agent: {avg_archived:.1f}")
    print(f"  Max active memories for one agent: {max_active}")
    print(f"  Max archived memories for one agent: {max_archived}")

    print("  Memory types:")
    for memory_type, count in memory_type_counts.most_common():
        print(f"    {memory_type}: {count}")

    print("  Memory quality flags:")

    if max_active <= 200:
        print("    PASS max active memories <= 200")
    else:
        print("    WARN max active memories exceeds 200")

    if avg_active <= 150:
        print("    PASS average active memories <= 150")
    else:
        print("    WARN average active memories is high")

    if memory_type_counts.get("town_arc_participation", 0) > 0:
        print("    PASS town arc participation memories exist")
    else:
        print("    WARN no town arc participation memories found")

    if memory_type_counts.get("conversation", 0) > 0:
        print("    PASS conversation memories exist")
    else:
        print("    WARN no conversation memories found")

    if memory_type_counts.get("daily_event", 0) > 0:
        print("    PASS daily event memories exist")
    else:
        print("    WARN no daily event memories found")
        
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

    if 0.0045 <= compliment_rate <= 0.15:
        print("  PASS compliment rate between 5% and 15%")
    else:
        print("  WARN compliment rate outside 5%-15%")

    if 0.20 <= event_rate <= 0.40:
        print("  PASS daily event mention rate between 20% and 40%")
    else:
        print("  WARN daily event mention rate outside 20%-40%")

def print_town_arc_change_summary(path: Path = Path("logs/town_arc_changes.jsonl")) -> None:
    print("\nTown arc causal changes:")

    if not path.exists():
        print("  No town arc change log found.")
        return

    records = []

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        print("  Total conversation-driven arc changes: 0")
        return

    arc_counts = Counter(record["arc_name"] for record in records)
    action_counts = Counter(record["action"] for record in records)

    progress_increases = sum(
        1 for record in records
        if record["new_progress"] > record["old_progress"]
    )

    tension_increases = sum(
        1 for record in records
        if record["new_tension"] > record["old_tension"]
    )

    tension_decreases = sum(
        1 for record in records
        if record["new_tension"] < record["old_tension"]
    )

    print(f"  Total conversation-driven arc changes: {len(records)}")
    print(f"  Progress increases: {progress_increases}")
    print(f"  Tension increases: {tension_increases}")
    print(f"  Tension decreases: {tension_decreases}")

    print("  Changes by arc:")
    for arc_name, count in arc_counts.most_common():
        print(f"    {arc_name}: {count}")

    print("  Changes by action:")
    for action, count in action_counts.most_common():
        print(f"    {action}: {count}")

def main() -> None:
    records = load_conversations(CONVERSATIONS_PATH)

    print("=== LLM-Town Quality Report ===")
    print_run_metadata()
    print(f"\nTotal conversations: {len(records)}")

    print_action_distribution(records)
    print_repetition_summary(records)
    print_daily_event_usage(records)
    print_arc_usage(records)
    print_town_arc_change_summary()
    print_story_summary()
    print_memory_summary()
    print_quality_flags(records)


if __name__ == "__main__":
    main()
