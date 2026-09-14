"""Structured quality metrics for simulation runs.

This module contains no printing and no simulation orchestration.  Both the
human-readable quality report and the benchmark runner use these functions so
that a metric has one definition regardless of how a run was started.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any, Iterable


ACTION_TAGS = {
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

ARC_RELEVANT_ACTIONS = {
    "cooperate",
    "offer_help",
    "ask_for_help",
    "share_rumor",
    "argue",
    "apologize",
}

ARC_KEYWORDS = {
    "town_arc",
    "market",
    "business",
    "wealth",
    "community",
    "volunteer",
    "social",
    "knowledge",
    "rules",
    "learning",
}

INTENT_COMPATIBLE_ACTIONS = {
    "build_friendship": {"chat", "compliment", "offer_help", "cooperate"},
    "repair_relationship": {"chat", "apologize", "offer_help"},
    "investigate": {"chat", "ask_for_help", "share_rumor"},
    "socialize": {"chat", "compliment", "offer_help", "cooperate"},
    "seek_work": {"chat", "ask_for_help", "cooperate", "offer_help"},
}

RELATIONSHIP_LABELS = (
    "close friends",
    "friendly",
    "neutral",
    "tense",
    "enemies",
)


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    return numerator / denominator if denominator else 0.0


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []

    records = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON in {path} at line {line_number}: {error.msg}"
                ) from error
    return records


def load_state(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sorted_counter(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _relationship_label(score: int) -> str:
    if score >= 7:
        return "close friends"
    if score >= 3:
        return "friendly"
    if score <= -7:
        return "enemies"
    if score <= -3:
        return "tense"
    return "neutral"


def _conversation_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    actions = Counter(record.get("action", "unknown") for record in records)
    dialogue_counts = Counter(
        record.get("conversation", "").strip()
        for record in records
        if record.get("conversation", "").strip()
    )
    repeated_instances = sum(
        count - 1 for count in dialogue_counts.values() if count > 1
    )
    event_related = sum(
        "event" in record.get("tags", []) for record in records
    )
    arc_related = sum(
        bool(set(record.get("tags", [])) & ARC_KEYWORDS) for record in records
    )
    arc_actions = Counter(
        record.get("action", "unknown")
        for record in records
        if set(record.get("tags", [])) & ARC_KEYWORDS
        and record.get("action") in ARC_RELEVANT_ACTIONS
    )

    return {
        "total": total,
        "action_counts": dict(sorted(actions.items())),
        "action_rates": {
            action: safe_rate(count, total)
            for action, count in sorted(actions.items())
        },
        "unique_dialogues": len(dialogue_counts),
        "repeated_instances": repeated_instances,
        "repetition_rate": safe_rate(repeated_instances, total),
        "most_repeated_dialogues": [
            {"dialogue": dialogue, "count": count}
            for dialogue, count in sorted(
                dialogue_counts.items(), key=lambda item: (-item[1], item[0])
            )
            if count > 1
        ][:5],
        "daily_event_related": event_related,
        "daily_event_rate": safe_rate(event_related, total),
        "town_arc_related": arc_related,
        "town_arc_rate": safe_rate(arc_related, total),
        "arc_relevant_action_counts": dict(sorted(arc_actions.items())),
    }


def _nested_counts(counter: Counter) -> dict[str, dict[str, int]]:
    nested: dict[str, dict[str, int]] = {}
    for (outer, inner), count in sorted(counter.items()):
        nested.setdefault(outer, {})[inner] = count
    return nested


def analyze_intent_followthrough(
    conversations: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    locations_by_tick = {
        (row.get("day"), row.get("hour"), row.get("agent")): row.get(
            "location", ""
        )
        for row in events
        if row.get("type") == "activity"
    }

    with_intent = 0
    target_agent_opportunities = 0
    target_agent_matches = 0
    target_agent_unavailable = 0
    target_location_opportunities = 0
    target_location_matches = 0
    compatible_actions = 0
    intent_counts = Counter()
    action_by_intent = Counter()
    location_by_intent = Counter()
    suggested_actions = Counter()
    parsed_actions = Counter()
    inferred_actions = Counter()
    final_actions = Counter()
    final_action_reasons = Counter()
    suggested_to_final = Counter()
    parsed_to_final = Counter()
    inferred_to_final = Counter()

    for row in conversations:
        action = row.get("action", "")
        suggested = row.get("suggested_action", "")
        parsed = row.get("parsed_action", "")
        inferred = row.get("inferred_action", "")
        reason = row.get("final_action_reason", "")
        final_actions[action or "unknown"] += 1
        if suggested:
            suggested_actions[suggested] += 1
            suggested_to_final[(suggested, action)] += 1
        if parsed:
            parsed_actions[parsed] += 1
            parsed_to_final[(parsed, action)] += 1
        if inferred:
            inferred_actions[inferred] += 1
            inferred_to_final[(inferred, action)] += 1
        if reason:
            final_action_reasons[reason] += 1

        intent_type = row.get("speaker_intent_type", "")
        if not intent_type:
            continue

        with_intent += 1
        intent_counts[intent_type] += 1
        action_by_intent[(intent_type, action)] += 1
        location_by_intent[(intent_type, row.get("location", ""))] += 1
        if action in INTENT_COMPATIBLE_ACTIONS.get(intent_type, set()):
            compatible_actions += 1

        target_agent = row.get("speaker_intent_target_agent", "")
        if target_agent:
            target_location = locations_by_tick.get(
                (row.get("day"), row.get("hour"), target_agent), ""
            )
            if target_location == row.get("location", ""):
                target_agent_opportunities += 1
                if row.get("listener", "") == target_agent:
                    target_agent_matches += 1
            else:
                target_agent_unavailable += 1

        target_location = row.get("speaker_intent_target_location", "")
        if target_location:
            target_location_opportunities += 1
            if row.get("location", "") == target_location:
                target_location_matches += 1

    return {
        "conversations_with_intent": with_intent,
        "intent_counts": dict(sorted(intent_counts.items())),
        "target_agent_opportunities": target_agent_opportunities,
        "target_agent_matches": target_agent_matches,
        "target_agent_unavailable": target_agent_unavailable,
        "target_agent_rate": safe_rate(
            target_agent_matches, target_agent_opportunities
        ),
        "target_location_opportunities": target_location_opportunities,
        "target_location_matches": target_location_matches,
        "target_location_rate": safe_rate(
            target_location_matches, target_location_opportunities
        ),
        "compatible_actions": compatible_actions,
        "action_compatibility_rate": safe_rate(compatible_actions, with_intent),
        "actions_by_intent": _nested_counts(action_by_intent),
        "locations_by_intent": _nested_counts(location_by_intent),
        "action_pipeline": {
            "suggested_counts": dict(sorted(suggested_actions.items())),
            "parsed_counts": dict(sorted(parsed_actions.items())),
            "inferred_counts": dict(sorted(inferred_actions.items())),
            "final_counts": dict(sorted(final_actions.items())),
            "final_reason_counts": dict(sorted(final_action_reasons.items())),
            "suggested_to_final": _nested_counts(suggested_to_final),
            "parsed_to_final": _nested_counts(parsed_to_final),
            "inferred_to_final": _nested_counts(inferred_to_final),
        },
    }


def _state_metrics(state: dict[str, Any]) -> dict[str, Any]:
    agents = state.get("agents", [])
    active_counts = [len(agent.get("memory", [])) for agent in agents]
    archived_counts = [len(agent.get("memory_archive", [])) for agent in agents]
    memory_types = Counter(
        memory.get("type", "unknown")
        for agent in agents
        for memory in agent.get("memory", []) + agent.get("memory_archive", [])
    )

    relationship_scores = list(state.get("relationship_scores", {}).values())
    relationship_labels = Counter(
        _relationship_label(score) for score in relationship_scores
    )
    relationship_events = state.get("relationship_events", [])
    relationship_action_counts = Counter(
        event.get("action", "unknown") for event in relationship_events
    )

    active_intents = state.get("agent_intents", {})
    intent_history = state.get("intent_history", [])
    intent_types = Counter(
        intent.get("intent_type", "unknown") for intent in active_intents.values()
    )
    intent_outcomes = Counter(
        intent.get("status", "unknown") for intent in intent_history
    )

    arcs = state.get("town_arcs", [])
    journals_per_agent = [len(agent.get("daily_journals", [])) for agent in agents]
    current_day = state.get("current_day", 0) or 0
    expected_journals = len(agents) * current_day
    total_journals = sum(journals_per_agent)

    need_names = sorted(
        {
            need
            for agent in agents
            for need in agent.get("needs", {})
        }
    )
    average_needs = {
        need: fmean(
            agent.get("needs", {}).get(need, 0)
            for agent in agents
            if need in agent.get("needs", {})
        )
        for need in need_names
    }

    return {
        "memory": {
            "agent_count": len(agents),
            "average_active_per_agent": fmean(active_counts) if active_counts else 0.0,
            "average_archived_per_agent": (
                fmean(archived_counts) if archived_counts else 0.0
            ),
            "max_active_per_agent": max(active_counts, default=0),
            "max_archived_per_agent": max(archived_counts, default=0),
            "type_counts": dict(sorted(memory_types.items())),
        },
        "relationships": {
            "pair_count": len(relationship_scores),
            "average_score": (
                fmean(relationship_scores) if relationship_scores else 0.0
            ),
            "minimum_score": min(relationship_scores, default=0),
            "maximum_score": max(relationship_scores, default=0),
            "label_counts": {
                label: relationship_labels[label] for label in RELATIONSHIP_LABELS
            },
            "event_count": len(relationship_events),
            "positive_events": sum(
                event.get("relationship_change", 0) > 0
                for event in relationship_events
            ),
            "negative_events": sum(
                event.get("relationship_change", 0) < 0
                for event in relationship_events
            ),
            "neutral_events": sum(
                event.get("relationship_change", 0) == 0
                for event in relationship_events
            ),
            "event_action_counts": dict(sorted(relationship_action_counts.items())),
        },
        "intents": {
            "active": len(active_intents),
            "ended": len(intent_history),
            "active_type_counts": dict(sorted(intent_types.items())),
            "outcome_counts": dict(sorted(intent_outcomes.items())),
            "success_rate": safe_rate(intent_outcomes["succeeded"], len(intent_history)),
        },
        "town_arcs": {
            "total": len(arcs),
            "active": sum(arc.get("status") == "active" for arc in arcs),
            "resolved": sum(arc.get("status") == "resolved" for arc in arcs),
            "type_counts": _sorted_counter(
                arc.get("name", "unknown") for arc in arcs
            ),
        },
        "needs": {"averages": average_needs},
        "journals": {
            "total": total_journals,
            "average_per_agent": (
                fmean(journals_per_agent) if journals_per_agent else 0.0
            ),
            "minimum_per_agent": min(journals_per_agent, default=0),
            "maximum_per_agent": max(journals_per_agent, default=0),
            "coverage_rate": safe_rate(total_journals, expected_journals),
        },
    }


def _activity_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    activities = [row for row in events if row.get("type") == "activity"]
    return {
        "total": len(activities),
        "activity_counts": _sorted_counter(
            row.get("activity_name", "unknown") for row in activities
        ),
        "location_counts": _sorted_counter(
            row.get("location", "unknown") for row in activities
        ),
    }


def _arc_change_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    records_by_arc: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        records_by_arc.setdefault(record.get("arc_name", "unknown"), []).append(
            record
        )

    return {
        "causal_changes": len(records),
        "progress_increases": sum(
            row.get("new_progress", 0) > row.get("old_progress", 0)
            for row in records
        ),
        "tension_increases": sum(
            row.get("new_tension", 0) > row.get("old_tension", 0)
            for row in records
        ),
        "tension_decreases": sum(
            row.get("new_tension", 0) < row.get("old_tension", 0)
            for row in records
        ),
        "change_action_counts": _sorted_counter(
            row.get("action", "unknown") for row in records
        ),
        "change_arc_counts": _sorted_counter(
            row.get("arc_name", "unknown") for row in records
        ),
        "changes_by_arc": {
            arc_name: {
                "changes": len(arc_records),
                "progress_increases": sum(
                    row.get("new_progress", 0) > row.get("old_progress", 0)
                    for row in arc_records
                ),
                "tension_increases": sum(
                    row.get("new_tension", 0) > row.get("old_tension", 0)
                    for row in arc_records
                ),
                "tension_decreases": sum(
                    row.get("new_tension", 0) < row.get("old_tension", 0)
                    for row in arc_records
                ),
                "action_counts": _sorted_counter(
                    row.get("action", "unknown") for row in arc_records
                ),
            }
            for arc_name, arc_records in sorted(records_by_arc.items())
        },
    }


def _check(
    value: int | float,
    expectation: str,
    passed: bool,
    *,
    applicable: bool = True,
) -> dict[str, Any]:
    return {
        "status": "pass" if passed else ("warn" if applicable else "no_data"),
        "passed": passed if applicable else None,
        "value": value,
        "expectation": expectation,
    }


def _quality_checks(metrics: dict[str, Any]) -> dict[str, Any]:
    conversations = metrics["conversations"]
    memory = metrics["memory"]
    journals = metrics["journals"]
    total = conversations["total"]
    rates = conversations["action_rates"]
    has_agents = memory["agent_count"] > 0
    memory_types = memory["type_counts"]

    checks = {
        "repetition_rate": _check(
            conversations["repetition_rate"],
            "at most 5%",
            conversations["repetition_rate"] <= 0.05,
            applicable=total > 0,
        ),
        "chat_rate": _check(
            rates.get("chat", 0.0),
            "between 60% and 80%",
            0.60 <= rates.get("chat", 0.0) <= 0.80,
            applicable=total > 0,
        ),
        "compliment_rate": _check(
            rates.get("compliment", 0.0),
            "between 5% and 15%",
            0.05 <= rates.get("compliment", 0.0) <= 0.15,
            applicable=total > 0,
        ),
        "daily_event_rate": _check(
            conversations["daily_event_rate"],
            "between 20% and 40%",
            0.20 <= conversations["daily_event_rate"] <= 0.40,
            applicable=total > 0,
        ),
        "max_active_memories": _check(
            memory["max_active_per_agent"],
            "at most 200 per agent",
            memory["max_active_per_agent"] <= 200,
            applicable=has_agents,
        ),
        "average_active_memories": _check(
            memory["average_active_per_agent"],
            "at most 150 per agent",
            memory["average_active_per_agent"] <= 150,
            applicable=has_agents,
        ),
        "conversation_memories": _check(
            memory_types.get("conversation", 0),
            "at least one",
            memory_types.get("conversation", 0) > 0,
            applicable=has_agents,
        ),
        "daily_event_memories": _check(
            memory_types.get("daily_event", 0),
            "at least one",
            memory_types.get("daily_event", 0) > 0,
            applicable=has_agents,
        ),
        "town_arc_participation_memories": _check(
            memory_types.get("town_arc_participation", 0),
            "at least one",
            memory_types.get("town_arc_participation", 0) > 0,
            applicable=has_agents,
        ),
        "journal_coverage": _check(
            journals["coverage_rate"],
            "one journal per agent per completed day",
            journals["coverage_rate"] == 1.0,
            applicable=has_agents,
        ),
    }

    applicable = [check for check in checks.values() if check["passed"] is not None]
    passed = sum(check["passed"] is True for check in applicable)
    return {
        "checks": checks,
        "passed": passed,
        "applicable": len(applicable),
        "pass_rate": safe_rate(passed, len(applicable)),
    }


def analyze_run(
    conversations: list[dict[str, Any]],
    state: dict[str, Any],
    events: list[dict[str, Any]] | None = None,
    arc_changes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return all benchmark metrics for one completed simulation run."""

    events = events or []
    arc_changes = arc_changes or []
    metrics = {
        "conversations": _conversation_metrics(conversations),
        "intent_followthrough": analyze_intent_followthrough(
            conversations, events
        ),
        "activities": _activity_metrics(events),
        **_state_metrics(state),
    }
    metrics["town_arcs"].update(_arc_change_metrics(arc_changes))
    metrics["quality"] = _quality_checks(metrics)
    return metrics


def analyze_run_files(
    conversations_path: str | Path,
    state_path: str | Path,
    events_path: str | Path,
    arc_changes_path: str | Path,
) -> dict[str, Any]:
    return analyze_run(
        conversations=load_jsonl(conversations_path),
        state=load_state(state_path),
        events=load_jsonl(events_path),
        arc_changes=load_jsonl(arc_changes_path),
    )


KPI_PATHS = (
    "conversations.total",
    "conversations.repetition_rate",
    "conversations.daily_event_rate",
    "conversations.town_arc_rate",
    "intent_followthrough.target_agent_rate",
    "intent_followthrough.target_location_rate",
    "intent_followthrough.action_compatibility_rate",
    "relationships.average_score",
    "intents.success_rate",
    "town_arcs.causal_changes",
    "town_arcs.resolved",
    "memory.average_active_per_agent",
    "memory.max_active_per_agent",
    "journals.coverage_rate",
    "quality.pass_rate",
)


def metric_at(metrics: dict[str, Any], path: str) -> int | float:
    value: Any = metrics
    for part in path.split("."):
        value = value[part]
    if not isinstance(value, (int, float)):
        raise TypeError(f"Metric at {path!r} is not numeric")
    return value


def aggregate_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate stable KPIs and check outcomes across benchmark seeds."""

    kpis = {}
    for path in KPI_PATHS:
        values = [metric_at(run["metrics"], path) for run in runs]
        kpis[path] = {
            "mean": fmean(values) if values else 0.0,
            "minimum": min(values, default=0),
            "maximum": max(values, default=0),
            "population_stddev": pstdev(values) if len(values) > 1 else 0.0,
            "values": values,
        }

    check_names = sorted(
        {
            name
            for run in runs
            for name in run["metrics"]["quality"]["checks"]
        }
    )
    checks = {}
    for name in check_names:
        statuses = [
            run["metrics"]["quality"]["checks"][name]["passed"]
            for run in runs
        ]
        applicable = [status for status in statuses if status is not None]
        passed = sum(status is True for status in applicable)
        checks[name] = {
            "passed_runs": passed,
            "applicable_runs": len(applicable),
            "pass_rate": safe_rate(passed, len(applicable)),
        }

    pooled_actions = Counter()
    for run in runs:
        pooled_actions.update(run["metrics"]["conversations"]["action_counts"])
    total_actions = sum(pooled_actions.values())

    return {
        "run_count": len(runs),
        "kpis": kpis,
        "quality_checks": checks,
        "pooled_action_counts": dict(sorted(pooled_actions.items())),
        "pooled_action_rates": {
            action: safe_rate(count, total_actions)
            for action, count in sorted(pooled_actions.items())
        },
    }
