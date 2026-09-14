"""Build compact, speaker-bounded context for one conversation."""

from __future__ import annotations

import re

from src.agents.memory import Memory


ACTION_AND_SYSTEM_TAGS = {
    "conversation",
    "neutral",
    "friendly",
    "tense",
    "enemies",
    "close friends",
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


def _memory_score(
    memory: Memory,
    listener_name: str,
    location_id: str,
    current_day: int,
) -> tuple[int, int, int, int, int]:
    involves_listener = listener_name in memory.participants
    is_personal_arc_event = memory.type == "town_arc_participation"
    matches_location = memory.location == location_id
    age = max(0, current_day - memory.day)
    return (
        1 if involves_listener else 0,
        1 if is_personal_arc_event else 0,
        1 if matches_location else 0,
        memory.importance,
        -age,
    )


def select_conversation_memories(
    speaker,
    listener_name: str,
    location_id: str,
    current_day: int,
    *,
    limit: int = 3,
    max_age_days: int = 14,
) -> list[Memory]:
    """Select known memories without letting public-event entries crowd out history.

    Conversation memories involving the listener come first. One personally
    observed arc event or important same-location memory may fill remaining
    space. Daily-event memories are excluded because today's public event has a
    dedicated context field and old events otherwise tend to dominate by
    importance.
    """

    eligible = [
        memory
        for memory in speaker.memory
        if 0 <= current_day - memory.day <= max_age_days
        and memory.type not in {"daily_event", "town_arc"}
        and (
            listener_name in memory.participants
            or memory.type == "town_arc_participation"
            or (memory.location == location_id and memory.importance >= 3)
        )
    ]
    eligible.sort(
        key=lambda memory: _memory_score(
            memory, listener_name, location_id, current_day
        ),
        reverse=True,
    )

    selected = []
    seen_descriptions = set()
    partner_memories = 0
    for memory in eligible:
        normalized = " ".join(memory.description.lower().split())
        if normalized in seen_descriptions:
            continue
        involves_listener = listener_name in memory.participants
        if involves_listener and partner_memories >= 2:
            continue
        if not involves_listener and len(selected) >= 2:
            continue

        selected.append(memory)
        seen_descriptions.add(normalized)
        if involves_listener:
            partner_memories += 1
        if len(selected) >= limit:
            break

    for memory in selected:
        memory.last_accessed_day = current_day
        memory.strength = min(10, memory.strength + 1)
    return selected


def select_recent_topics(topics: list[str], limit: int = 4) -> list[str]:
    selected = []
    for topic in reversed(topics):
        normalized = topic.strip().lower()
        if (
            not normalized
            or normalized in ACTION_AND_SYSTEM_TAGS
            or normalized in selected
        ):
            continue
        selected.append(normalized)
        if len(selected) >= limit:
            break
    return list(reversed(selected))


def select_recent_utterances(speaker, limit: int = 5) -> list[str]:
    utterances = []
    seen = set()
    for memory in reversed(speaker.memory):
        if (
            memory.type != "conversation"
            or not memory.participants
            or memory.participants[0] != speaker.name
        ):
            continue
        normalized = " ".join(memory.description.lower().split())
        if not normalized or normalized in seen:
            continue
        utterances.append(memory.description.strip())
        seen.add(normalized)
        if len(utterances) >= limit:
            break
    return utterances


def _format_memory(memory: Memory, current_day: int) -> str:
    age = current_day - memory.day
    timing = "earlier today" if age == 0 else f"{age} day{'s' if age != 1 else ''} ago"
    description = memory.description
    if memory.type == "town_arc_participation":
        match = re.search(
            r"affected the town arc '([^']+)' through action '([^']+)'",
            description,
        )
        if match:
            arc_name, action = match.groups()
            participants = " and ".join(memory.participants) or "Residents"
            verbs = {
                "cooperate": "worked together on",
                "offer_help": "helped with",
                "ask_for_help": "asked for help with",
                "share_rumor": "discussed uncertain information about",
                "argue": "disagreed about",
                "apologize": "made amends while discussing",
            }
            description = f"{participants} {verbs.get(action, 'discussed')} {arc_name}."
    return f"{timing} at {memory.location.replace('_', ' ')}: {description}"


def _display_activity(activity: str) -> str:
    text = str(activity or "ordinary errands").strip()
    if text.lower().startswith("work on intent:"):
        text = text.split(":", 1)[1].strip().replace("_", " ")
        replacements = {
            "seek work": "Look for work or business opportunities",
            "investigate": "Investigate recent town activity",
            "socialize": "Catch up with other residents",
            "build friendship": "Get to know other residents",
            "repair relationship": "Try to make amends",
        }
        return replacements.get(text.lower(), text.capitalize())
    return text.replace("_", " ")


def _format_journal(summary: str) -> str:
    text = summary
    substitutions = {
        "Work on intent: seek_work": "looked for work",
        "Work on intent: investigate": "investigated recent town activity",
        "Work on intent: socialize": "caught up with residents",
        "Work on intent: build_friendship": "got to know residents",
        "Work on intent: repair_relationship": "tried to make amends",
    }
    for raw, natural in substitutions.items():
        text = text.replace(raw, natural)
    text = re.sub(r" Intent outcomes:.*$", "", text)
    text = re.sub(r" Intent '[^']+'.*$", "", text)
    return text.strip()


def _focus_options(
    *,
    memories: list[Memory],
    relationship_history: list[str],
    speaker_intent: dict | None,
    listener_name: str,
    location_id: str,
    daily_event: dict | None,
    daily_event_relevant: bool,
    town_arcs: list[dict],
) -> list[str]:
    options = []
    if relationship_history or any(
        listener_name in memory.participants for memory in memories
    ):
        options.append("shared history with the listener")
    if speaker_intent and (
        speaker_intent.get("target_agent") in (None, listener_name)
        and speaker_intent.get("target_location") in (None, location_id)
    ):
        options.append("the speaker's current intent")
    if any(memory.type == "town_arc_participation" for memory in memories):
        options.append("the speaker's prior participation in an ongoing issue")
    elif town_arcs:
        options.append("an active issue at this location")
    if daily_event and daily_event_relevant:
        options.append("today's public event")
    options.append("the current activity or an ordinary location observation")
    return options[:4]


def build_conversation_context(
    speaker,
    listener,
    location_id,
    relationship_label,
    relationship_score,
    current_day: int,
    daily_event=None,
    allowed_actions=None,
    suggested_action=None,
    relationship_history=None,
    speaker_intent=None,
    listener_intent=None,
    town_arcs=None,
):
    del listener_intent  # A listener's private intent is not speaker knowledge.
    relationship_history = relationship_history or []
    town_arcs = town_arcs or []
    memories = select_conversation_memories(
        speaker=speaker,
        listener_name=listener.name,
        location_id=location_id,
        current_day=current_day,
    )

    memory_descriptions = {memory.description for memory in memories}
    relationship_history = [
        item
        for item in relationship_history
        if not any(description in item for description in memory_descriptions)
    ][:2]

    recent_journals = speaker.get_recent_journals(current_day=current_day, limit=1)
    activity_text = _display_activity(speaker.current_activity)
    daily_event_relevant = bool(
        daily_event
        and (
            daily_event.location_id == location_id
            or daily_event.name.lower() in speaker.current_activity.lower()
            or daily_event.id in speaker.current_activity_tags
        )
    )
    event_data = (
        {
            "id": daily_event.id,
            "name": daily_event.name,
            "description": daily_event.description,
            "location_id": daily_event.location_id,
            "tags": daily_event.tags,
        }
        if daily_event and daily_event_relevant
        else None
    )

    context = {
        "speaker": speaker.name,
        "listener": listener.name,
        "speaker_personality": speaker.personality,
        "location": location_id,
        "relationship_label": relationship_label,
        "relationship_score": relationship_score,
        "relationship_history": relationship_history,
        "speaker_intent": speaker_intent,
        "relevant_memories": [
            _format_memory(memory, current_day) for memory in memories
        ],
        "recent_journals": [
            f"Day {journal.day}: {_format_journal(journal.summary)}"
            for journal in recent_journals
        ],
        "memory_summary": speaker.memory_summary,
        "goals": speaker.goals[:3],
        "occupation": speaker.occupation,
        "speaker_activity": speaker.current_activity,
        "speaker_activity_display": activity_text,
        "speaker_activity_reason": speaker.current_activity_reason,
        "speaker_activity_tags": speaker.current_activity_tags,
        "primary_need": speaker.get_primary_need(),
        "recent_topics": select_recent_topics(speaker.recent_topics),
        "recent_utterances": select_recent_utterances(speaker),
        "allowed_actions": allowed_actions or ["chat"],
        "suggested_action": suggested_action or "chat",
        "town_arcs": town_arcs,
        "daily_event": event_data,
        "daily_event_relevant": daily_event_relevant,
    }
    context["focus_options"] = _focus_options(
        memories=memories,
        relationship_history=relationship_history,
        speaker_intent=speaker_intent,
        listener_name=listener.name,
        location_id=location_id,
        daily_event=event_data,
        daily_event_relevant=daily_event_relevant,
        town_arcs=town_arcs,
    )
    context["context_evidence"] = {
        "memories": [
            {
                "day": memory.day,
                "type": memory.type,
                "description": memory.description,
                "participants": memory.participants,
                "location": memory.location,
            }
            for memory in memories
        ],
        "journal_days": [journal.day for journal in recent_journals],
        "relationship_history_count": len(relationship_history),
        "daily_event_relevant": daily_event_relevant,
        "daily_event_id": daily_event.id if daily_event else None,
        "town_arc_ids": [arc.get("id") for arc in town_arcs],
    }
    return context
