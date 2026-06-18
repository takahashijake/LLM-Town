import json
from collections import Counter


POSITIVE_INTENT_ACTIONS = {
    "build_friendship": {
        "compliment",
        "offer_help",
        "cooperate",
        "chat",
    },
    "repair_relationship": {
        "apologize",
        "offer_help",
        "chat",
    },
    "investigate": {
        "ask_for_help",
        "share_rumor",
        "chat",
    },
    "socialize": {
        "chat",
        "compliment",
    },
    "seek_work": {
        "ask_for_help",
        "cooperate",
        "chat",
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


def main():
    conversations = load_jsonl("logs/conversations/conversations.jsonl")

    total_with_intent = 0
    target_match_count = 0
    action_match_count = 0
    intent_counts = Counter()
    action_by_intent = Counter()

    for row in conversations:
        intent_type = row.get("speaker_intent_type", "")
        target_agent = row.get("speaker_intent_target_agent", "")
        listener = row.get("listener", "")
        action = row.get("action", "")

        if not intent_type:
            continue

        total_with_intent += 1
        intent_counts[intent_type] += 1
        action_by_intent[(intent_type, action)] += 1

        if target_agent and target_agent == listener:
            target_match_count += 1

        expected_actions = POSITIVE_INTENT_ACTIONS.get(intent_type, set())

        if action in expected_actions:
            action_match_count += 1

    print("Intent follow-through report")
    print(f"  Conversations with speaker intent: {total_with_intent}")
    print(f"  Target-agent conversations: {target_match_count}")
    print(f"  Intent-compatible actions: {action_match_count}")

    if total_with_intent:
        print(f"  Target-agent rate: {target_match_count / total_with_intent:.1%}")
        print(f"  Intent-action compatibility: {action_match_count / total_with_intent:.1%}")

    print("\nIntents:")
    for intent_type, count in intent_counts.most_common():
        print(f"  {intent_type}: {count}")

    print("\nActions by intent:")
    for (intent_type, action), count in action_by_intent.most_common():
        print(f"  {intent_type} -> {action}: {count}")


if __name__ == "__main__":
    main()