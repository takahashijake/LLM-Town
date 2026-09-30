# V4 bounded goal-planning freeze candidate

## Architectural contract

V4 coordinates one durable goal through one persistent, bounded plan. It is a
closed-registry extension of the existing intent and world systems, not a general
planner:

```text
durable Goal
    -> persistent owner/goal-scoped GoalPlan
    -> finite registered strategy
    -> bounded authoritative prerequisites or one delegated V3 commitment
    -> existing world authority performs the action
    -> authoritative execution evidence
    -> strict current-revision provenance validation
    -> exactly-once Goal progress
    -> adapt, complete, or block without inventing state
```

The governing rule remains: the LLM may propose or realize behavior;
deterministic code validates it; existing authoritative systems mutate world
state; and authoritative evidence proves the result. Generated text cannot
change money, inventory, ownership, events, commitments, plan revisions, or goal
progress.

## What V4 Phases 1–6 provide

Phase 1 binds a durable `Goal` to one stable
`plan:goal:<owner-id>:<goal-id>` identity. Expired intents may be replaced, but
the plan is not duplicated. Phase 2 assigns every finite strategy an immutable
execution contract and rejects merely arriving, speaking, remembering, or
selecting an intent as proof. Phase 3 adds the current-event prerequisite. Phase
4 adds the fixed `reference_book` ownership and authorized-purchase path. Phase 5
permits an ordered conjunction of at most two registered prerequisites and
stages at most one preparation mutation per decision. Phase 6 adds exactly one
delegation strategy, `request_research_help`, whose result is proven by a normal
helper-owned V3 `help` commitment.

These phases collectively provide persistence, finite strategy selection,
authoritative dependency refresh, fixed resource preparation, bounded composite
execution, revision, and one commitment-backed cross-agent outcome. The phase
evaluators establish each vertical slice. The whole-V4 evaluator adds the
previously missing joint proof that those slices preserve their contracts when
they share a world and lifecycle.

## State and authority boundaries

- `Goal` is the durable desired outcome and the only owner of progress and
  completion.
- `GoalPlan` is bounded persistent coordination and audit state. It selects a
  registered strategy but cannot perform effects or add progress.
- `Intent` is a short-lived attempt bound to the plan ID and current revision.
- An activity, validated social action, material exchange, or V3 commitment
  execution is the actual behavior.
- Goal evidence is accepted only after the exact world proof and provenance
  match the active plan revision. The plan then mirrors that already-accepted
  evidence.

Choosing a strategy, creating an intent, reaching a place, mentioning success in
dialogue, or storing a success claim in memory is never execution. Unknown
strategies, dependency kinds, actions, and future schema versions fail closed.

## Resources and composite prerequisites

The resource path is intentionally fixed. `study_reference_material` and
`study_reference_material_at_active_location` require the configured
`reference_book`. When the owner lacks it, `MaterialSystem` may expose a route
only if the configured seller is active, has a location and stock, the good has
a configured price, and the owner has sufficient funds. The existing atomic
purchase authority moves money and a real material lot once. Purchase satisfies
only the prerequisite; a later exact study activity is still required for goal
progress.

The composite strategy additionally requires a current `DailyEvent` at the
selected knowledge location. Inventory and event requirements are recomputed
from live authority before selection and proof acceptance. Persisted
`satisfied` labels, another resident's book, another good, an old event, or a
book lost before final execution cannot substitute. Preparation never chains
into final execution in the same decision, and an event disappearing after a
purchase returns the strategy to waiting.

## Delegation semantics

`request_research_help` binds one requester, one deterministic helper, the fixed
`goal_research_help` task code, one registered location, one stable request ID,
and the current goal-plan revision. Dialogue acceptance creates an ordinary V3
`help` commitment in which the helper is the obligated owner. Normal V3 planning
and activity arbitration must select the helper's `commitment_help` action.

The request, response, acceptance, and commitment-plan creation all produce zero
goal progress. Fulfillment credits the requester only when the current binding,
commitment participants, type, task, location, status, commitment ID, execution
record, and commitment evidence all match. Unrelated help, another helper, wrong
terms, a forged fulfilled label, or a terminal nonfulfillment gives no progress.
A superseded commitment may still complete as a legitimate V3 outcome, including
its normal relationship, reputation, and memory consequences, but it cannot
credit a newer goal-plan revision. Goal consumption never reapplies those V3
social consequences.

## Revision, persistence, and replay

Adaptation retains the plan ID and all prior goal progress, increments the
revision deterministically, replaces dependencies and delegation bindings with
revision-scoped state, and supersedes the old intent. Old intent, dependency,
activity, and delegation proof cannot cross-credit. At most three adaptations
are permitted; the next request blocks the plan with
`adaptation_budget_exhausted`, preventing an infinite replan loop.

Save/resume preserves stable plan, request, commitment, and execution identities.
It reconstructs opportunities from current authority rather than trusting
serialized feasibility. Stable event and evidence keys make purchase,
commitment execution, goal progress, and social-consequence consumption
idempotent. Terminal goals synchronize to terminal plans and never silently
reactivate.

## Integrated freeze evaluation

Run the model-free acceptance layer with:

```bash
python scripts/evaluate_v4_freeze.py
```

The CLI returns nonzero on any failure and reports named scenarios, invariants,
and diagnostics. The evaluation uses real `SimulationEngine` instances,
`FakeLLMClient`, isolated global randomness, and ordinary system paths wherever
practical. It does not call the six phase evaluators and aggregate their results.

Its strongest shared-world lifecycle keeps two independent durable goals active
while one owner:

1. creates and resumes one stable composite goal plan;
2. performs a real atomic book purchase without receiving progress;
3. resumes, observes a real current event, and performs exact composite study;
4. adapts without losing progress to `request_research_help`;
5. creates one dialogue-backed ordinary V3 help commitment;
6. lets the helper's normal commitment arbitration preempt the helper's separate
   goal intent and execute `commitment_help`;
7. consumes exact fulfillment once without duplicating social consequences;
8. adapts to another registered direct strategy and completes from its exact
   authoritative activity; and
9. remains stable through a 30-day projection.

Separate controlled attack worlds prevent deliberate corruptions from polluting
that lifecycle. Coverage includes four save boundaries; intent expiration;
current inventory/event rechecks; missing seller, stock, price, and funds;
resource loss; event replacement; terminal delegation and bounded recovery;
stale-revision V3 fulfillment; real batched conversation ordering; independent
concurrent goals; duplicate purchase, execution, and goal-evidence keys; and
wrong owner, source goal, plan, revision, intent, strategy, activity, helper,
commitment, task, location, resource, and event provenance.

Freeze-level checks reuse plan, commitment, material, economy, and outcome-memory
validators. They additionally aggregate contract registration, owner/goal-scoped
IDs, current active source bindings, evidence mirroring and uniqueness, bounded
dependency/delegation/audit collections, and declared execution sources.

## Known limitations and future versions

V4 deliberately does **not** provide:

- arbitrary task decomposition;
- arbitrary dependency DAGs;
- general hierarchical planning;
- recursive delegation or delegation chains;
- multi-party commitments;
- teams or organizations;
- arbitrary plan-to-plan dependencies;
- model-authored authoritative steps;
- generalized markets; or
- pathfinding/navigation planning.

It also remains limited to one selected strategy per goal revision, at most two
ordered registered prerequisites, one fixed purchasable resource path, and one
fixed one-helper delegation strategy. Bounded collaborative plans,
plan-to-plan dependencies, limited recursive decomposition, and
organization-level coordination are possible post-V4 directions, not implied V4
capabilities.
