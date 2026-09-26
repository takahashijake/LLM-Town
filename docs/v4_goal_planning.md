# V4 Phase 1: bounded autonomous goal planning

## Contract

V4 Phase 1 makes one deterministic strategy for an active durable goal persist
across short-lived intents and save/resume. It is not a general planner. It does
not create free-form steps, facts, resources, places, actions, or goals.

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
Intent (short-lived tactical attempt, bound to plan revision)
  |
  +----------------------+
  v                      v
target-location activity validated social action
  |                      |
  +----------+-----------+
             v
existing IntentSystem evidence rules
             |
             v
Goal progress/status (authority)
             |
             v
GoalPlan observes evidence and synchronizes lifecycle
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

## Current strategy support matrix

Every executable name comes from `GoalPlanner.STRATEGY_EXECUTION_MODES`.

| Strategy | Classification | Runtime/proof path |
| --- | --- | --- |
| `direct_cooperation` | Existing authoritative runtime | Registered `cooperate` action; normal validation/effects/goal evidence |
| `apologize_directly` | Existing authoritative runtime | Registered `apologize` action; normal validation/effects/goal evidence |
| `offer_help` | Existing authoritative runtime | Registered `offer_help` action; normal validation/effects/goal evidence |
| `low_risk_chat` | Existing authoritative runtime | Registered `chat` action; normal validation/effects/goal evidence |
| `ask_target_directly` | Existing authoritative runtime | Registered `ask_for_help`, with the selected target and relationship eligibility |
| `ask_informed_agent` | Existing authoritative runtime | Registered `ask_for_help`, with the deterministic alternate target |
| `ask_reliable_partner` | Existing authoritative runtime | Registered `ask_for_help`, with the deterministic relationship target |
| `seek_information_at_location` | Small V4 integration | Persistent target-location intent; existing activity evidence advances the goal |
| `observe_relevant_activity` | Small V4 integration | Persistent target-location intent; existing activity evidence advances the goal |
| `direct_participation` | Small V4 integration | Persistent target-location intent; existing activity evidence advances the goal |

No current named strategy needs a new world-effect authority. A social strategy
is feasible only if its target exists and relationship rules allow its registered
action. A location strategy is executable only if the configured location exists.
Unknown strategies, unknown required actions, missing targets/locations, and any
future candidate without an explicit mapping are not safely executable and fail
closed. Existing legacy intent behavior remains available only outside a safely
bound goal-plan path.

## Evidence and authority boundaries

Target-location evidence uses a stable key derived from goal, intent, day, and
location. Ordered social commit passes a stable conversation-session/turn key.
Both the goal and goal plan reject a processed key. A reload or replay therefore
cannot increment goal progress, append a second plan evidence record, or complete
an intent twice.

`GoalPlan.observe_goal_evidence()` first verifies that the key is already present
in authoritative goal evidence. Calling it with generated dialogue or an invented
claim is a no-op. Conversation replicas, concurrent workers, and batch rows never
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

Run `python scripts/evaluate_goal_planning.py`. The evaluator uses
`FakeLLMClient`, isolates global random state, reports named scenarios and
invariants, and exits non-zero on failure.

## Known limitations and next slice

This phase has one strategy per goal plan, one goal plan per source goal, and no
plan dependencies or multi-party coordination. Location strategies use the
existing target-location evidence granularity; they do not add navigation or a
new knowledge model. Social success remains constrained by existing action and
relationship evidence rather than natural-language claims.

The next logical V4 slice is richer deterministic execution/evidence for selected
finite strategies that currently share broad target-location or social evidence,
without widening mutation authority or adding LLM-authored steps.
