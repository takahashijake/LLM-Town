"""Auditable measurements and review samples for controlled real-LLM runs."""

from __future__ import annotations

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from src.analysis.quality_metrics import (
    INTENT_COMPATIBLE_ACTIONS,
    load_jsonl,
    safe_rate,
)


EVALUATION_SCHEMA_VERSION = 2


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
            (context.get("active_goal") or {}).get("description", ""),
            (context.get("active_goal") or {}).get("strategy", ""),
            intent.get("description", "") if isinstance(intent, dict) else intent,
        ],
        "occupation": [context.get("occupation") or ""],
        "activity": [
            context.get("activity_display") or context.get("activity") or ""
        ],
        "daily_event": [
            f"{event.get('name', '')} {event.get('description', '')}"
        ] if event and context.get("daily_event_relevant") else [],
        "town_arc": [
            f"{arc.get('name', '')} {arc.get('description', '')}"
            for arc in context.get("town_arcs", [])
        ],
        "reputation": context.get("reputation", []),
        "reputation_rumor": [context.get("reputation_rumor", "")],
    }


def _lexical_context_use(records: list[dict[str, Any]]) -> dict[str, Any]:
    indicators = {}
    for category in (
        "relationship_history", "memory", "journal", "goal_or_intent",
        "occupation", "activity", "daily_event", "town_arc",
        "reputation", "reputation_rumor",
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


def _action_language_diagnostics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Expose recorded parser/inference/final-action decisions for audit."""
    inference_reasons = Counter(
        row.get("inference_reason", "not_recorded") for row in records
    )
    disagreements = [
        row for row in records
        if row.get("parsed_action") and row.get("inferred_action")
        and row["parsed_action"] != row["inferred_action"]
    ]
    inferred_non_chat_capped = [
        row for row in records
        if row.get("inferred_action") not in {"", "chat"}
        and row.get("action") == "chat"
    ]
    return {
        "parser_inference_disagreements": len(disagreements),
        "parser_inference_disagreement_pairs": dict(sorted(Counter(
            f"{row.get('parsed_action', '')}->{row.get('inferred_action', '')}"
            for row in disagreements
        ).items())),
        "inferred_non_chat_finalized_as_chat": len(inferred_non_chat_capped),
        "inferred_non_chat_finalized_as_chat_reasons": dict(sorted(Counter(
            row.get("final_action_reason", "not_recorded")
            for row in inferred_non_chat_capped
        ).items())),
        "inference_reason_counts": dict(sorted(inference_reasons.items())),
        "note": (
            "A parser/inference disagreement is an audit candidate, not an error: "
            "the final action also reflects allowed-action and repetition-cap policy."
        ),
    }


def _strategy_adaptation_diagnostics(state_path: Path) -> dict[str, Any]:
    """Explain adaptation outcomes from durable goal evidence without mutation."""
    if not state_path.is_file():
        return {
            "goals_reviewed": 0,
            "adaptations_triggered": 0,
            "adaptations_not_triggered": 0,
            "goals": [],
            "note": "No persisted state artifact was available for goal adaptation review.",
        }
    state = json.loads(state_path.read_text(encoding="utf-8"))
    rows = []
    for agent in state.get("agents", []):
        for goal in agent.get("structured_goals", []):
            adaptations = [
                evidence for evidence in goal.get("evidence", [])
                if evidence.get("type") == "strategy_adaptation"
            ]
            selections = [
                evidence for evidence in goal.get("evidence", [])
                if evidence.get("type") == "strategy_selected"
            ]
            if adaptations:
                outcome = "triggered"
                reason = "Recorded strategy replacement after a terminal tactic trigger."
            elif goal.get("status") in {"achieved", "blocked", "abandoned"}:
                outcome = "not_triggered"
                reason = "Goal reached a terminal state without a recorded strategy replacement."
            elif selections:
                outcome = "not_triggered"
                reason = "Current tactic remained active; no terminal trigger required replacement."
            else:
                outcome = "not_applicable"
                reason = "No feasible strategy was selected for this goal during the run."
            rows.append({
                "agent": agent.get("name", ""),
                "goal_id": goal.get("id", ""),
                "goal": goal.get("description", ""),
                "goal_status": goal.get("status", "active"),
                "outcome": outcome,
                "reason": reason,
                "current_strategy": goal.get("current_strategy"),
                "adaptation_count": len(adaptations),
                "adaptations": adaptations,
            })
    return {
        "goals_reviewed": len(rows),
        "adaptations_triggered": sum(row["outcome"] == "triggered" for row in rows),
        "adaptations_not_triggered": sum(row["outcome"] == "not_triggered" for row in rows),
        "goals": rows,
        "note": (
            "This is derived from persisted goal evidence. It distinguishes a recorded "
            "replacement from a stable or terminal goal; it does not infer unrecorded causes."
        ),
    }


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
    fallback_flags = [
        row.get("action_source", "llm") != "llm"
        or row.get("dialogue_source", "llm") != "llm"
        or bool(row.get("generation_error"))
        for row in records
    ]
    fallbacks = sum(fallback_flags)
    relationship_opportunities = sum(
        row.get("relationship_snapshot", {}).get("interaction_count", 0) > 0
        for row in records
    )
    relationship_influenced = sum(
        bool(row.get("relationship_influenced")) for row in records
    )
    valid_relationship_diagnostics = sum(
        bool(row.get("relationship_snapshot", {}).get("interaction_count", 0))
        and bool(row.get("retrieved_social_memories"))
        and bool(row.get("relationship_decision_reasons"))
        for row in records
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
            "malformed_response_rate": safe_rate(malformed, len(records)),
            "generation_exceptions": generation_errors,
            "generation_exception_rate": safe_rate(generation_errors, len(records)),
            "dialogue_fallbacks": fallbacks,
            "dialogue_fallback_rate": safe_rate(fallbacks, len(records)),
        },
        "generic_phrase_flags": generic,
        "generic_phrase_rate": safe_rate(generic, len(records)),
        "intent_action_compatibility": simulation_metrics.get(
            "intent_followthrough", {}
        ).get("action_compatibility_rate", 0.0),
        "action_language_diagnostics": _action_language_diagnostics(records),
        "relationship_conditioning_diagnostics": {
            "opportunities": relationship_opportunities,
            "influenced_decisions": relationship_influenced,
            "influenced_decision_rate": safe_rate(
                relationship_influenced, relationship_opportunities
            ),
            "valid_diagnostics": valid_relationship_diagnostics,
            "valid_diagnostics_rate": safe_rate(
                valid_relationship_diagnostics, relationship_opportunities
            ),
            "context_present_without_measurable_policy_influence": max(
                0, relationship_opportunities - relationship_influenced
            ),
        },
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
        "intent_or_goal_related": [],
        "activity_grounded": [],
        "daily_event_related": [],
        "town_arc_related": [],
        "ordinary_low_context": [],
        "suspected_repetitive_or_generic": [],
        "malformed_or_fallback": [],
        "intent_action_mismatch": [],
        "model_action_or_inference_disagreement": [],
        "direct_reputation_grounded_interaction": [],
        "legitimate_rumor_transmission": [],
        "behavior_influenced_by_reputation": [],
        "unsupported_rumor_blocked_or_fallback": [],
        "goal_grounded_dialogue": [],
        "intent_serving_active_goal": [],
        "strategy_adaptation": [],
        "goal_progress": [],
        "goal_reputation_tension": [],
        "relationship_conditioned_decision": [],
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
                "relationship_history", "memory", "journal", "daily_event", "town_arc",
                "reputation", "reputation_rumor",
            )
        ) or bool(context.get("speaker_intent"))
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
            "inference_reason": record.get("inference_reason", "not_recorded"),
            "final_action_reason": record.get("final_action_reason", "not_recorded"),
            "final_action": record.get("action"),
            "action_source": record.get("action_source"),
            "dialogue_source": record.get("dialogue_source"),
            "context": {
                "activity": context.get("activity_display") or context.get("activity"),
                "relationship_history": context.get("relationship_history", [])[:1],
                "memories": context.get("memories", [])[:2],
                "journal": context.get("journals", [])[:1],
                "goals": context.get("goals", [])[:3],
                "active_goal": context.get("active_goal"),
                "intent": intent.get("description") if isinstance(intent, dict) else intent,
                "daily_event": (
                    {"name": event.get("name"), "description": event.get("description")}
                    if event else None
                ),
                "town_arcs": [arc.get("name") for arc in context.get("town_arcs", [])],
                "recent_topics": context.get("recent_topics", [])[-4:],
                "recent_utterances": context.get("recent_utterances", [])[:2],
                "reputation": context.get("reputation", [])[:2],
                "reputation_rumor": context.get("reputation_rumor", ""),
            },
        }
        memberships = []
        if matches["relationship_history"]:
            memberships.append("relationship_grounded")
        if matches["memory"]:
            memberships.append("memory_grounded")
        if matches["goal_or_intent"]:
            memberships.append("intent_or_goal_related")
            if context.get("active_goal"):
                memberships.append("goal_grounded_dialogue")
        active_goal = context.get("active_goal") or {}
        if active_goal and context.get("speaker_intent"):
            memberships.append("intent_serving_active_goal")
        if active_goal.get("adaptation_count", 0) > 0:
            memberships.append("strategy_adaptation")
        if active_goal.get("progress", 0) > 0:
            memberships.append("goal_progress")
        if active_goal and context.get("reputation"):
            memberships.append("goal_reputation_tension")
        if matches["activity"]:
            memberships.append("activity_grounded")
        if matches["daily_event"]:
            memberships.append("daily_event_related")
        if matches["town_arc"]:
            memberships.append("town_arc_related")
        if not special:
            memberships.append("ordinary_low_context")
        if index in repetition_flags or generic:
            memberships.append("suspected_repetitive_or_generic")
        if (
            record.get("action_source", "llm") != "llm"
            or record.get("dialogue_source", "llm") != "llm"
            or bool(record.get("generation_error"))
        ):
            memberships.append("malformed_or_fallback")
        intent_type = record.get("speaker_intent_type", "")
        target_agent = record.get("speaker_intent_target_agent", "")
        target_location = record.get("speaker_intent_target_location", "")
        intent_applies = (
            (not target_agent or target_agent == record.get("listener", ""))
            and (not target_location or target_location == record.get("location", ""))
        )
        if (
            intent_type
            and intent_applies
            and record.get("action") not in INTENT_COMPATIBLE_ACTIONS.get(
                intent_type, set()
            )
        ):
            memberships.append("intent_action_mismatch")
        if (
            record.get("parsed_action")
            and record.get("inferred_action")
            and record.get("parsed_action") != record.get("inferred_action")
        ):
            memberships.append("model_action_or_inference_disagreement")
        if matches["reputation"] and any(
            "direct experience" in str(item).lower()
            for item in values["reputation"]
        ):
            memberships.append("direct_reputation_grounded_interaction")
        if record.get("rumor_transmission"):
            memberships.append("legitimate_rumor_transmission")
        if record.get("reputation_influenced"):
            memberships.append("behavior_influenced_by_reputation")
        if record.get("relationship_influenced"):
            memberships.append("relationship_conditioned_decision")
        if record.get("dialogue_source") == "policy_fallback_unsourced_hearsay":
            memberships.append("unsupported_rumor_blocked_or_fallback")

        for category in memberships:
            if len(categories[category]) < per_category:
                categories[category].append(row)
    return categories


def _write_transcript(records: list[dict[str, Any]], path: Path) -> None:
    lines = ["REAL-LLM TRANSCRIPT", ""]
    for row in records:
        lines.extend(
            [
                f"Day {row.get('day')}, {row.get('hour')}:00 at {row.get('location')}",
                f"{row.get('speaker')} -> {row.get('listener')}: {row.get('conversation')}",
                f"Action: {row.get('action')} (suggested {row.get('suggested_action')}, "
                f"parsed {row.get('parsed_action')}, inferred {row.get('inferred_action')}; "
                f"inference {row.get('inference_reason', 'not_recorded')}, final "
                f"{row.get('final_action_reason', 'not_recorded')})",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_review(sample: dict[str, list[dict[str, Any]]], path: Path) -> None:
    lines = [
        "# Real-LLM human review",
        "",
        "Categories use conservative lexical and recorded-pipeline heuristics. "
        "They identify review candidates, not proven causal context use or subjective quality.",
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
                    f"final `{row['final_action']}`; inference `"
                    f"{row['inference_reason']}`, final-selection `"
                    f"{row['final_action_reason']}`; action source "
                    f"`{row['action_source']}`, dialogue source `{row['dialogue_source']}`.",
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
    adaptation_diagnostics = _strategy_adaptation_diagnostics(
        output_dir / run["artifacts"].get("state", "missing-save-state.json")
    )

    transcript_path = output_dir / "transcript.txt"
    sample_json_path = output_dir / "human_review_sample.json"
    sample_markdown_path = output_dir / "review.md"
    adaptation_diagnostics_path = output_dir / "strategy_adaptation_diagnostics.json"
    _write_transcript(records, transcript_path)
    sample_json_path.write_text(
        json.dumps(sample, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    adaptation_diagnostics_path.write_text(
        json.dumps(adaptation_diagnostics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_review(sample, sample_markdown_path)

    config = benchmark["configuration"]
    metadata = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "kind": "llm-town-real-llm-evaluation",
        "timestamp": benchmark["created_at"],
        "git_commit": benchmark.get("revision", {}).get("commit", "unknown"),
        "git_dirty": benchmark.get("revision", {}).get("dirty"),
        "python_version": benchmark.get("environment", {}).get("python", "unknown"),
        "model_identifier": config["model_name"],
        "generation_settings": {
            "max_new_tokens": config["max_new_tokens"],
            "do_sample": True,
            "temperature": config["temperature"],
            "top_p": config["top_p"],
        },
        "days": config["days"],
        "hours": config["hours"],
        "seed": run["seed"],
    }
    simulation_metrics = run["metrics"]
    health = indicators["response_health"]
    metrics = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "total_conversations": indicators["conversation_count"],
        "exact_repetition": {
            "count": indicators["dialogue_repetition"]["exact_repeated_instances"],
            "rate": indicators["dialogue_repetition"]["exact_repetition_rate"],
        },
        "near_repetition": {
            "count": indicators["dialogue_repetition"]["near_repeated_instances"],
            "rate": indicators["dialogue_repetition"]["near_repetition_rate"],
        },
        "action_distribution": simulation_metrics.get("conversations", {}).get(
            "action_counts", {}
        ),
        "action_parse": {
            "success_count": health["action_parsing_successes"],
            "success_rate": health["action_parsing_success_rate"],
            "source_counts": health["action_source_counts"],
        },
        "malformed_output": {
            "count": health["malformed_responses"],
            "rate": health["malformed_response_rate"],
        },
        "fallback": {
            "count": health["dialogue_fallbacks"],
            "rate": health["dialogue_fallback_rate"],
            "dialogue_source_counts": health["dialogue_source_counts"],
        },
        "intent_action_compatibility": indicators["intent_action_compatibility"],
        "action_language_diagnostics": indicators["action_language_diagnostics"],
        "strategy_adaptation_diagnostics": {
            "goals_reviewed": adaptation_diagnostics["goals_reviewed"],
            "adaptations_triggered": adaptation_diagnostics["adaptations_triggered"],
            "adaptations_not_triggered": adaptation_diagnostics["adaptations_not_triggered"],
        },
        "daily_event_usage": {
            "count": simulation_metrics.get("conversations", {}).get(
                "daily_event_related", 0
            ),
            "rate": simulation_metrics.get("conversations", {}).get(
                "daily_event_rate", 0.0
            ),
        },
        "town_arc_usage": {
            "count": indicators["context_use_indicators"]["town_arc"][
                "lexical_matches"
            ],
            "rate": safe_rate(
                indicators["context_use_indicators"]["town_arc"][
                    "lexical_matches"
                ],
                indicators["conversation_count"],
            ),
            "opportunities": indicators["context_use_indicators"]["town_arc"][
                "opportunities"
            ],
            "opportunity_match_rate": indicators["context_use_indicators"][
                "town_arc"
            ]["lexical_match_rate"],
        },
        "context_use_indicators": indicators["context_use_indicators"],
        "reputation": simulation_metrics.get("reputation", {}),
        "goals": simulation_metrics.get("goals", {}),
        "intents": simulation_metrics.get("intents", {}),
        "suspected_generic": {
            "count": indicators["generic_phrase_flags"],
            "rate": indicators["generic_phrase_rate"],
        },
        "exceptions_errors": {
            "generation_exception_count": health["generation_exceptions"],
            "generation_exception_rate": health["generation_exception_rate"],
            "examples": [
                row.get("generation_error")
                for row in records
                if row.get("generation_error")
            ][:10],
        },
        "measurement_note": indicators["measurement_note"],
    }
    metadata_path = output_dir / "metadata.json"
    metrics_path = output_dir / "metrics.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # Keep one combined index for compatibility with interrupted Part 2 tooling.
    document = {
        **metadata,
        "model": {
            "identifier": metadata["model_identifier"],
            "generation": metadata["generation_settings"],
        },
        "simulation": {"metrics": simulation_metrics},
        "dialogue_evaluation": indicators,
        "metrics": metrics,
        "artifacts": {
            "benchmark": "benchmark.json",
            "metadata": metadata_path.name,
            "metrics": metrics_path.name,
            "raw_conversations": run["artifacts"]["conversations"],
            "simulation_output": run["artifacts"]["simulation_output"],
            "transcript": transcript_path.name,
            "human_review_json": sample_json_path.name,
            "human_review_markdown": sample_markdown_path.name,
            "strategy_adaptation_diagnostics": adaptation_diagnostics_path.name,
        },
    }
    (output_dir / "evaluation.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document


def run_real_llm_evaluation(config, output_dir: str | Path, *, project_root="."):
    """Run one isolated real-model seed and write the evaluation artifacts."""
    if config.fake_llm:
        raise ValueError("real-LLM evaluation cannot use the deterministic fake LLM")
    if len(config.seeds) != 1:
        raise ValueError("real-LLM evaluation requires exactly one seed")

    from src.analysis.benchmark import run_benchmark

    benchmark = run_benchmark(config, output_dir, project_root=project_root)
    return write_real_llm_evaluation(benchmark, output_dir)
