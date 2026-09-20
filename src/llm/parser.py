import json
import re

ALLOWED_ACTIONS = {
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


def clean_conversation_output(text: str) -> str:
    text = text.strip()
    return text


def extract_json_object(text: str) -> str | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None

    return match.group(0)


def infer_conversation_tags(text: str) -> list[str]:
    text_lower = text.lower()
    tags = ["conversation"]

    if "project" in text_lower or "business" in text_lower or "stall" in text_lower:
        tags.append("business")

    if "rumor" in text_lower or "trust" in text_lower or "suspicious" in text_lower:
        tags.append("rumor")

    if "price" in text_lower or "market" in text_lower or "buy" in text_lower:
        tags.append("market")

    if "book" in text_lower or "read" in text_lower or "research" in text_lower:
        tags.append("learning")

    if "avoiding" in text_lower or "done talking" in text_lower or "issue" in text_lower:
        tags.append("conflict")

    return tags


def normalize_action(action: str) -> str:
    action = str(action).strip().lower().replace("-", "_").replace(" ", "_")

    aliases = {
        "praise": "compliment",
        "thank": "compliment",
        "thanks": "compliment",
        "help": "offer_help",
        "request_help": "ask_for_help",
        "ask_help": "ask_for_help",
        "gossip": "share_rumor",
        "rumor": "share_rumor",
        "collaborate": "cooperate",
        "work_together": "cooperate",
        "disagree": "argue",
        "confront": "argue",
        "leave": "storm_off",
        "walk_away": "storm_off",
    }

    return aliases.get(action, action)


def clean_tags(tags) -> list[str]:
    if not isinstance(tags, list):
        return []

    cleaned = []

    for tag in tags:
        tag = str(tag).strip().lower().replace(" ", "_")
        if tag and tag not in cleaned:
            cleaned.append(tag)

    return cleaned


def parse_llm_conversation_output(
    text: str,
    allowed_actions: list[str] | None = None,
) -> dict:
    json_text = extract_json_object(text)

    if json_text is None:
        return {
            "dialogue": "",
            "action": "chat",
            "tags": [],
            "reason": "",
            "raw_action": "",
            "action_source": "fallback_no_json",
            "grounding_refs": [],
        }

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return {
            "dialogue": "",
            "action": "chat",
            "tags": [],
            "reason": "",
            "raw_action": "",
            "action_source": "fallback_bad_json",
            "grounding_refs": [],
        }

    dialogue = clean_conversation_output(str(data.get("dialogue", "")))
    raw_action = str(data.get("action", "chat")).strip()
    action = normalize_action(raw_action)
    grounding_refs = data.get("grounding_refs", [])
    if not isinstance(grounding_refs, list):
        grounding_refs = []
    grounding_refs = list(dict.fromkeys(str(ref).strip() for ref in grounding_refs if str(ref).strip()))

    allowed = set(allowed_actions or ALLOWED_ACTIONS)

    if "chat" not in allowed:
        allowed.add("chat")

    if action not in ALLOWED_ACTIONS:
        return {
            "dialogue": dialogue,
            "action": "chat",
            "tags": clean_tags(data.get("tags", [])),
            "reason": str(data.get("reason", "")),
            "raw_action": raw_action,
            "action_source": "fallback_unknown_action",
            "grounding_refs": grounding_refs,
        }

    if action not in allowed:
        return {
            "dialogue": dialogue,
            "action": "chat",
            "tags": clean_tags(data.get("tags", [])),
            "reason": str(data.get("reason", "")),
            "raw_action": raw_action,
            "action_source": "fallback_disallowed_action",
            "grounding_refs": grounding_refs,
        }

    return {
        "dialogue": dialogue,
        "action": action,
        "tags": clean_tags(data.get("tags", [])),
        "reason": str(data.get("reason", "")),
        "raw_action": raw_action,
        "action_source": "llm",
        "grounding_refs": grounding_refs,
    }
