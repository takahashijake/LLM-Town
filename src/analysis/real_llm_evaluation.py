"""Auditable measurements and review samples for controlled real-LLM runs."""

from __future__ import annotations

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from src.analysis.quality_metrics import load_jsonl, safe_rate


TOKEN_RE = re.compile(r"[a-z][a-z'-]{2,}")
STOPWORDS = {
    "about", "action", "active", "affected", "after", "again", "also", "been",
    "before", "being", "changed", "conversation", "could", "current", "doing",
    "earlier", "enough", "expired", "from", "goal", "have", "important", "intent",
    "into", "involved", "just", "more", "none", "other", "outcomes", "people",
    "progress", "reached", "recent", "relationship", "score", "speaker", "spent",
    "status", "succeeded", "tension", "that", "their", "there", "these", "they",
    "this", "through", "today", "town", "used", "want", "with", "work", "would",
    "your",
}
GENERIC_PATTERNS = (
    "a lot happening",
    "lot going on",
    "town feels busy",
    "nice to see you",
    "things have been busy",
    "everything going on",
    "place feels",
    "my work as a",
    "my work as an",
    "i have been focused on",
)


def _tokens(value: Any) -> set[str]:
    if isinstance(value, dict):
        value = " ".join(str(item) for item in value.values())
    elif isinstance(value, list):
        value = " ".join(str(item) for item in value)
    return {
        token for token in TOKEN_RE.findall(str(value).lower())
        if token not in STOPWORDS
    }


def _context_values(record: dict[str, Any]) -> dict[str, list[Any]]:
    context = record.get("context", {})
    event = context.get("daily_event")
    intent = context.get("speaker_intent") or {}
    return {
        "relationship_history": context.get("relationship_history", []),
        "memory": context.get("memories", []),
        "journal": context.get("journals", []),
        "goal_or_intent": [
            *context.get("goals", []),
            intent.get("description", "") if isinstance(intent, dict) else intent,
        ],
        "occupation": [context.get("occupation") or ""],
        "daily_event": [
            f"{event.get('name', '')} {event.get('description', '')}"
        ] if event and context.get("daily_event_relevant") else [],
        "town_arc": [
            f"{arc.get('name', '')} {arc.get('description', '')}"
            for arc in context.get("town_arcs", [])
        ],
    }


def _lexical_context_use(records: list[dict[str, Any]]) -> dict[str, Any]:
    indicators = {}
    for category in (
        "relationship_history", "memory", "journal", "goal_or_intent",
        "occupation", "daily_event", "town_arc",
    ):
        opportunities = 0
        matches = 0
        for record in records:
            values = _context_values(record)[category]
            evidence_tokens = _tokens(values)
            if not evidence_tokens:
                continue
            opportunities += 1
            if _tokens(record.get("conversation", "")) & evidence_tokens:
                matches += 1
        indicators[category] = {
            "opportunities": opportunities,
            "lexical_matches": matches,
            "lexical_match_rate": safe_rate(matches, opportunities),
        }
    return indicators


def _repetition(records: list[dict[str, Any]]) -> tuple[dict[str, Any], set[int]]:
    normalized = [" ".join(row.get("conversation", "").lower().split()) for row in records]
    counts = Counter(text for text in normalized if text)
    exact_instances = sum(count - 1 for count in counts.values() if count > 1)
    flagged: set[int] = set()
    near_pairs = []
    for index, text in enumerate(normalized):
        if not text:
            continue
        if counts[text] > 1:
            flagged.add(index)
        for prior_index in range(index):
            prior = normalized[prior_index]
            if min(len(text), len(prior)) < 20 or text == prior:
                continue
            similarity = SequenceMatcher(None, prior, text).ratio()
            if similarity >= 0.86:
                flagged.add(index)
                near_pairs.append(
                    {
                        "first_index": prior_index,
                        "second_index": index,
                        "similarity": round(similarity, 4),
                    }
                )
                break
    return {
        "exact_repeated_instances": exact_instances,
        "exact_repetition_rate": safe_rate(exact_instances, len(records)),
        "near_repeated_instances": len(near_pairs),
        "near_repetition_rate": safe_rate(len(near_pairs), len(records)),
        "near_repeat_pairs": near_pairs[:20],
    }, flagged


def analyze_real_llm_records(
    records: list[dict[str, Any]],
    simulation_metrics: dict[str, Any],
) -> tuple[dict[str, Any], set[int]]:
    repetition, repetition_flags = _repetition(records)
    action_sources = Counter(row.get("action_source", "unknown") for row in records)
    dialogue_sources = Counter(row.get("dialogue_source", "unknown") for row in records)
    generation_errors = sum(bool(row.get("generation_error")) for row in records)
    malformed = sum(
        row.get("action_source") in {"fallback_no_json", "fallback_bad_json"}
        for row in records
    )
    generic = sum(
        any(pattern in row.get("conversation", "").lower() for pattern in GENERIC_PATTERNS)
        for row in records
    )
    parsing_successes = action_sources["llm"]
    fallbacks = sum(
        row.get("dialogue_source", "llm") != "llm" for row in records
    )

    return {
        "conversation_count": len(records),
        "dialogue_repetition": repetition,
        "context_use_indicators": _lexical_context_use(records),
        "response_health": {
            "action_source_counts": dict(sorted(action_sources.items())),
            "dialogue_source_counts": dict(sorted(dialogue_sources.items())),
            "action_parsing_successes": parsing_successes,
            "action_parsing_success_rate": safe_rate(parsing_successes, len(records)),
            "malformed_responses": malformed,
            "generation_exceptions": generation_errors,
            "dialogue_fallbacks": fallbacks,
            "dialogue_fallback_rate": safe_rate(fallbacks, len(records)),
        },
        "generic_phrase_flags": generic,
        "generic_phrase_rate": safe_rate(generic, len(records)),
        "intent_action_compatibility": simulation_metrics.get(
            "intent_followthrough", {}
        ).get("action_compatibility_rate", 0.0),
        "measurement_note": (
            "Context-use rates are transparent lexical-overlap indicators, not "
            "judgments of naturalness or proof that context was used causally."
        ),
    }, repetition_flags


def build_human_review_sample(
    records: list[dict[str, Any]],
    repetition_flags: set[int],
    *,
    per_category: int = 2,
) -> dict[str, list[dict[str, Any]]]:
    categories = {
        "relationship_grounded": [],
        "memory_grounded": [],
        "journal_grounded": [],
        "goal_or_intent_related": [],
        "town_event": [],
        "town_arc": [],
        "little_special_context": [],
        "suspected_repetitive_or_generic": [],
        "parser_or_action_mismatch": [],
    }

    for index, record in enumerate(records):
        values = _context_values(record)
        dialogue_tokens = _tokens(record.get("conversation", ""))
        matches = {
            name: bool(dialogue_tokens & _tokens(items))
            for name, items in values.items()
        }
        context = record.get("context", {})
        special = any(
            values[name]
            for name in (
                "relationship_history", "memory", "journal", "goal_or_intent",
                "daily_event", "town_arc",
            )
        )
        generic = any(
            pattern in record.get("conversation", "").lower()
            for pattern in GENERIC_PATTERNS
        )
        intent = context.get("speaker_intent") or {}
        event = context.get("daily_event")
        row = {
            "index": index,
            "day": record.get("day"),
            "hour": record.get("hour"),
            "location": record.get("location"),
            "speaker": record.get("speaker"),
            "listener": record.get("listener"),
            "dialogue": record.get("conversation"),
            "suggested_action": record.get("suggested_action"),
            "parsed_action": record.get("parsed_action"),
            "inferred_action": record.get("inferred_action"),
            "final_action": record.get("action"),
            "action_source": record.get("action_source"),
            "dialogue_source": record.get("dialogue_source"),
            "context": {
                "activity": context.get("activity_display") or context.get("activity"),
                "relationship_history": context.get("relationship_history", [])[:1],
                "memories": context.get("memories", [])[:2],
                "journal": context.get("journals", [])[:1],
                "goals": context.get("goals", [])[:3],
                "intent": intent.get("description") if isinstance(intent, dict) else intent,
                "daily_event": (
                    {"name": event.get("name"), "description": event.get("description")}
                    if event else None
                ),
                "town_arcs": [arc.get("name") for arc in context.get("town_arcs", [])],
                "recent_topics": context.get("recent_topics", [])[-4:],
                "recent_utterances": context.get("recent_utterances", [])[:2],
            },
        }
        memberships = []
        if matches["relationship_history"]:
            memberships.append("relationship_grounded")
        if matches["memory"]:
            memberships.append("memory_grounded")
        if matches["journal"]:
            memberships.append("journal_grounded")
        if matches["goal_or_intent"]:
            memberships.append("goal_or_intent_related")
        if matches["daily_event"]:
            memberships.append("town_event")
        if values["town_arc"]:
            memberships.append("town_arc")
        if not special:
            memberships.append("little_special_context")
        if index in repetition_flags or generic:
            memberships.append("suspected_repetitive_or_generic")
        if (
            record.get("parsed_action") != record.get("action")
            or record.get("suggested_action") != record.get("action")
            or record.get("action_source") != "llm"
        ):
            memberships.append("parser_or_action_mismatch")

        for category in memberships:
            if len(categories[category]) < per_category:
                categories[category].append(row)
    return categories


def _write_transcript(records: list[dict[str, Any]], path: Path) -> None:
    lines = ["# Real-LLM transcript", ""]
    for row in records:
        lines.extend(
            [
                f"## Day {row.get('day')}, {row.get('hour')}:00 — {row.get('location')}",
                "",
                f"**{row.get('speaker')} → {row.get('listener')}:** {row.get('conversation')}",
                "",
                f"Action: `{row.get('action')}` (suggested `{row.get('suggested_action')}`, "
                f"parsed `{row.get('parsed_action')}`, inferred `{row.get('inferred_action')}`)",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_review(sample: dict[str, list[dict[str, Any]]], path: Path) -> None:
    lines = [
        "# Human review sample",
        "",
        "Categories use lexical/context heuristics only. Read the dialogue and context to judge naturalness.",
        "",
    ]
    for category, rows in sample.items():
        lines.extend([f"## {category.replace('_', ' ').title()}", ""])
        if not rows:
            lines.extend(["No qualifying conversation in this short run.", ""])
            continue
        for row in rows:
            context = row["context"]
            lines.extend(
                [
                    f"- Day {row['day']} {row['hour']}:00, {row['speaker']} → "
                    f"{row['listener']} at {row['location']}: “{row['dialogue']}”",
                    f"  Actions: suggested `{row['suggested_action']}`, parsed "
                    f"`{row['parsed_action']}`, inferred `{row['inferred_action']}`, "
                    f"final `{row['final_action']}`.",
                    f"  Context: {json.dumps(context, sort_keys=True, ensure_ascii=False)}",
                    "",
                ]
            )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_real_llm_evaluation(
    benchmark: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    if len(benchmark.get("runs", [])) != 1:
        raise ValueError("real-LLM evaluation requires exactly one seed")
    run = benchmark["runs"][0]
    records = load_jsonl(output_dir / run["artifacts"]["conversations"])
    indicators, repetition_flags = analyze_real_llm_records(records, run["metrics"])
    sample = build_human_review_sample(records, repetition_flags)

    transcript_path = output_dir / "transcript.md"
    sample_json_path = output_dir / "human_review_sample.json"
    sample_markdown_path = output_dir / "human_review_sample.md"
    _write_transcript(records, transcript_path)
    sample_json_path.write_text(
        json.dumps(sample, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_review(sample, sample_markdown_path)

    config = benchmark["configuration"]
    document = {
        "schema_version": 1,
        "kind": "llm-town-real-llm-evaluation",
        "created_at": benchmark["created_at"],
        "revision": benchmark["revision"],
        "model": {
            "identifier": config["model_name"],
            "generation": {
                "max_new_tokens": config["max_new_tokens"],
                "do_sample": True,
                "temperature": config["temperature"],
                "top_p": config["top_p"],
            },
        },
        "simulation": {
            "days": config["days"],
            "hours": config["hours"],
            "seed": run["seed"],
            "metrics": run["metrics"],
        },
        "dialogue_evaluation": indicators,
        "artifacts": {
            "benchmark": "benchmark.json",
            "raw_conversations": run["artifacts"]["conversations"],
            "simulation_output": run["artifacts"]["simulation_output"],
            "transcript": transcript_path.name,
            "human_review_json": sample_json_path.name,
            "human_review_markdown": sample_markdown_path.name,
        },
    }
    (output_dir / "evaluation.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document
