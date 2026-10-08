"""Read-only V7 inspection of persisted authoritative histories.

This module intentionally consumes plain JSON snapshots, never engine objects.
A report is an observation, not an authority or a persistence input.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from src.analysis.inspection_save import load_save as _load, records as _records, check_versions, bounded_report
from src.analysis.inspection_records import (
    SCHEMA_VERSION, SOURCES, ALLOWED_FIELDS as ALLOWED_FIELDS, TEXT_FIELDS as TEXT_FIELDS,
    safe_fields as _safe_fields,
    chronology, safe_identity,
)

def _event(source: str, index: int, row: dict) -> dict:
    fields = _safe_fields(row)
    # Use a source-local ordinal to prevent ID collisions and preserve replay
    # identity across independently loaded copies of the same save.
    identity = f"{source}:{index:08d}"
    day, hour = chronology(fields)
    return {
        "id": identity,
        "authority_id": fields.get("id"),
        "source": source,
        "provenance": "authoritative_history",
        "day": day if type(day) is int else None,
        "hour": hour if type(hour) is int else None,
        "fields": fields,
    }

def _order(event: dict) -> tuple:
    return (event["day"] if event["day"] is not None else -1,
            event["hour"] if event["hour"] is not None else -1,
            event["source"], event["id"])


def timeline(source: str | Path | dict, *, limit: int = 100,
             offset: int = 0, kinds: set[str] | None = None) -> dict:
    """Chronological bounded event window; ties are stable, not causal claims."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be 1..1000")
    if type(offset) is not int or offset < 0:
        raise ValueError("offset must be nonnegative")
    save = _load(source)
    check_versions(save)
    selected = SOURCES.keys() if kinds is None else sorted(kinds)
    unknown = set(selected) - SOURCES.keys()
    if unknown:
        raise ValueError("unknown inspection source")
    entries = [
        _event(kind, index, row)
        for kind in selected
        for index, row in enumerate(_records(save, SOURCES[kind]))
        if isinstance(row, dict)
    ]
    entries.sort(key=_order)
    return bounded_report({
        "schema_version": SCHEMA_VERSION,
        "kind": "timeline",
        "total": len(entries),
        "offset": offset,
        "limit": limit,
        "events": entries[offset:offset + limit],
        "ordering_note": "Same-time records have stable presentation order, not proven causal order.",
    })

def inspect(source: str | Path | dict, *, scope: str = "world",
            identity: str | None = None, limit: int = 100) -> dict:
    """Inspect public authority records without exposing private resident state.

    The evidence links are *co-occurrences of exact identifiers*, never
    inferred causal edges. Absence does not prove an event did not happen.
    """
    if scope not in {"world", "resident", "relationship", "institution", "economy"}:
        raise ValueError("unsupported inspection scope")
    if identity is not None and (not isinstance(identity, str) or not all(
        safe_identity(part) for part in identity.split(','))):
        raise ValueError("invalid inspection identity")
    if scope in {"resident", "relationship", "institution"} and not identity:
        raise ValueError("identity required for this scope")
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
    check_versions(save)
    events = [_event(kind, index, row) for kind in sorted(kinds)
              for index, row in enumerate(_records(save, SOURCES[kind]))]
    events.sort(key=_order)
    if identity:
        # Exact identifier membership only; no textual substring queries.
        ids = set(identity.split(",")) if scope == "relationship" else {identity}
        events = [e for e in events if any(
            (value in ids if isinstance(value, str) else
             any(v in ids for v in value) if isinstance(value, list) else False)
            for key, value in e["fields"].items()
            if key == 'id' or key.endswith(('_id', '_ids')) or key in {'event_key', 'execution_key'}
        )]
    return bounded_report({
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
    })

def compare(left: str | Path | dict, right: str | Path | dict) -> dict:
    """Compare authoritative event projections, not stochastic dialogue."""
    a, b = _load(left), _load(right)
    check_versions(a)
    check_versions(b)
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
    return bounded_report({
        "schema_version": SCHEMA_VERSION,
        "kind": "comparison",
        "sources": {
            k: {"left": x[k]["count"], "right": y[k]["count"],
                "delta": y[k]["count"] - x[k]["count"],
                "same_projection": x[k]["sha256"] == y[k]["sha256"]}
            for k in sorted(SOURCES)
        },
        "note": "Equality compares allowlisted history projections, not full saved world states.",
    })
