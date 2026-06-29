def is_narration(conversation: str, speaker_name: str, listener_name: str) -> bool:
    text = conversation.strip().lower()

    quoted_name_prefixes = [
        f"{speaker_name.lower()}:",
        f"{listener_name.lower()}:",
    ]

    if any(text.startswith(prefix) for prefix in quoted_name_prefixes):
        return True

    narration_patterns = [
        f"{speaker_name.lower()} noticed",
        f"{listener_name.lower()} noticed",
        f"{speaker_name.lower()} notices",
        f"{listener_name.lower()} notices",
        f"{speaker_name.lower()} nodded",
        f"{listener_name.lower()} nodded",
        f"{speaker_name.lower()} nods",
        f"{listener_name.lower()} nods",
        f"{speaker_name.lower()} looked",
        f"{listener_name.lower()} looked",
        f"{speaker_name.lower()} looks",
        f"{listener_name.lower()} looks",
        f"{speaker_name.lower()} smiled",
        f"{listener_name.lower()} smiled",
        f"{speaker_name.lower()} smiles",
        f"{listener_name.lower()} smiles",
        f"{speaker_name.lower()} asks",
        f"{listener_name.lower()} asks",
        f"{speaker_name.lower()} says",
        f"{listener_name.lower()} says",
    ]

    return any(pattern in text for pattern in narration_patterns)


def clean_dialogue_text(conversation: str) -> str:
    conversation = conversation.strip()

    replacements = {
        ".I ": ". I ",
        ".You ": ". You ",
        ".We ": ". We ",
        ".They ": ". They ",
        ".This ": ". This ",
        ".That ": ". That ",
        "check records": "checking records",
        "review reports": "reviewing reports",
        "help neighbors": "helping neighbors",
        "serve customers": "serving customers",
        "organize supplies": "organizing supplies",
    }

    for old_text, new_text in replacements.items():
        conversation = conversation.replace(old_text, new_text)

    return conversation


def has_rumor_marker(conversation: str) -> bool:
    text = conversation.lower()

    rumor_markers = [
        "rumor",
        "rumors",
        "gossip",
        "someone said",
        "people are saying",
        "concerns about",
        "not sure if it is true",
        "not sure it's true",
        "unverified",
        "suspicious",
        "strange about",
        "might be hiding",
        "might be unreliable",
    ]

    return any(marker in text for marker in rumor_markers)


def get_previous_event_keywords(
    daily_event_history: list[dict],
    current_day: int,
) -> list[str]:
    keywords = []

    for event in daily_event_history:
        if event["day"] >= current_day:
            continue

        name = event["name"].lower()
        keywords.append(name)

        for word in name.split():
            if len(word) >= 5:
                keywords.append(word)

    return list(dict.fromkeys(keywords))


def fix_stale_event_reference(
    conversation: str,
    current_day: int,
    current_daily_event,
    daily_event_history: list[dict],
) -> str:
    if not current_daily_event:
        return conversation

    current_event_name = current_daily_event.name.lower()
    current_event_words = {
        word
        for word in current_event_name.split()
        if len(word) >= 5
    }

    previous_keywords = get_previous_event_keywords(
        daily_event_history=daily_event_history,
        current_day=current_day,
    )

    fixed_conversation = conversation
    fixed_lower = fixed_conversation.lower()

    mentions_today = (
        "today" in fixed_lower
        or "tonight" in fixed_lower
        or "this morning" in fixed_lower
        or "this afternoon" in fixed_lower
        or "this evening" in fixed_lower
    )

    if not mentions_today:
        return fixed_conversation

    for keyword in previous_keywords:
        if keyword in current_event_words:
            continue

        if keyword in fixed_lower and keyword not in current_event_name:
            fixed_conversation = fixed_conversation.replace(" today", " recently")
            fixed_conversation = fixed_conversation.replace(" Today", " Recently")
            fixed_conversation = fixed_conversation.replace(" tonight", " recently")
            fixed_conversation = fixed_conversation.replace(" Tonight", " Recently")
            fixed_conversation = fixed_conversation.replace(" this morning", " recently")
            fixed_conversation = fixed_conversation.replace(" this afternoon", " recently")
            fixed_conversation = fixed_conversation.replace(" this evening", " recently")
            return fixed_conversation

    return fixed_conversation