# V4 Phases 1–2: bounded goal planning and execution fidelity

## Contract

Phase 1 makes one deterministic strategy for an active durable goal persist
across short-lived intents and save/resume. Phase 2 makes each strategy denote a
distinct, authoritatively provable behavior. Neither phase is a general planner;
they do not create free-form steps, facts, resources, places, actions, or goals.

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

Plan schema version 3 adds `goal_plans` and `goal_planning_records` beside the
unchanged commitment-plan representation. Unversioned/version-1 and version-2
documents load with empty goal-plan fields. Version-2 commitment plans retain
their exact template, step, proof, and lifecycle behavior. Unknown future schema
versions and unknown goal strategy names fail closed.

A goal plan stores only bounded diagnostic state: source and owner IDs, strategy,
intent type, target agent/location, required action, feasibility and score at
selection, selected/review day, revision, lifecycle, at most 50 transitions, at
most 50 mirrored evidence records, and at most 50 plan evidence keys. It never
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
| `observe_relevant_activity` | activity | `goal_observe_relevant_activity` | selected location required |
| `direct_participation` | activity | `goal_direct_participation` | selected location required |

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

Run `python scripts/evaluate_goal_planning.py` for Phase 1 lifecycle coverage and
`python scripts/evaluate_goal_strategy_execution.py` for Phase 2 execution
fidelity. Both use `FakeLLMClient`, isolate global random state, report named
scenarios and invariants, and exit non-zero on failure.

## Known limitations and next slice

The implementation still has one selected strategy per goal-plan revision, no
general plan dependencies, no arbitrary multi-step decomposition, no navigation,
no model-authored authoritative actions, a limited finite vocabulary, limited
resource/opportunity awareness, and no multi-party coordination.

The next major V4 slice should be bounded resource/opportunity-aware strategy
dependencies: a finite strategy may recognize a real prerequisite before
execution while continuing to use only registered deterministic activities and
existing authoritative systems.
