def clean_conversation_output(text: str) -> str:
    text = text.strip()

    if not text:
        return "They have a brief conversation."

    return text