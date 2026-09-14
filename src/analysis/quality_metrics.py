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
    "repair_relationship": {"chat", "apologize", "offer_help", "cooperate"},
    "investigate": {"chat", "ask_for_help", "share_rumor"},
    "socialize": {"chat", "compliment", "offer_help", "ask_for_help", "cooperate"},
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
        "reputation_influenced_decisions": sum(
            bool(record.get("reputation_influenced")) for record in records
        ),
        "unsupported_rumor_fallbacks": sum(
            record.get("dialogue_source") == "policy_fallback_unsourced_hearsay"
            for record in records
        ),
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
    intent_action_opportunities = 0
    intent_not_applicable = 0
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
        target_agent = row.get("speaker_intent_target_agent", "")
        intent_target_location = row.get("speaker_intent_target_location", "")
        intent_applies = (
            (not target_agent or target_agent == row.get("listener", ""))
            and (
                not intent_target_location
                or intent_target_location == row.get("location", "")
            )
        )
        if intent_applies:
            intent_action_opportunities += 1
            if action in INTENT_COMPATIBLE_ACTIONS.get(intent_type, set()):
                compatible_actions += 1
        else:
            intent_not_applicable += 1

        if target_agent:
            target_agent_location = locations_by_tick.get(
                (row.get("day"), row.get("hour"), target_agent), ""
            )
            if target_agent_location == row.get("location", ""):
                target_agent_opportunities += 1
                if row.get("listener", "") == target_agent:
                    target_agent_matches += 1
            else:
                target_agent_unavailable += 1

        if intent_target_location:
            target_location_opportunities += 1
            if row.get("location", "") == intent_target_location:
                target_location_matches += 1

    return {
        "conversations_with_intent": with_intent,
        "intent_action_opportunities": intent_action_opportunities,
        "intent_not_applicable": intent_not_applicable,
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
        "action_compatibility_rate": safe_rate(
            compatible_actions, intent_action_opportunities
        ),
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
    all_intents = [*active_intents.values(), *intent_history]
    linked_intents = [intent for intent in all_intents if intent.get("parent_goal_id")]
    intents_per_goal_counts = Counter(
        intent.get("parent_goal_id") for intent in linked_intents
    )
    goals = [
        goal for agent in agents for goal in agent.get("structured_goals", [])
    ]
    goal_statuses = Counter(goal.get("status", "active") for goal in goals)
    goal_categories = Counter(goal.get("category", "unknown") for goal in goals)
    achieved_by_category = Counter(
        goal.get("category", "unknown") for goal in goals
        if goal.get("status") == "achieved"
    )
    terminal_by_category = Counter(
        goal.get("category", "unknown") for goal in goals
        if goal.get("status") in {"achieved", "blocked", "abandoned"}
    )
    terminal_goals = sum(
        goal_statuses[status] for status in ("achieved", "blocked", "abandoned")
    )
    progress_rates = [
        safe_rate(goal.get("progress", 0), goal.get("progress_target", 1))
        for goal in goals
    ]
    achievement_times = [
        goal["completion_day"] - goal.get("created_day", 0)
        for goal in goals
        if goal.get("status") == "achieved" and goal.get("completion_day") is not None
    ]
    adaptations = [
        record for goal in goals for record in goal.get("evidence", [])
        if record.get("type") == "strategy_adaptation"
    ]
    progress_records = [
        record for goal in goals for record in goal.get("evidence", [])
        if record.get("type") == "progress"
    ]

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
            "outcome_rates": {
                status: safe_rate(intent_outcomes[status], len(intent_history))
                for status in (
                    "succeeded", "failed", "superseded", "blocked", "expired"
                )
            },
            "success_rate": safe_rate(intent_outcomes["succeeded"], len(intent_history)),
            "succeeded": intent_outcomes["succeeded"],
            "failed": intent_outcomes["failed"],
            "superseded": intent_outcomes["superseded"],
            "blocked": intent_outcomes["blocked"],
            "expired": intent_outcomes["expired"],
            "expiration_no_opportunity": sum(
                intent.get("expiration_reason") == "no_opportunity"
                for intent in intent_history
            ),
            "expiration_despite_opportunity": sum(
                intent.get("expiration_reason") == "despite_opportunity"
                for intent in intent_history
            ),
            "average_intents_per_goal": (
                fmean(intents_per_goal_counts.values()) if intents_per_goal_counts else 0.0
            ),
            "average_tactical_progress": (
                fmean(intent.get("progress", 0) for intent in all_intents)
                if all_intents else 0.0
            ),
        },
        "goals": {
            "created": len(goals),
            "active": goal_statuses["active"],
            "achieved": goal_statuses["achieved"],
            "blocked": goal_statuses["blocked"],
            "abandoned": goal_statuses["abandoned"],
            "paused": goal_statuses["paused"],
            "attainment_rate": safe_rate(goal_statuses["achieved"], terminal_goals),
            "average_progress": fmean(progress_rates) if progress_rates else 0.0,
            "average_time_to_achievement": (
                fmean(achievement_times) if achievement_times else 0.0
            ),
            "category_counts": dict(sorted(goal_categories.items())),
            "achievement_by_category": dict(sorted(achieved_by_category.items())),
            "attainment_rate_by_category": {
                category: safe_rate(achieved_by_category[category], count)
                for category, count in sorted(terminal_by_category.items())
            },
            "strategy_adaptations": len(adaptations),
            "reputation_triggered_adaptations": sum(
                record.get("trigger") == "reputation" for record in adaptations
            ),
            "relationship_triggered_adaptations": sum(
                record.get("trigger") == "relationship" for record in adaptations
            ),
            "goals_recovered_after_adaptation": sum(
                bool(goal.get("recovered_after_adaptation")) for goal in goals
            ),
            "applicable_progress_opportunities": sum(
                int(intent.get("opportunity_count", 0)) for intent in all_intents
            ),
            "opportunities_that_produced_progress": len(progress_records),
            "opportunity_progress_rate": safe_rate(
                len(progress_records),
                sum(int(intent.get("opportunity_count", 0)) for intent in all_intents),
            ),
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


def _reputation_metrics(
    state: dict[str, Any],
    conversations: list[dict[str, Any]],
) -> dict[str, Any]:
    agents = state.get("agents", [])
    beliefs = []
    beliefs_per_agent = {}
    signs_by_subject_dimension: dict[tuple[str, str], set[int]] = {}
    for agent in agents:
        count = 0
        for target, dimensions in agent.get("reputation_beliefs", {}).items():
            for dimension, belief in dimensions.items():
                row = {
                    "observer": agent.get("name", "unknown"),
                    "target_agent": target,
                    "dimension": dimension,
                    **belief,
                }
                beliefs.append(row)
                count += 1
                score = float(belief.get("score", 0.0))
                sign = 1 if score > 0 else (-1 if score < 0 else 0)
                signs_by_subject_dimension.setdefault((target, dimension), set()).add(sign)
        beliefs_per_agent[agent.get("name", "unknown")] = count

    distributions = {}
    dimensions = sorted({belief["dimension"] for belief in beliefs})
    for dimension in dimensions:
        scores = [
            float(belief.get("score", 0.0))
            for belief in beliefs
            if belief["dimension"] == dimension
        ]
        distributions[dimension] = {
            "count": len(scores),
            "average": fmean(scores) if scores else 0.0,
            "minimum": min(scores, default=0.0),
            "maximum": max(scores, default=0.0),
        }

    updates = state.get("reputation_updates", [])
    source_counts = Counter(
        update.get("source_type", "unknown") for update in updates
    )
    hearsay_updates = [
        update for update in updates if update.get("source_type") == "hearsay"
    ]
    confidences = [float(belief.get("confidence", 0.0)) for belief in beliefs]
    return {
        "update_count": len(updates),
        "source_type_counts": dict(sorted(source_counts.items())),
        "direct_updates": sum(
            source_counts[source]
            for source in ("direct_interaction", "direct_observation")
        ),
        "hearsay_updates": len(hearsay_updates),
        "belief_count": len(beliefs),
        "beliefs_per_agent": dict(sorted(beliefs_per_agent.items())),
        "score_distribution_by_dimension": distributions,
        "average_confidence": fmean(confidences) if confidences else 0.0,
        "rumor_transmissions": sum(
            record.get("action") == "share_rumor" for record in conversations
        ),
        "duplicate_or_rejected_rumor_transmissions": max(
            0,
            sum(
                record.get("action") == "share_rumor"
                for record in conversations
            ) - len(hearsay_updates),
        ),
        "unique_rumor_subjects": len(
            {update.get("target_agent") for update in hearsay_updates}
        ),
        "maximum_transmission_depth": max(
            (int(update.get("transmission_depth", 0)) for update in hearsay_updates),
            default=0,
        ),
        "third_party_reputation_changes": sum(
            bool(update.get("third_party")) for update in updates
        ),
        "behavior_decisions_influenced": sum(
            bool(record.get("reputation_influenced"))
            for record in conversations
        ),
        "unsupported_rumors_blocked": sum(
            record.get("dialogue_source") == "policy_fallback_unsourced_hearsay"
            for record in conversations
        ),
        "disagreements": sum(
            1 for signs in signs_by_subject_dimension.values()
            if 1 in signs and -1 in signs
        ),
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
        "reputation": _reputation_metrics(state, conversations),
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
    "goals.attainment_rate",
    "goals.average_progress",
    "goals.strategy_adaptations",
    "goals.reputation_triggered_adaptations",
    "goals.opportunity_progress_rate",
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

    reputation_fields = (
        "update_count",
        "direct_updates",
        "hearsay_updates",
        "belief_count",
        "average_confidence",
        "rumor_transmissions",
        "duplicate_or_rejected_rumor_transmissions",
        "unique_rumor_subjects",
        "maximum_transmission_depth",
        "third_party_reputation_changes",
        "behavior_decisions_influenced",
        "unsupported_rumors_blocked",
        "disagreements",
    )
    goal_count_fields = (
        "created", "active", "achieved", "blocked", "abandoned", "paused",
        "strategy_adaptations", "reputation_triggered_adaptations",
        "relationship_triggered_adaptations", "goals_recovered_after_adaptation",
        "applicable_progress_opportunities", "opportunities_that_produced_progress",
    )
    pooled_goal_counts = {
        field: sum(run["metrics"]["goals"][field] for run in runs)
        for field in goal_count_fields
    }
    pooled_terminal = (
        pooled_goal_counts["achieved"] + pooled_goal_counts["blocked"]
        + pooled_goal_counts["abandoned"]
    )
    intent_outcome_fields = (
        "succeeded", "failed", "superseded", "blocked", "expired",
        "expiration_no_opportunity", "expiration_despite_opportunity",
    )
    pooled_intent_outcomes = {
        field: sum(run["metrics"]["intents"][field] for run in runs)
        for field in intent_outcome_fields
    }
    pooled_ended_intents = sum(
        pooled_intent_outcomes[field]
        for field in ("succeeded", "failed", "superseded", "blocked", "expired")
    )
    opportunity_counts = {
        "applicable_interactions": sum(
            run["metrics"]["intent_followthrough"]["intent_action_opportunities"]
            for run in runs
        ),
        "compatible_actions": sum(
            run["metrics"]["intent_followthrough"]["compatible_actions"]
            for run in runs
        ),
        "target_agent_opportunities": sum(
            run["metrics"]["intent_followthrough"]["target_agent_opportunities"]
            for run in runs
        ),
        "target_agent_matches": sum(
            run["metrics"]["intent_followthrough"]["target_agent_matches"]
            for run in runs
        ),
        "target_agent_unavailable": sum(
            run["metrics"]["intent_followthrough"]["target_agent_unavailable"]
            for run in runs
        ),
        "target_location_opportunities": sum(
            run["metrics"]["intent_followthrough"]["target_location_opportunities"]
            for run in runs
        ),
        "target_location_matches": sum(
            run["metrics"]["intent_followthrough"]["target_location_matches"]
            for run in runs
        ),
    }

    return {
        "run_count": len(runs),
        "kpis": kpis,
        "quality_checks": checks,
        "pooled_action_counts": dict(sorted(pooled_actions.items())),
        "pooled_action_rates": {
            action: safe_rate(count, total_actions)
            for action, count in sorted(pooled_actions.items())
        },
        "reputation": {
            field: {
                "mean": fmean(
                    run["metrics"]["reputation"][field] for run in runs
                ) if runs else 0.0,
                "values": [
                    run["metrics"]["reputation"][field] for run in runs
                ],
            }
            for field in reputation_fields
        },
        "goals": {
            "pooled": {
                **pooled_goal_counts,
                "attainment_rate": safe_rate(
                    pooled_goal_counts["achieved"], pooled_terminal
                ),
                "opportunity_progress_rate": safe_rate(
                    pooled_goal_counts["opportunities_that_produced_progress"],
                    pooled_goal_counts["applicable_progress_opportunities"],
                ),
            },
            "mean_per_seed": {
                field: fmean(run["metrics"]["goals"][field] for run in runs)
                if runs else 0.0
                for field in (*goal_count_fields, "attainment_rate", "average_progress",
                              "average_time_to_achievement", "opportunity_progress_rate")
            },
        },
        "intents": {
            "pooled_outcomes": pooled_intent_outcomes,
            "pooled_outcome_rates": {
                field: safe_rate(pooled_intent_outcomes[field], pooled_ended_intents)
                for field in ("succeeded", "failed", "superseded", "blocked", "expired")
            },
            "mean_per_seed": {
                field: fmean(run["metrics"]["intents"][field] for run in runs)
                if runs else 0.0
                for field in (*intent_outcome_fields, "average_intents_per_goal",
                              "average_tactical_progress")
            },
            "mean_per_seed_outcome_rates": {
                field: fmean(
                    run["metrics"]["intents"]["outcome_rates"][field]
                    for run in runs
                ) if runs else 0.0
                for field in ("succeeded", "failed", "superseded", "blocked", "expired")
            },
        },
        "opportunities": {
            "pooled_counts": opportunity_counts,
            "pooled_rates": {
                "action_compatibility_rate": safe_rate(
                    opportunity_counts["compatible_actions"],
                    opportunity_counts["applicable_interactions"],
                ),
                "target_agent_rate": safe_rate(
                    opportunity_counts["target_agent_matches"],
                    opportunity_counts["target_agent_opportunities"],
                ),
                "target_location_rate": safe_rate(
                    opportunity_counts["target_location_matches"],
                    opportunity_counts["target_location_opportunities"],
                ),
            },
            "mean_per_seed_rates": {
                field: fmean(
                    run["metrics"]["intent_followthrough"][field]
                    for run in runs
                ) if runs else 0.0
                for field in (
                    "action_compatibility_rate", "target_agent_rate",
                    "target_location_rate",
                )
            },
        },
    }
