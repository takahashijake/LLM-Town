"""Inspect long-run save files for bounded causal-memory invariants."""

import json
from pathlib import Path


def analyze_stress_state(path: str | Path) -> dict:
    path = Path(path)
    state = json.loads(path.read_text())
    agents = state["agents"]
    memories = [m for a in agents for m in a.get("memory", []) + a.get("memory_archive", [])]
    causal = [m for m in memories if m.get("causal")]
    owner_duplicates = 0
    for agent in agents:
        ids = [m["id"] for m in agent.get("memory", []) + agent.get("memory_archive", [])]
        owner_duplicates += len(ids) - len(set(ids))
    commitments = (state.get("commitments") or {}).get("commitments", [])
    plans = (state.get("plans") or {}).get("plans", [])
    incidents = (state.get("crime") or {}).get("incidents", [])
    evidence = (state.get("crime") or {}).get("evidence", [])
    adjudications = (state.get("justice") or {}).get("adjudications", [])
    restitutions = (state.get("justice") or {}).get("restitutions", [])
    exchanges = (state.get("materials") or {}).get("exchanges", [])
    sources = {
        "commitments": {x["id"] for x in commitments},
        "plans": {x["id"] for x in plans},
        "crime": {x["id"] for x in incidents + evidence},
        "justice": {x["id"] for x in adjudications + restitutions},
        "materials": {x["id"] for x in exchanges},
    }
    relationship_values = list(state.get("relationship_scores", {}).values())
    reputation = [belief for agent in agents
                  for dimensions in agent.get("reputation_beliefs", {}).values()
                  for belief in dimensions.values()]
    checks = {
        "active_memory_bounded": all(len(a.get("memory", [])) <= 200 for a in agents),
        "archive_bounded": all(len(a.get("memory_archive", [])) <= 500 for a in agents),
        "owner_memory_ids_unique": owner_duplicates == 0,
        "causal_provenance_complete": all(
            all(m.get(k) for k in ("owner_id", "source_system", "source_id",
                                   "event_type", "knowledge_basis")) for m in causal
        ),
        "causal_sources_reconstructable": all(
            m.get("source_id") in sources.get(m.get("source_system"), set())
            for m in causal
        ),
        "relationship_bounds": all(-10 <= value <= 10 for value in relationship_values),
        "reputation_bounds": all(
            -10 <= belief.get("score", 0) <= 10
            and 0 <= belief.get("confidence", 0) <= 1 for belief in reputation
        ),
    }
    return {
        "path": str(path), "state_bytes": path.stat().st_size,
        "active_memories": [len(a.get("memory", [])) for a in agents],
        "archive_entries": [len(a.get("memory_archive", [])) for a in agents],
        "causal_memories": len(causal), "owner_duplicate_ids": owner_duplicates,
        "plans": {status: sum(x["status"] == status for x in plans)
                  for status in ("active", "completed", "failed", "abandoned")},
        "commitments": {status: sum(x["status"] == status for x in commitments)
                        for status in ("accepted", "fulfilled", "failed", "expired", "cancelled")},
        "crime_incidents": len(incidents), "adjudications": len(adjudications),
        "checks": checks, "passed": all(checks.values()),
    }


def analyze_stress_suite(paths) -> dict:
    runs = [analyze_stress_state(path) for path in paths]
    return {"runs": runs, "passed": all(run["passed"] for run in runs)}
