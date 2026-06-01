import json 

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
}

def clean_conversation_output(text: str) -> str:
    text = text.strip()

    if not text:
        return "They have a brief conversation."

    return text

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

def parse_llm_conversation_output(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {
            "dialogue": clean_conversation_output(text),
            "action": "chat",
        }

    dialogue = clean_conversation_output(data.get("dialogue", ""))
    action = data.get("action", "chat")

    if action not in ALLOWED_ACTIONS:
        action = "chat"

    return {
        "dialogue": dialogue,
        "action": action,
    }