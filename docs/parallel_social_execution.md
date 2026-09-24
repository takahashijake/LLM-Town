# Deterministic parallel social execution

Conversation ticks use a plan → realize → barrier → commit architecture.

```text
authoritative state after activities
              |
              v
 immutable social tick snapshot
              |
              v
 deterministic disjoint scheduler
       /             \
 session realization  session realization
 (private replica)     (private replica)
       \             /
        result barrier
              |
              v
 schedule-ordered authoritative commit
              |
              v
 memory, logs, and next-tick visibility
```

`ConversationTickSnapshot` gives every planned session the same versioned tick
identity and stable participant/location view. `ConversationScheduler` sorts
inputs, derives local seeds with SHA-256, and pairs residents without replacement.
It can therefore schedule every disjoint pair at a location and cannot double
book a resident.

Realization runs against a private, pre-commit copy of conversation-visible
state. Economy, crime, justice, plans, persistence, activity machinery, loggers,
and effect appliers are removed from that view. A worker can build each speaker's
private context, invoke parsing and grounding validation, repair once, and create
turn records, but it cannot mutate the live town. The serial backend is the
reference implementation. The concurrent backend uses a bounded thread pool and
collects all results before any commit. Worker completion order is discarded;
results commit by `schedule_index`.

Simultaneous means **the same authoritative snapshot and independent
realization**, not unsynchronized concurrent mutation of world state. Commit-time
relationship, reputation, intent, commitment, memory, rate-cap, and logging rules
remain deterministic authorities. A failed worker becomes a diagnostic result
and cannot leave a partial world update.

Simulation concurrency and GPU generation concurrency are different. The local
Transformers client protects its tokenizer/model generation and mutable
diagnostics with a lock because thread safety is not guaranteed. Concurrent mode
therefore establishes correct independent sessions and can overlap thread-safe
clients or remote requests, but a single local Transformers model may still
serialize generation. True GPU throughput improvement requires deterministic
model batching or a serving backend; neither is claimed here.

Per-session request seeds are derived from the simulation seed, day, hour,
session ID, turn, and attempt using SHA-256 rather than Python's randomized
`hash()`. The current runner exposes the session seed in context and telemetry.
Ephemeral snapshots, replicas, pools, and futures are never saved. Saves occur
after the tick barrier through the existing simulation loop, while committed
authoritative records continue through the existing schema.

The tick order remains:

1. expire due commitments;
2. execute deterministic activities and activity intent effects;
3. snapshot, schedule, realize, barrier, and commit conversations;
4. maintain memories;
5. decay and synchronize relationships;
6. save at the existing safe tick boundary.

Grounded-dialogue authority is unchanged. The engine still owns applicability,
reference, polarity, counterpart, knowledge basis, permitted fact, intent, and
follow-through eligibility. Model metadata remains advisory, validation scores
surface meaning, and recovery remains one bounded repair followed by fallback.
Capability tiers remain explicit; no model-name promotion occurs.

