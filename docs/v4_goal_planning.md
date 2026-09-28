# V4 Phases 1–4: bounded goal planning and authoritative preparation

## Contract

Phase 1 makes one deterministic strategy for an active durable goal persist
across short-lived intents and save/resume. Phase 2 makes each strategy denote a
distinct, authoritatively provable behavior. Phase 3 gives strategies one optional
finite prerequisite checked against authoritative world state. These phases are
not a general planner; Phase 4 activates bounded preparation for exactly one
fixed resource-dependent knowledge strategy. They do not create free-form steps, facts, resources,
places, actions, dependencies, or goals.

```text
Goal (authoritative desired outcome)
  |
  v
GoalPlanner finite candidates and deterministic score
  |
  v
GoalPlan (persistent strategy and audit state)
  |
  v
Intent bound to plan + revision
  |
  +-----------------------------+
  |                             |
  v                             v
strategy-specific          exact registered
activity                   social action
  |                             |
  +-------------+---------------+
                v
       authoritative runtime record
                |
                v
       strategy contract validation
                |
                v
           Goal evidence
                |
                v
       GoalPlan mirrors evidence
```

The distinctions are deliberate:

- `Goal` is the durable desired outcome and remains the only authority for goal
  progress and completion.
- `GoalPlan` is persistent coordination state for the selected deterministic
  strategy. It cannot apply world effects or increment a goal.
- `Intent` is a short-lived attempt to pursue the current goal-plan revision.
- An activity or validated social action is actual attempted behavior.
- Existing deterministic systems own effects and produce evidence.
- Evidence is a stable, replay-protected record accepted by the existing goal
  path. The plan only mirrors it after it is present on the goal.
- The language model realizes surface dialogue. Its text is never execution
  proof and never mutates a goal plan.

## Identity, persistence, and bounded state

A goal-plan ID is derived only from immutable source identity:

```text
plan:goal:<owner-agent-id>:<goal-id>
```

`ensure_goal_plan()` returns the existing plan for a source goal and never
creates a second one. Strategy adaptation retains that ID and increments a
revision. Each generated intent records the plan ID and revision; an intent from
a superseded revision is terminalized before it can continue.

Plan schema version 5 supports Phase 4 resource dependency diagnostics. Versions
1 and 2 load with empty goal-plan fields; version 3 goal plans load without
fabricating dependencies, and version 4 retains its Phase 3 semantics. No
migration fabricates ownership, a seller route, or a resource dependency.
Version-2 commitment plans retain
their exact template, step, proof, and lifecycle behavior. Unknown future schema
versions and unknown goal strategy names fail closed.

A goal plan stores only bounded diagnostic state: source and owner IDs, strategy,
intent type, target agent/location, required action, feasibility and score at
selection, selected/review day, revision, lifecycle, at most 50 transitions, at
most 50 mirrored evidence records, at most 50 plan evidence keys, and at most 20
dependency transitions. Dependency state stores only kind, deterministic subject,
revision, status, last check, optional preparation activity, and authority
reference. It never
stores prompts, model output, whole memories, or context snapshots. Goals retain
up to 100 processed evidence keys as their authoritative replay guard.

## Lifecycle and adaptation

| Goal status | Goal-plan status | Execution contract |
| --- | --- | --- |
| `active` | `active` when safely plannable | May issue an intent for the current revision |
| `paused` | `paused` | Issues no new intent; may resume with the same plan |
| `achieved` | `completed` | Terminal; never reopens |
| `blocked` | `blocked` | Terminal; never reopens |
| `abandoned` | `abandoned` | Terminal; never reopens |

An active goal with no feasible candidate records one persisted
`no_feasible_strategy` planning decision and becomes blocked under the existing
goal contract. A selected candidate whose execution mapping is unsafe produces a
blocked plan with an explicit reason.

Adaptation reuses `GoalPlanner.should_adapt()`. A meaningful relationship,
reputation, hard-constraint, or target change can replace the strategy. The
transition records the day, trigger, old/new strategy, old/new target, preserved
goal progress, and revision. Progress is never reset. Autonomous adaptation is
limited to three revisions. A fourth request blocks the plan with
`adaptation_budget_exhausted`; the runtime then blocks the source goal instead of
spinning.

## Finite strategy execution contract

`GOAL_STRATEGY_EXECUTION_CONTRACTS` is the single source of truth consumed by
goal planning, activity construction, intent validation, plan validation, and
evaluation. Each immutable entry declares its execution mode, authoritative
evidence type, exact action or activity identity, target policy, required tags,
and location requirement. Unknown strategies and malformed plans fail closed.

| Strategy | Mode | Required authoritative behavior | Target rule |
| --- | --- | --- | --- |
| `direct_cooperation` | social | registered `cooperate` | selected resident required |
| `apologize_directly` | social | registered `apologize` | selected resident required |
| `offer_help` | social | registered `offer_help` | selected resident required |
| `low_risk_chat` | social | registered `chat` | selected resident if present; otherwise any scheduled listener |
| `ask_target_directly` | social | registered `ask_for_help` | selected goal target required |
| `ask_informed_agent` | social | registered `ask_for_help` | selected alternate resident required |
| `ask_reliable_partner` | social | registered `ask_for_help` | selected relationship target required |
| `seek_information_at_location` | activity | `goal_seek_information` | selected location required |
| `study_reference_material` | activity | `goal_study_reference_material` | selected knowledge location plus owned `reference_book` |
| `observe_relevant_activity` | activity | `goal_observe_relevant_activity` | selected location plus current event there |
| `direct_participation` | activity | `goal_direct_participation` | selected location plus current event there |

No strategy adds a world-effect authority. A social strategy is feasible only if
its target policy is satisfied and relationship rules allow its registered action.
A location strategy is executable only if the configured location exists.
Unknown strategies, unknown required actions, missing targets/locations, and any
future candidate without an explicit mapping are not safely executable and fail
closed. Existing legacy intent behavior remains available only outside a safely
bound goal-plan path.

The three location activities carry internal `source_goal_id`,
`source_goal_plan_id`, `source_goal_plan_revision`, `source_goal_strategy`, and
`source_intent_id` provenance. Activity records persist those optional fields.
They are diagnostic proof inputs only: they do not mutate a plan or goal and are
not exposed in unrelated residents' prompt context. Reaching the location through
`wander`, a purchase, an event, or another goal strategy is not proof.

## Phase 3 dependency contract

Phase 3 extends the same immutable strategy registry. A contract may specify zero
or one dependency from a closed vocabulary. The currently supported kind is:

| Kind | Meaning | Authority | Preparation | Failure behavior | Strategies |
| --- | --- | --- | --- | --- | --- |
| `daily_event_at_target_location` | A real current daily event exists at the plan's selected location | `SimulationEngine.current_daily_event` (`DailyEvent.id` and `location_id`) | none; the plan waits | absence or a different location remains `waiting`; unknown kinds fail closed | `observe_relevant_activity`, `direct_participation` |
| `owned_good` | The plan owner has the fixed configured good | `MaterialSystem` agent inventory | exact registered configured purchase | no route makes only this strategy unavailable | `study_reference_material` |

```text
Goal
 ↓
GoalPlan revision
 ↓
finite strategy
 ↓
dependency contract
 ↓
authoritative prerequisite state
 ├── satisfied ─────────────┐
 ├── preparable → activity ─┤
 └── unavailable → adapt    │
                            ↓
                   exact strategy execution
                            ↓
                   authoritative evidence
                            ↓
                       Goal progress
```

The daily-event dependency is recomputed before activity selection and again
before proof acceptance. A persisted `satisfied` label is diagnostic, not
authority: resume must still observe the current event. The selected activity
carries dependency kind, subject, and event ID in addition to Phase 2 provenance.
A different event, location, revision, strategy, plan, intent, owner, or goal
cannot cross-credit. The event appearing changes no goal progress; only the exact
Phase 2 activity does.

## Phase 4 bounded authoritative resource preparation

The four V4 phases have separate responsibilities:

- Phase 1: persistent selected strategy.
- Phase 2: exact strategy execution contracts.
- Phase 3: authoritative opportunity dependencies.
- Phase 4: bounded authoritative resource preparation.

Phase 4 adds exactly one dependency kind, `owned_good`, and exactly one strategy
using it: `study_reference_material` for `investigate` and
`increase_knowledge` goals. Its subject is fixed to the configured
`reference_book`; model text cannot nominate another good. Final execution is
the separately registered `goal_study_reference_material` activity at the
goal-selected knowledge location.

```text
GoalPlan
  |
  v
reference_book dependency
  +-- owned -------------------------> study
  `-- missing
        |
        v
 authorized configured seller route
        |
        v
 real atomic purchase (money + lot)
        |
        v
      owned
        |
        v
 goal_study_reference_material
        |
        v
 authoritative goal evidence
```

`MaterialSystem.find_purchase_route()` is read-only. It accepts only the current
agent inventory/account linkage, configured good and price, an active configured
seller with a location and sufficient stock, and sufficient buyer funds. The
commitment acquisition path delegates to the same helper. It never creates stock,
sellers, prices, or funds.

When the book is absent but that route exists, the dependency is `preparable`.
The current bound revision may emit `goal_acquire_reference_book` at the seller
location with owner, goal, plan, revision, strategy, intent, dependency, subject,
and seller provenance. The configured material activity rule invokes the existing
atomic purchase path and records the resulting exchange ID diagnostically. Its
stable event key prevents a replay from charging or transferring twice.

After preparation, ownership is recomputed from the agent's current authoritative
inventory. Ownership acquired through another legitimate route also satisfies
the dependency. Another agent's book and another good do not. If neither
ownership nor a legal route exists, this strategy becomes infeasible and existing
bounded adaptation may select another finite tactic. The goal is blocked only
when no safe candidate remains. Its score is deliberately comparable rather than
universal: an already-owned book or a knowledge goal with preserved prior progress
can select the strategy, while an ordinary new missing-book goal may prefer the
existing information route.

> **Acquisition satisfies only the prerequisite. Goal progress requires the exact strategy execution.**

Purchase is never final execution proof and increments neither intent nor goal
progress. A later tick must select the exact study activity. Ownership is checked
before selection and again before proof acceptance, so stale serialized status or
a book lost before study cannot authorize progress. Existing owner/goal/plan/
revision/intent/strategy evidence keys reject replay and cross-credit.

## Evidence and authority boundaries

V4 evidence keys include the owner, source goal, stable goal-plan ID, plan
revision, intent, strategy, proof mode, and authoritative activity or conversation
execution identity. Both the goal and goal plan retain bounded replay guards.
Proof from another owner, goal, plan, revision, intent, strategy, target, or
activity is rejected. A reload or replay cannot increment progress or append a
second mirrored record.

`GoalPlan.observe_goal_evidence()` verifies the current active contract and that
the fully bound key and metadata already exist in authoritative goal evidence.
Calling it with generated dialogue or an invented claim is a no-op. Broad legacy
intent categories may still weight ordinary behavior, but cannot certify a bound
strategy. Conversation replicas, concurrent workers, and batch rows never
receive the live `PlanSystem`; they only realize prepared context. The existing
snapshot, disjoint schedule, private session, realization barrier, and stable
ordered commit architecture is unchanged.

Goal planning has no API to modify relationships, reputation, memories, money,
inventory, materials, commitments, crime/evidence, or justice. Goal-plan IDs,
scores, revisions, and private selection diagnostics are not placed in another
resident's context. No new goal-plan memory is created; observable activity and
social outcomes continue through existing memory systems.

## Priority with V3 commitment plans

Goal plans operate through the intent layer. `ActivityPlanner` still evaluates
commitment opportunities before intent, event, and ordinary need behavior. Its
existing bounded pressure decision remains the single inspectable arbitration
point. A due accepted commitment can therefore preempt a goal intent, while both
the commitment plan and goal plan remain persistent. V3 commitment templates,
proof requirements, lifecycle, pair-private knowledge, and persistence are
unchanged.

## Evaluation

Run `python scripts/evaluate_goal_planning.py` for Phase 1 lifecycle coverage,
`python scripts/evaluate_goal_strategy_execution.py` for Phase 2 execution
fidelity, and `python scripts/evaluate_goal_strategy_dependencies.py` for Phase 3
dependency lifecycle, persistence, revision, arbitration, privacy, and authority
coverage. Run `python scripts/evaluate_goal_resource_dependencies.py` for the
Phase 4 purchase, ownership, execution, persistence, replay, conservation,
provenance, privacy, and V3-priority funnel. All use `FakeLLMClient`, isolate global random state, report named
scenarios and invariants, and exit non-zero on failure.

## Known limitations

The implementation still has one selected strategy and at most one prerequisite
per revision. It has no arbitrary dependency graphs, multiple prerequisites,
general hierarchical planning, LLM-authored tasks, arbitrary resource selection,
bargaining, dynamic prices, loans/debt, generalized shopping, navigation or
pathfinding, multi-party goal plans, or model-authored authoritative actions. The
only resource preparation is the fixed `reference_book` purchase for the fixed
study strategy.
