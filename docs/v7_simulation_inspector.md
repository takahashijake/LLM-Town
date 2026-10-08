# V7 simulation inspector — initial read-only evidence projection

This first increment exposes a versioned (`schema_version: 1`) JSON report
built from existing saved histories. It neither loads an LLM nor reconstructs
the live engine. It never writes to a save, runs an event, or mutates world state.

## Quickstart

After producing a save with the existing engine:

```bash
python scripts/inspect_town.py timeline data/save_state.json --limit 25
python scripts/inspect_town.py timeline data/save_state.json --source ledger
python scripts/inspect_town.py show data/save_state.json world
python scripts/inspect_town.py show data/save_state.json resident --id resident-1
python scripts/inspect_town.py show data/save_state.json institution --id garden
python scripts/inspect_town.py show data/save_state.json economy
python scripts/inspect_town.py compare before.json after.json
```

An event is labeled `authoritative_history` because its source collection
is an existing deterministic system's persisted record. Its inspector ID is a
stable source-local ordinal. The embedded `authority_id` is the original
authoritative ID where one is present. Same-timestamp ordering is **not** a
proof that one event caused another; records that share identifiers are only
linked by exact identity, not speculative causality.

Private memories, beliefs, journals, social prompts, transcript text, and raw
LLM proposals are excluded entirely. The reporting whitelist also omits
narrative fields from otherwise authoritative rows. An absent record is **not**
proof that the event never occurred; some histories are intentionally bounded.
This is an operator-facing read-only audit view, not an authenticated interface.

The output is bounded at 1,000 events per view; timeline supports offset
pagination. The comparison reports history counts and digest equality over
allowlisted fields, not full-state equivalence.

## Planned next increments

This implementation does not yet prove directed causal dependencies,
institution formation chains, end-to-end lot lineage, cross-run trajectories,
or resident-observed knowledge. These require verified typed references and
explicit disclosure controls, not inference from prose. It also does not
replace the V6 freeze evaluator or claim to validate corrupted saves.

Regression invocation:

```bash
python -m pytest tests/analysis/test_simulation_inspector.py -q
python scripts/evaluate_v6_freeze.py
```
