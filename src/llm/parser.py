import json 

ALLOWED_ACTIONS = {
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