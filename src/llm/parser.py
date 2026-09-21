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

SOCIAL_RESPONSE_TYPES = {
    "accept_request", "decline_request", "counteroffer", "acknowledge",
    "unrelated", "uncertain", "none",
}
SOCIAL_RESPONSE_TARGETS = {"help", "meet", "transfer", "none"}
COMMITMENT_RELATIONS = {
    "planning_to_fulfill", "fulfilling", "references_fulfillment",
    "acknowledges_failure", "attempts_repair", "unrelated",
    "contradicts_state", "none",
}


def _bounded_social_response(value) -> dict:
    """Parse bounded semantic evidence; invalid/free-form values become none."""
    if not isinstance(value, dict):
        return {"type": "none", "target": "none", "confidence": "none", "evidence": []}
    kind = str(value.get("type", "none")).strip().lower()
    target = str(value.get("target", "none")).strip().lower()
    confidence = str(value.get("confidence", "none")).strip().lower()
    evidence = value.get("evidence", [])
    if kind not in SOCIAL_RESPONSE_TYPES:
        kind = "none"
    if target not in SOCIAL_RESPONSE_TARGETS:
        target = "none"
    if confidence not in {"high", "medium", "low", "none"}:
        confidence = "none"
    if not isinstance(evidence, list):
        evidence = []
    return {
        "type": kind, "target": target, "confidence": confidence,
        "evidence": [str(item)[:80] for item in evidence[:3] if str(item).strip()],
    }


def _bounded_commitment_relation(value) -> dict:
    if not isinstance(value, dict):
        return {"commitment_id": "", "relation": "none", "confidence": "none"}
    relation = str(value.get("relation", "none")).strip().lower()
    confidence = str(value.get("confidence", "none")).strip().lower()
    if relation not in COMMITMENT_RELATIONS:
        relation = "none"
    if confidence not in {"high", "medium", "low", "none"}:
        confidence = "none"
    commitment_id = str(value.get("commitment_id", "")).strip()
    if not re.fullmatch(r"commitment-\d{8}", commitment_id):
        commitment_id = ""
    return {"commitment_id": commitment_id, "relation": relation, "confidence": confidence}


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

    empty_social = _bounded_social_response(None)
    empty_relation = _bounded_commitment_relation(None)
    if json_text is None:
        return {
            "dialogue": "",
            "action": "chat",
            "tags": [],
            "reason": "",
            "raw_action": "",
            "action_source": "fallback_no_json",
            "grounding_refs": [],
            "social_response": empty_social,
            "commitment_relation": empty_relation,
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
            "social_response": empty_social,
            "commitment_relation": empty_relation,
        }

    dialogue = clean_conversation_output(str(data.get("dialogue", "")))
    raw_action = str(data.get("action", "chat")).strip()
    action = normalize_action(raw_action)
    grounding_refs = data.get("grounding_refs", [])
    if not isinstance(grounding_refs, list):
        grounding_refs = []
    grounding_refs = list(dict.fromkeys(str(ref).strip() for ref in grounding_refs if str(ref).strip()))
    social_response = _bounded_social_response(data.get("social_response"))
    commitment_relation = _bounded_commitment_relation(data.get("commitment_relation"))

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
            "social_response": social_response,
            "commitment_relation": commitment_relation,
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
            "social_response": social_response,
            "commitment_relation": commitment_relation,
        }

    return {
        "dialogue": dialogue,
        "action": action,
        "tags": clean_tags(data.get("tags", [])),
        "reason": str(data.get("reason", "")),
        "raw_action": raw_action,
        "action_source": "llm",
        "grounding_refs": grounding_refs,
        "social_response": social_response,
        "commitment_relation": commitment_relation,
    }
