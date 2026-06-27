import json
from collections import Counter


INTENT_COMPATIBLE_ACTIONS = {
    "build_friendship": {
        "chat",
        "compliment",
        "offer_help",
        "cooperate",
    },
    "repair_relationship": {
        "chat",
        "apologize",
        "offer_help",
    },
    "investigate": {
        "chat",
        "ask_for_help",
        "share_rumor",
    },
    "socialize": {
        "chat",
        "compliment",
        "offer_help",
        "cooperate",
    },
    "seek_work": {
        "chat",
        "ask_for_help",
        "cooperate",
        "offer_help",
    },
}


def load_jsonl(path):
    rows = []

    with open(path) as f:
        for line in f:
            line = line.strip()

            if line:
                rows.append(json.loads(line))

    return rows


def safe_rate(numerator, denominator):
    if denominator == 0:
        return 0.0

    return numerator / denominator


def build_agent_locations_by_tick(events):
    locations_by_tick = {}

    for row in events:
        if row.get("type") != "activity":
            continue

        key = (
            row.get("day"),
            row.get("hour"),
            row.get("agent"),
        )

        locations_by_tick[key] = row.get("location", "")

    return locations_by_tick


def main():
    conversations = load_jsonl("logs/conversations/conversations.jsonl")
    events = load_jsonl("logs/events/events.jsonl")
    locations_by_tick = build_agent_locations_by_tick(events)

    total_with_intent = 0

    target_agent_opportunities = 0
    target_agent_matches = 0
    target_agent_unavailable = 0

    target_location_opportunities = 0
    target_location_matches = 0

    action_match_count = 0

    intent_counts = Counter()
    action_by_intent = Counter()
    location_by_intent = Counter()
    target_agent_by_intent = Counter()
    target_location_by_intent = Counter()

    missed_target_agents = Counter()
    missed_target_locations = Counter()
    unavailable_target_agents = Counter()

    for row in conversations:
        intent_type = row.get("speaker_intent_type", "")
        target_agent = row.get("speaker_intent_target_agent", "")
        target_location = row.get("speaker_intent_target_location", "")

        listener = row.get("listener", "")
        location = row.get("location", "")
        action = row.get("action", "")

        if not intent_type:
            continue

        total_with_intent += 1

        intent_counts[intent_type] += 1
        action_by_intent[(intent_type, action)] += 1
        location_by_intent[(intent_type, location)] += 1

        expected_actions = INTENT_COMPATIBLE_ACTIONS.get(intent_type, set())

        if action in expected_actions:
            action_match_count += 1

        if target_agent:
            target_agent_location = locations_by_tick.get(
                (
                    row.get("day"),
                    row.get("hour"),
                    target_agent,
                ),
                "",
            )

            target_available = target_agent_location == location

            if target_available:
                target_agent_opportunities += 1
                target_agent_by_intent[(intent_type, target_agent)] += 1

                if listener == target_agent:
                    target_agent_matches += 1
                else:
                    missed_target_agents[(intent_type, target_agent, listener)] += 1
            else:
                target_agent_unavailable += 1
                unavailable_target_agents[
                    (
                        intent_type,
                        target_agent,
                        target_agent_location or "unknown",
                        location,
                    )
                ] += 1

        if target_location:
            target_location_opportunities += 1
            target_location_by_intent[(intent_type, target_location)] += 1

            if location == target_location:
                target_location_matches += 1
            else:
                missed_target_locations[(intent_type, target_location, location)] += 1

    print("Intent follow-through report")
    print(f"  Conversations with speaker intent: {total_with_intent}")

    print(f"  Target-agent opportunities: {target_agent_opportunities}")
    print(f"  Target-agent conversations: {target_agent_matches}")
    print(f"  Target-agent unavailable/skipped: {target_agent_unavailable}")
    print(
        "  Target-agent rate: "
        f"{safe_rate(target_agent_matches, target_agent_opportunities):.1%}"
    )

    print(f"  Target-location opportunities: {target_location_opportunities}")
    print(f"  Target-location conversations: {target_location_matches}")
    print(
        "  Target-location rate: "
        f"{safe_rate(target_location_matches, target_location_opportunities):.1%}"
    )

    print(f"  Intent-compatible actions: {action_match_count}")
    print(
        "  Intent-action compatibility: "
        f"{safe_rate(action_match_count, total_with_intent):.1%}"
    )

    print("\nIntents:")
    for intent_type, count in intent_counts.most_common():
        print(f"  {intent_type}: {count}")

    print("\nActions by intent:")
    for (intent_type, action), count in action_by_intent.most_common():
        print(f"  {intent_type} -> {action}: {count}")

    print("\nLocations by intent:")
    for (intent_type, location), count in location_by_intent.most_common():
        print(f"  {intent_type} @ {location}: {count}")

    if target_agent_by_intent:
        print("\nTarget agents by intent:")
        for (intent_type, target_agent), count in target_agent_by_intent.most_common():
            print(f"  {intent_type} -> {target_agent}: {count}")

    if target_location_by_intent:
        print("\nTarget locations by intent:")
        for (intent_type, target_location), count in target_location_by_intent.most_common():
            print(f"  {intent_type} -> {target_location}: {count}")

    if missed_target_agents:
        print("\nMost common missed target-agent conversations:")
        for (intent_type, target_agent, actual_listener), count in missed_target_agents.most_common(5):
            print(
                f"  {intent_type}: wanted {target_agent}, "
                f"talked to {actual_listener}: {count}"
            )

    if unavailable_target_agents:
        print("\nMost common unavailable target-agent cases:")
        for (
            intent_type,
            target_agent,
            target_agent_location,
            speaker_location,
        ), count in unavailable_target_agents.most_common(5):
            print(
                f"  {intent_type}: wanted {target_agent}, "
                f"target at {target_agent_location}, "
                f"speaker conversation at {speaker_location}: {count}"
            )

    if missed_target_locations:
        print("\nMost common missed target-location conversations:")
        for (intent_type, target_location, actual_location), count in missed_target_locations.most_common(5):
            print(
                f"  {intent_type}: wanted {target_location}, "
                f"conversation at {actual_location}: {count}"
            )


if __name__ == "__main__":
    main()