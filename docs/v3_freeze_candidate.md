# V3 bounded social-planning freeze candidate

## Contract

V3 social planning is deliberately not a general planner. One accepted concrete
commitment can own at most one persistent plan selected from three templates:

| Commitment | Required stored terms | Registered steps |
| --- | --- | --- |
| `help` | task, valid location, due day/tick | `commitment_help` |
| `meet` | valid location, due day/tick | `commitment_meet` |
| `transfer` | existing transfer terms | optional `commitment_acquire_resource`, then `commitment_transfer` |

The help and meet templates never infer a task, place, counterpart, or time. An
accepted but underspecified source gets a persisted planning decision with a
stable no-plan reason and continues through the narrower commitment opportunity
path. Transfer behavior remains the regression reference: acquisition exists only
when current authoritative inventory, seller stock, price, and balance checks
find a legal route. Delivery requires real owned stock and preserves material-lot
provenance.

The commitment recognizer retains a help location only when the proposal names a
registered place explicitly (for example, “at the cafe”). It never substitutes
the conversation location. This lets concrete dialogue-originated help promises
enter the same template while vague help remains unplanned.

Plans nominate ordinary registered activities. The activity, commitment,
material, and economy systems make all world mutations. A plan step cannot edit
money, inventory, ownership, commitment/relationship/reputation state, memory,
crime/evidence, or justice state. It advances only after a matching authoritative
commitment execution or preparation record exists.

## Identity and lifecycle

New plan IDs are `plan:commitment:<owner-id>:<commitment-id>`. Step IDs append a
stable ordinal and action type. Neither uses Python `hash()`. Execution records
bind plan, step, source commitment, action type, and authoritative execution key.
Replayed keys, cross-source proof, wrong action types, and terminal plans are
no-ops.

Cancellation, expiry, failure, and fulfillment deterministically terminalize the
associated plan when the plan system next synchronizes. Terminal plans are never
recreated. A bounded plan failure also marks an accepted source commitment failed,
so it cannot later succeed. Temporary help/meeting infeasibility stays pending;
deduplicated scheduler observations do not become memories. Transfer acquisition
keeps its three-attempt bounded failure policy.

## Knowledge and dialogue

Commitment acceptance and terminal outcomes are projected to the two participants
with owner, source system/record, event type, knowledge basis, event day,
counterpart, and polarity. Plan creation, completion, acquisition preparation,
and internal failure remain actor-private. Uninvolved residents receive neither
commitment truth nor private plan mechanics. Deterministic memory IDs make replay
and save/resume projection idempotent. Memory remains downstream knowledge and
has no route back into plan or commitment authority.

Pair-private conversation context exposes commitment status and only a coarse plan
stage: pending, preparing, terminal, or unsupported. Active repair successors are
identified as such to the same two participants, and their accepted/fulfilled
memories retain repair-specific event provenance. Context does not expose
plan/step IDs or private failure reasons. Grounding distinguishes accepted/pending,
preparing, repair-successor-active, fulfilled, failed, expired, and cancelled
states. Generated claims are evidence text only; false fulfillment is rejected or
safely replaced under the existing one-repair-then-fallback policy.

## Snapshot, batching, and persistence

Planning adds no capability to conversation replicas. Social ticks still use one
immutable snapshot, deterministic disjoint scheduling, private session state,
turn-wave batching, row-local validation/repair, a full realization barrier, and
stable schedule-order commit. Consequential proposals are revalidated by the
existing ordered authoritative commit path. Batch membership does not share
knowledge, and workers cannot access plan, economy, crime, justice, persistence,
or activity mutation authorities.

Plan persistence is schema version 2. Version 1/unversioned documents load with
empty planning-decision records and preserve existing plan IDs. Missing optional
fields get dataclass defaults. Unknown schema versions or unknown step actions
fail closed. Saves contain plans, decisions, transitions, and execution proofs,
not snapshots, workers, futures, model tensors, private replicas, or batch state.

## Freeze evaluation and limitations

Run the model-free acceptance suite with:

```bash
python scripts/evaluate_v3_freeze.py
```

It covers 25 scenarios: transfer acquisition/delivery, concrete and vague help and
meet, explicit dialogue-originated help, temporary blocking, all terminal states,
proof replay/source isolation, before/after save-resume, knowledge routing and
authority independence, pending/preparing/repair-successor lifecycle grounding
and outcomes, false claims, batched snapshot/commit invariants, longitudinal
retention, and old-save loading. It reports scenario and invariant counts with
named diagnostics and returns nonzero on failure.

No post-change live-model run is required for correctness. Existing Qwen2.5 3B
and 7B configurations remain honestly classified as safe-degraded support because
their frozen repair/fallback rates do not meet the full-quality envelope. V3 does
not loosen those thresholds and does not add navigation, arbitrary decomposition,
multi-party planning, or model-authored authoritative steps.
