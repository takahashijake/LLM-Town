# Deterministic parallel social execution

Conversation ticks use a plan → realize → barrier → commit architecture. The
batched realization backend advances all active private sessions in turn waves.

```text
authoritative state after activities
              |
              v
 immutable social tick snapshot
              |
              v
 deterministic disjoint scheduler
              |
              v
       private session states
              |
              v
 collect one ready turn per active session
              |
              v
  bounded padded generation batch
              |
              v
 per-row validation and selective repair batch
              |
              v
       next turn wave
              |
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
and effect appliers are removed from that view. A realization state can build each
speaker's private context, invoke parsing and grounding validation, repair once,
and create turn records, but it cannot mutate the live town. All backends use the
same per-turn semantic state machine.

The three explicit modes have different computational behavior:

- `serial` is the reference and completes private sessions one at a time;
- `concurrent` uses `--conversation-workers` bounded threads for whole private
  sessions, while a shared local Transformers client still locks each model call;
- `batched` uses `--conversation-batch-size` to collect one ready request from
  each active session, tokenize those requests as one left-padded tensor batch,
  and invoke `model.generate()` once per bounded batch.

Sessions that close early are absent from later waves. Parsing, grounding,
engine-plan surface validation, commitment-state validation, anti-echo handling,
action inference, outcome resolution, and termination remain row-local. If one
row needs recovery, only qualifying rows enter the corresponding repair sub-batch;
valid rows are never regenerated. Recovery remains bounded to the existing one
repair followed by deterministic safe fallback.

Simultaneous means **the same authoritative snapshot and independent
realization**, not unsynchronized concurrent mutation of world state. Commit-time
relationship, reputation, intent, commitment, memory, rate-cap, and logging rules
remain deterministic authorities. A failed worker becomes a diagnostic result
and cannot leave a partial world update.

Simulation concurrency and GPU generation concurrency remain different.
`concurrent` may overlap thread-safe clients or remote requests but does not batch
a single local model. `batched` performs actual tensor batching inside one
explicitly controlled, lock-protected local-model call; it does not remove the
generation lock or invoke mutable model state concurrently. Model weights load
once and remain shared. A client without `generate_conversation_batch(requests)`
is rejected clearly when batched mode is selected rather than silently degraded.

Decoder-only prompts are left-padded. Generated tokens are decoded after the
common input tensor boundary, while attention-mask sums retain each row's true
prompt-token length for diagnostics. Rows are always demultiplexed by immutable
request ID, never return position or completion timing.

Every request ID and seed includes simulation seed, day, hour, session ID,
schedule index, turn index, generation attempt, and request kind. Both use SHA-256
rather than Python's randomized `hash()`. Request kinds distinguish primary,
grounding repair/retry, commitment repair, and anti-echo generation.

Transformers 5.17 does not expose a supported per-row `generator` parameter on
the installed `generate()` API. Batched sampling therefore derives one batch RNG
seed from the ordered immutable row seeds while holding the generation lock. The
reproducibility contract is the same repository revision, model/runtime versions,
hardware class, simulation seed, schedule, generation configuration, and batch
size/composition. Changing batch size may change stochastic text. Serial and
batched stochastic transcripts are not promised to be bitwise identical; the
invariants across backends are deterministic authority, isolation, safety, and
ordered commit.

Ephemeral snapshots, replicas, pools, and futures are never saved. Saves occur
after the tick barrier through the existing simulation loop, while committed
authoritative records continue through the existing schema.

Tick telemetry includes backend, snapshot and schedule identity, active sessions
per wave, batch count and sizes, request successes/failures, repair batches,
fallbacks, generation time, tokens and throughput, and ordered commit. A real
Transformers client also reports model name, device, dtype, runtime versions, and
peak CUDA allocation. Timing and performance fields are diagnostic only and are
never simulation inputs.

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

Run the model-free architectural acceptance evaluator with:

```bash
python scripts/evaluate_batched_social.py
```

The opt-in real-model benchmark never downloads weights and skips cleanly when
CUDA or the requested cached model is unavailable:

```bash
python scripts/benchmark_batched_local_llm.py \
  --model Qwen/Qwen2.5-3B-Instruct \
  --batch-sizes 2 4 8 16 \
  --output outputs/batched_local_llm_benchmark.json
```
