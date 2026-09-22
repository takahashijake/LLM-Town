"""Build compact, speaker-bounded context for one conversation."""

from __future__ import annotations

import re

from src.agents.memory import Memory
from src.systems.reputation import ReputationSystem
from src.llm.grounding import build_grounding_sources


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

MAX_CONTEXT_TEXT_CHARS = 2_400
MAX_CONTEXT_ITEM_CHARS = 320


def _bounded_text(value: object, limit: int = MAX_CONTEXT_ITEM_CHARS) -> str:
    """Normalize and deterministically cap one prompt-facing text value."""
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _content_tokens(value: object) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z][a-z'-]{2,}", str(value).lower())
        if token not in ACTION_AND_SYSTEM_TAGS
    }


def _is_redundant(value: str, existing: list[str]) -> bool:
    candidate = _content_tokens(value)
    if not candidate:
        return True
    for item in existing:
        known = _content_tokens(item)
        if known and len(candidate & known) / min(len(candidate), len(known)) >= 0.7:
            return True
    return False


def _intent_for_interaction(
    intent: dict | None,
    listener_name: str,
    location_id: str,
) -> dict | None:
    if not intent:
        return None
    if intent.get("target_agent") not in (None, listener_name):
        return None
    if intent.get("target_location") not in (None, location_id):
        return None
    selected = {
        key: (
            None
            if intent[key] is None
            else (
                _bounded_text(intent[key], 240)
                if key in {"description", "target_agent", "target_location"}
                else intent[key]
            )
        )
        for key in (
            "intent_type", "description", "target_agent", "target_location",
            "priority", "progress", "progress_goal", "parent_goal_id", "strategy",
        )
        if key in intent
    }
    if not selected.get("parent_goal_id"):
        selected.pop("parent_goal_id", None)
    if not selected.get("strategy"):
        selected.pop("strategy", None)
    return selected


def _select_goals(
    goals: list,
    *,
    activity: str,
    intent: dict | None,
    location_id: str,
    memories: list[str],
    limit: int = 2,
) -> list[str]:
    """Prefer goals connected to the immediate interaction context."""
    focus_tokens = _content_tokens(
        " ".join(
            [
                activity,
                location_id,
                str((intent or {}).get("description", "")),
                *memories,
            ]
        )
    )
    ranked = []
    for index, goal in enumerate(goals):
        bounded = _bounded_text(goal, 180)
        overlap = len(_content_tokens(bounded) & focus_tokens)
        ranked.append((overlap, -index, bounded))
    relevant = [item for item in sorted(ranked, reverse=True) if item[0] > 0]
    if relevant:
        return [item[2] for item in relevant[:limit]]
    # A single persistent goal is useful when the immediate context is sparse.
    return [ranked[0][2]] if ranked and not intent and not memories else []


def _public_town_arcs(town_arcs: list[dict]) -> list[dict]:
    """Expose public descriptions, never internal arc progress/tension state."""
    public = []
    for arc in town_arcs[:2]:
        public.append(
            {
                key: _bounded_text(arc.get(key), 300)
                for key in ("id", "name", "description", "location_id")
                if arc.get(key) is not None
            }
        )
    return public


def _prompt_context_text_chars(context: dict) -> int:
    event = context.get("daily_event") or {}
    intent = context.get("speaker_intent") or {}
    values = [
        context.get("speaker", ""),
        context.get("listener", ""),
        context.get("speaker_personality", ""),
        context.get("location", ""),
        context.get("occupation", ""),
        context.get("speaker_activity_display", ""),
        context.get("speaker_activity_reason", ""),
        context.get("primary_need", ""),
        intent.get("description", ""),
        (context.get("active_goal") or {}).get("description", ""),
        event.get("name", ""),
        event.get("description", ""),
        *context.get("relationship_history", []),
        *context.get("social_memories", []),
        *context.get("reputation_context", []),
        *context.get("active_commitments", []),
        context.get("reputation_rumor_text", ""),
        *context.get("relevant_memories", []),
        *context.get("recent_journals", []),
        context.get("memory_summary", ""),
        *context.get("goals", []),
        *context.get("recent_topics", []),
        *context.get("recent_utterances", []),
        *(
            turn.get("dialogue", "")
            for turn in context.get("session_transcript", [])
        ),
        context.get("most_recent_utterance", ""),
        *(
            f"{arc.get('name', '')} {arc.get('description', '')}"
            for arc in context.get("town_arcs", [])
        ),
    ]
    return sum(len(str(value)) for value in values)


def _prune_context_to_budget(context: dict) -> None:
    """Drop lower-priority optional material until the hard budget is met."""
    reductions = (
        lambda: context.update(memory_summary=""),
        lambda: context.update(goals=context["goals"][:1]),
        lambda: context.update(town_arcs=[]),
        lambda: context.update(goals=[]),
        lambda: context.update(recent_journals=[]),
        lambda: context.update(daily_event=None, daily_event_relevant=False),
        lambda: context.update(relationship_history=context["relationship_history"][:1]),
        lambda: context.update(social_memories=context["social_memories"][:1]),
        lambda: context.update(reputation_context=context["reputation_context"][:1]),
        lambda: context.update(relevant_memories=context["relevant_memories"][:2]),
        lambda: context.update(recent_utterances=context["recent_utterances"][:1]),
        lambda: context.update(recent_topics=context["recent_topics"][:2]),
        lambda: context.update(session_transcript=context.get("session_transcript", [])[-2:]),
        lambda: context.update(relevant_memories=context["relevant_memories"][:1]),
    )
    for reduce_context in reductions:
        if _prompt_context_text_chars(context) <= MAX_CONTEXT_TEXT_CHARS:
            return
        reduce_context()


def _memory_score(
    memory: Memory,
    listener_name: str,
    location_id: str,
    current_day: int,
) -> tuple[int, int, int, int, int, int]:
    involves_listener = listener_name in memory.participants
    is_personal_arc_event = memory.type == "town_arc_participation"
    matches_location = memory.location == location_id
    age = max(0, current_day - memory.day)
    return (
        1 if involves_listener else 0,
        1 if memory.causal and memory.has_authoritative_provenance else 0,
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

    active_eligible = [
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
    # Archived recall is deliberately narrower than recent recall: only one
    # provenance-backed, important item relevant to this listener may return.
    historical = [
        memory for memory in speaker.memory_archive
        if memory.causal and memory.has_authoritative_provenance
        and memory.importance >= 4
        and listener_name in memory.participants
        and 0 <= current_day - memory.day
    ]
    historical.sort(
        key=lambda memory: _memory_score(
            memory, listener_name, location_id, current_day
        ), reverse=True,
    )
    eligible = active_eligible + historical[:1]
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
        normalized = _bounded_text(topic.strip().lower(), 80)
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


def select_recent_utterances(speaker, limit: int = 3) -> list[str]:
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
        utterances.append(_bounded_text(memory.description, 180))
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
    social_memories: list[str],
    speaker_intent: dict | None,
    listener_name: str,
    location_id: str,
    daily_event: dict | None,
    daily_event_relevant: bool,
    town_arcs: list[dict],
    reputation_context: list[str],
    reputation_rumor: dict | None,
) -> list[str]:
    options = []
    if relationship_history or social_memories or any(
        listener_name in memory.participants for memory in memories
    ):
        options.append("shared history with the listener")
    if reputation_context:
        options.append("the speaker's own belief about the listener's conduct")
    if reputation_rumor:
        options.append("one supported social observation about a third party")
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
    relationship_snapshot=None,
    social_memories=None,
    speaker_intent=None,
    listener_intent=None,
    town_arcs=None,
    reputation_context=None,
    reputation_rumor=None,
    session_transcript=None,
    most_recent_utterance="",
):
    del listener_intent  # A listener's private intent is not speaker knowledge.
    relationship_history = relationship_history or []
    relationship_snapshot = relationship_snapshot or {}
    social_memories = [
        _bounded_text(item, 220) for item in (social_memories or [])[:3]
    ]
    town_arcs = _public_town_arcs(town_arcs or [])
    speaker_intent = _intent_for_interaction(
        speaker_intent,
        listener_name=listener.name,
        location_id=location_id,
    )
    active_goal = speaker.get_goal(
        (speaker_intent or {}).get("parent_goal_id")
    )
    active_goal_summary = (
        {
            "description": _bounded_text(active_goal.description, 180),
            "category": active_goal.category,
            "progress": active_goal.progress,
            "progress_target": active_goal.progress_target,
            "strategy": (speaker_intent or {}).get("strategy") or active_goal.current_strategy,
            "adaptation_count": active_goal.adaptation_count,
        }
        if active_goal else None
    )
    reputation_context = [
        _bounded_text(item, 220) for item in (reputation_context or [])[:2]
    ]
    reputation_rumor_text = _bounded_text(
        ReputationSystem.format_rumor_claim(reputation_rumor), 280
    )
    memories = select_conversation_memories(
        speaker=speaker,
        listener_name=listener.name,
        location_id=location_id,
        current_day=current_day,
    )

    memory_descriptions = {memory.description for memory in memories}
    relationship_history = [
        _bounded_text(item)
        for item in relationship_history
        if not any(description in item for description in memory_descriptions)
    ][:2]

    formatted_memories = [
        _bounded_text(_format_memory(memory, current_day)) for memory in memories
    ]
    recent_journals = speaker.get_recent_journals(current_day=current_day, limit=1)
    formatted_journals = [
        f"Day {journal.day}: {_bounded_text(_format_journal(journal.summary), 300)}"
        for journal in recent_journals
    ]
    formatted_journals = [
        journal
        for journal in formatted_journals
        if not _is_redundant(journal, formatted_memories + relationship_history)
    ]
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
            "name": _bounded_text(daily_event.name, 120),
            "description": _bounded_text(daily_event.description, 300),
            "location_id": daily_event.location_id,
            "tags": daily_event.tags,
        }
        if daily_event and daily_event_relevant
        else None
    )

    context = {
        "speaker": _bounded_text(speaker.name, 80),
        "listener": _bounded_text(listener.name, 80),
        "speaker_personality": _bounded_text(speaker.personality, 180),
        "location": _bounded_text(location_id, 80),
        "relationship_label": relationship_label,
        "relationship_score": relationship_score,
        "relationship_history": relationship_history,
        "relationship_snapshot": relationship_snapshot,
        "social_memories": social_memories,
        "reputation_context": reputation_context,
        "reputation_rumor": reputation_rumor,
        "reputation_rumor_text": reputation_rumor_text,
        "active_commitments": [],
        "speaker_intent": speaker_intent,
        "active_goal": active_goal_summary,
        "relevant_memories": formatted_memories,
        "recent_journals": formatted_journals,
        "memory_summary": (
            _bounded_text(speaker.memory_summary, 400)
            if speaker.memory_summary and not formatted_memories and not formatted_journals
            else ""
        ),
        "goals": _select_goals(
            speaker.goal_descriptions(),
            activity=activity_text,
            intent=speaker_intent,
            location_id=location_id,
            memories=formatted_memories,
        ),
        "occupation": _bounded_text(speaker.occupation, 100),
        "speaker_activity": _bounded_text(speaker.current_activity, 180),
        "speaker_activity_display": _bounded_text(activity_text, 180),
        "speaker_activity_reason": _bounded_text(speaker.current_activity_reason, 220),
        "speaker_activity_tags": speaker.current_activity_tags,
        "primary_need": speaker.get_primary_need(),
        "recent_topics": select_recent_topics(speaker.recent_topics),
        "recent_utterances": select_recent_utterances(speaker),
        "allowed_actions": allowed_actions or ["chat"],
        "suggested_action": suggested_action or "chat",
        # Shared spoken knowledge. This is intentionally separate from the
        # current speaker's private memories and journals.
        "session_transcript": list(session_transcript or [])[-4:],
        "most_recent_utterance": _bounded_text(most_recent_utterance, 320),
        "town_arcs": town_arcs,
        "daily_event": event_data,
        "daily_event_relevant": daily_event_relevant,
    }
    _prune_context_to_budget(context)
    prompt_memories = memories[: len(context["relevant_memories"])]
    context["focus_options"] = _focus_options(
        memories=prompt_memories,
        relationship_history=context["relationship_history"],
        social_memories=context["social_memories"],
        speaker_intent=context["speaker_intent"],
        listener_name=listener.name,
        location_id=location_id,
        daily_event=context["daily_event"],
        daily_event_relevant=context["daily_event_relevant"],
        town_arcs=context["town_arcs"],
        reputation_context=context["reputation_context"],
        reputation_rumor=context["reputation_rumor"],
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
        "relationship_history_count": len(context["relationship_history"]),
        "social_memory_count": len(context["social_memories"]),
        "reputation_belief_count": len(context["reputation_context"]),
        "rumor_evidence_id": (
            context["reputation_rumor"].get("evidence_id")
            if context["reputation_rumor"] else None
        ),
        "daily_event_relevant": context["daily_event_relevant"],
        "daily_event_id": daily_event.id if daily_event else None,
        "town_arc_ids": [arc.get("id") for arc in context["town_arcs"]],
    }
    context["context_evidence"]["prompt_context_text_chars"] = (
        _prompt_context_text_chars(context)
    )
    context["grounding_sources"] = build_grounding_sources(context)
    return context
