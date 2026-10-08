"""Read-only V7 inspection of persisted authoritative histories.

This module intentionally consumes plain JSON snapshots, never engine objects.
A report is an observation, not an authority or a persistence input.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
# Only explicitly admitted authoritative collections are inspected. No agent
# memory, journal, prompt, dialogue, belief or LLM proposal text enters reports.
SOURCES = {
    "relationship_events": ("relationship_events",),
    "reputation_updates": ("reputation_updates",),
    "ledger": ("economy", "transactions"),
    "employment": ("economy", "employments"),
    "exchanges": ("materials", "exchanges"),
    "inventory_transfers": ("materials", "inventory_transfers"),
    "production": ("materials", "production_records"),
    "consumption": ("materials", "consumptions"),
    "lot_movements": ("materials", "lot_movements"),
    "migrations": ("town_growth", "migration_records"),
    "locations": ("location_growth", "activation_records"),
    "occurrences": ("event_ecology", "occurrence_records"),
    "institutions": ("institution_growth", "formation_records"),
    "commerce": ("commerce_growth", "activation_records"),
    "commitments": ("commitments", "commitments"),
    "plans": ("plans", "plans"),
}
# Exclude free-text and nested belief fields, even if they appear on an
# authoritative record. Relationships among events use exact matching IDs.
ALLOWED_FIELDS = frozenset({
    "id", "day", "hour", "tick", "sequence", "status", "event_key",
    "agent_id", "resident_id", "actor_id", "owner_id", "target_id",
    "source_id", "destination_id", "from_id", "to_id", "account_id",
    "from_account_id", "to_account_id", "sender_id", "receiver_id",
    "inventory_id", "from_inventory_id", "to_inventory_id",
    "lot_id", "lot_ids", "input_lot_ids", "output_lot_ids",
    "production_id", "transaction_id", "purchase_id", "exchange_id",
    "formation_id", "institution_id", "employment_id", "commitment_id",
    "plan_id", "goal_id", "location_id", "template_id", "recipe_id",
    "commerce_id", "seller_id", "goods_id", "good_id", "quantity",
    "amount", "price", "balance", "delta", "score_before", "score_after",
    "relationship_delta", "type", "kind", "action", "outcome",
    "reason_code", "activity_id", "event_id", "occurrence_id",
    "migration_id", "activation_id", "reference_id", "record_id",
    "payer_account_id", "payee_account_id", "counterparty_id",
})
# These fields can contain prose even on authoritative rows and are never emitted.
TEXT_FIELDS = frozenset({"reason", "description", "text", "summary", "name", "content", "dialogue", "metadata"})

def _load(source: str | Path | dict) -> dict:
    if isinstance(source, dict):
        return source
    with open(source, encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("simulation save must be a JSON object")
    return value

def _records(save: dict, path: tuple[str, ...]) -> list:
    node: Any = save
    for key in path:
        if not isinstance(node, dict):
            return []
        node = node.get(key)
    return node if isinstance(node, list) else []

def _safe_fields(row: dict) -> dict:
    result = {}
    for key in sorted(ALLOWED_FIELDS - TEXT_FIELDS):
        value = row.get(key)
        if type(value) in (str, int, float, bool) or value is None:
            if key in row:
                result[key] = value
        elif isinstance(value, (tuple, list)) and len(value) <= 64 and all(
            type(x) in (str, int, float, bool) for x in value
        ):
            result[key] = list(value)
    return result

def _event(source: str, index: int, row: dict) -> dict:
    fields = _safe_fields(row)
    # Use a source-local ordinal to prevent ID collisions and preserve replay
    # identity across independently loaded copies of the same save.
    identity = f"{source}:{index:08d}"
    day = fields.get("day")
    hour = fields.get("hour")
    return {
        "id": identity,
        "authority_id": fields.get("id"),
        "source": source,
        "provenance": "authoritative_history",
        "day": day if type(day) is int else None,
        "hour": hour if type(hour) is int else None,
        "fields": fields,
    }

def timeline(source: str | Path | dict, *, limit: int = 100,
             offset: int = 0, kinds: set[str] | None = None) -> dict:
    """Chronological bounded event window; ties are stable, not causal claims."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be 1..1000")
    if type(offset) is not int or offset < 0:
        raise ValueError("offset must be nonnegative")
    save = _load(source)
    selected = SOURCES.keys() if kinds is None else sorted(kinds)
    unknown = set(selected) - SOURCES.keys()
    if unknown:
        raise ValueError(f"unknown sources: {sorted(unknown)}")
    entries = [
        _event(kind, index, row)
        for kind in selected
        for index, row in enumerate(_records(save, SOURCES[kind]))
        if isinstance(row, dict)
    ]
    entries.sort(key=lambda e: (
        e["day"] if e["day"] is not None else -1,
        e["hour"] if e["hour"] is not None else -1,
        e["source"], e["id"],
    ))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "timeline",
        "total": len(entries),
        "offset": offset,
        "limit": limit,
        "events": entries[offset:offset + limit],
        "ordering_note": "Same-time records have stable presentation order, not proven causal order.",
    }

def inspect(source: str | Path | dict, *, scope: str = "world",
            identity: str | None = None, limit: int = 100) -> dict:
    """Inspect public authority records without exposing private resident state.

    The evidence links are *co-occurrences of exact identifiers*, never
    inferred causal edges. Absence does not prove an event did not happen.
    """
    if scope not in {"world", "resident", "relationship", "institution", "economy"}:
        raise ValueError("unsupported inspection scope")
    if scope in {"resident", "relationship", "institution"} and not identity:
        raise ValueError("identity required for this scope")
    data = timeline(source, limit=1000)
    # Recompute bounded projection for each view; saves are finite under the
    # system's configured limits, while the output is independently capped.
    save = _load(source)
    counts = {k: len(_records(save, path)) for k, path in SOURCES.items()}
    if scope == "economy":
        kinds = {"ledger", "employment", "exchanges", "inventory_transfers",
                 "production", "consumption", "lot_movements", "commerce"}
    elif scope == "institution":
        kinds = {"institutions", "commerce", "employment", "ledger", "production"}
    elif scope == "relationship":
        kinds = {"relationship_events", "reputation_updates", "commitments"}
    elif scope == "resident":
        kinds = set(SOURCES)
    else:
        kinds = set(SOURCES)
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be 1..1000")
    events = timeline(save, limit=1000, kinds=kinds)["events"]
    if identity:
        # Exact identifier membership only; no textual substring queries.
        ids = set(identity.split(",")) if scope == "relationship" else {identity}
        events = [e for e in events if any(
            (value in ids if isinstance(value, str) else
             any(v in ids for v in value) if isinstance(value, list) else False)
            for value in e["fields"].values()
        )]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "inspection",
        "scope": scope,
        "identity": identity,
        "counts": counts if scope == "world" else {k: counts[k] for k in sorted(kinds)},
        "matched": len(events),
        "events": events[:limit],
        "truncated": len(events) > limit,
        "evidence_policy": {
            "records": "authoritative history projection",
            "links": "exact identifier co-occurrence only; causation unproven",
            "resident_knowledge": "not inspected or disclosed",
            "llm_text": "excluded",
            "missing_evidence": "unknown, not evidence of absence",
        },
    }

def compare(left: str | Path | dict, right: str | Path | dict) -> dict:
    """Compare authoritative event projections, not stochastic dialogue."""
    a, b = _load(left), _load(right)
    def signatures(save: dict) -> dict:
        result = {}
        for kind, path in SOURCES.items():
            rows = [_safe_fields(row) for row in _records(save, path)
                    if isinstance(row, dict)]
            payload = json.dumps(rows, sort_keys=True, separators=(",", ":"))
            result[kind] = {"count": len(rows),
                            "sha256": sha256(payload.encode()).hexdigest()}
        return result
    x, y = signatures(a), signatures(b)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "comparison",
        "sources": {
            k: {"left": x[k]["count"], "right": y[k]["count"],
                "delta": y[k]["count"] - x[k]["count"],
                "same_projection": x[k]["sha256"] == y[k]["sha256"]}
            for k in sorted(SOURCES)
        },
        "note": "Equality compares allowlisted history projections, not full saved world states.",
    }
