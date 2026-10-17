# V9 verification record

## Verified repository baseline

Reconnaissance fetched `origin` and checked GitHub's live PR, issue and Actions
records. The initial working tree was clean. Main remained at
`cd55b2c40c37d078b2d6ae9df705405f141155cc`. The only open PR was
[#5](https://github.com/takahashijake/LLM-Town/pull/5), V8 causal inspection, at
`83a99244b6df19f876a43b5953681c7045c2d936`, based on main. V9's dedicated
`v9-collective-projects` branch starts at that exact V8 head and targets
`v8-causal-inspection`. It does not merge PR #5.

Main's [latest run](https://github.com/takahashijake/LLM-Town/actions/runs/37713791903)
failed. An isolated main worktree reproduced its inspector regression:

```bash
python -m pytest tests/analysis/test_simulation_inspector.py -q
# 1 failed, 5 passed: KeyError 'transactions' in the comparison fixture
```

PR #5's [head run](https://github.com/takahashijake/LLM-Town/actions/runs/37734919227)
was successful in all five jobs: complete pytest, fast inspector, normal freeze,
comprehensive freeze and showcase. Its inherited ledger-fixture repair is retained.
A separate untouched V8 worktree was used for the local full baseline gate.
[Issue #3](https://github.com/takahashijake/LLM-Town/issues/3) remained the roadmap
for dynamic growth, collective behavior, observability and release quality. V9
implements its bounded project direction, not the entire roadmap.

The baseline already included V3 commitment execution/accountability and V4 goal
planning/dependencies; V5/V6 population/place/event/institution/commerce growth;
strict deterministic persistence/replay; V7 read-only projection; and V8 typed
causal contract checks, privacy/input/output bounds and independently reported
release gates. No existing test, invariant threshold or freeze digest was changed.

## Executed gates

All required local gates completed successfully on 2026-10-11 (Python 3.13.11).

| Command | Result |
| --- | --- |
| `python -m compileall -q src scripts tests` | PASS |
| `python -m pytest -q --junitxml=/tmp/v9-clean-baseline.xml` in untouched V8 worktree | 1,038 passed in 1,213.24 seconds |
| `python -m pytest -q --junitxml=/tmp/v9-final-pytest.xml` | 1,139 passed in 1,269.72 seconds; zero failures, errors or skips |
| Combined feature and inspector acceptance command below | 197 passed in 64.83 seconds |
| `python -m pytest tests/analysis/test_simulation_inspector.py tests/analysis/test_causal_inspector.py -q` | 96 passed in 35.60 seconds |
| `PYTHONHASHSEED=1 python scripts/evaluate_v6_freeze.py --output /tmp/v9-freeze-final.json` | PASS, 77 scenarios, 42 invariants, 35 checkpoints, 730 mutations |
| `PYTHONHASHSEED=77 python scripts/evaluate_v6_freeze.py --comprehensive --output /tmp/v9-comprehensive.json` | PASS, 77 scenarios, 42 invariants, 69 checkpoints, 730 mutations |
| `PYTHONHASHSEED=77 python scripts/evaluate_v9_collective_projects.py --output /tmp/v9-accepted` | PASS, 29/29 checks, four reconstruction boundaries |
| `python scripts/evaluate_institution_growth.py` | PASS, 30/30 scenarios, 22/22 invariants |
| `python scripts/evaluate_event_ecology.py` | PASS, 28/28 scenarios, 21/21 invariants |
| `python scripts/evaluate_commitment_execution.py --output /tmp/v9-commitment-gate.json` | PASS, 20/20 hard invariants |
| Scoped Ruff E9/F command below | PASS |
| `git diff --check` and staged equivalent | PASS |

```bash
python -m pytest tests/systems/test_collective_projects.py \
  tests/simulation/test_project_persistence.py \
  tests/analysis/test_collective_project_evaluation.py \
  tests/analysis/test_simulation_inspector.py tests/analysis/test_causal_inspector.py -q
```

```bash
python -m ruff check --select E9,F \
  src/analysis/inspection_*.py src/analysis/simulation_inspector.py \
  src/analysis/causal*.py scripts/inspect_town.py scripts/showcase_v8.py \
  tests/analysis/test_causal_inspector.py tests/analysis/test_simulation_inspector.py \
  src/systems/collective_projects.py src/simulation/project_random_state.py \
  src/analysis/collective_project_evaluation.py scripts/evaluate_v9_collective_projects.py \
  tests/systems/test_collective_projects.py tests/simulation/test_project_persistence.py \
  tests/analysis/test_collective_project_evaluation.py
```

The final CLI showcase has PASS/FAIL exit status, substantive named invariants,
exact contribution references, an incomplete checkpoint, a rejected corrupted
example, six actual subsequent workshop executions, one daily event per day, and
money/material reconciliation checks. Every resumed authority signature matches:

```
cc7883f38f910375e390c773e217eb796d13c109e7f58cd9c09e37462b2664a5
```

This hashes deterministic systems and public behavior, including crime, justice, commitments, plans, procedural growth, relationship
scores, public goal/intent/arc state, resident needs and locations, excluding legacy UUID-bearing memories and narrative. It is not
an assertion that entire saved JSON bytes match. Project causal traces also match
across independent reconstruction. A separate subprocess with hash seed 77 and
initial activity seed 999 resumes the one-contribution save and matches authority.
Inspector subprocesses with hash seeds 1 and 77 have identical output, as does
reversed top-level dictionary insertion order.

## Adversarial review and repairs

| Perspective | Finding and repair | Verification |
| --- | --- | --- |
| Correctness | The final work slot could be consumed on the first day, preventing the required second day. Reserve the final slot for another work day and for missing distinct residents. | Work/day/resident boundaries and complete actual seeded trajectory |
| Security/untrusted output | A copied resident or changed offered activity could impersonate execution if equality or mutable metadata were trusted. Require exact resident/activity/log object identity and capture canonical action/place/source/tag bindings. Reject mixed or narrative authority. | Forged actors, copied rows/activities/residents, wrong locations/clocks, modified offers, prose claims |
| Replay/persistence | Existing global activity RNG was not persisted, so fresh-process continuation could diverge. V9 saves retain and validate that bounded stream; malformed states do not change it. | Four checkpoints, unrelated starting seeds, subprocess continuation, eight RNG corruption cases and real mid-day cancellation resume |
| Historical eligibility | A forged roster or workshop record could claim participation before arrival. Reconcile the exact sorted activation roster and workshop dates against authoritative migrations. | Future-arrival roster regression and wrong institution/project binding; chronological workshop validation |
| Scheduling/capacity | Previously issued offers could become stale after another actor executed. Recheck remaining work requirements and workshop capacity at execution; cap ephemeral offers at 64. | Stale work and workshop offers; large resident pool |
| Test effectiveness | Initial inspector extension violated V7's mandatory-source and V8's nested-collection assumptions. Keep V7 source contracts unchanged and index civic activities separately. | Existing 96 inspector tests unchanged; typed V9 graph tests |
| Maintainability | Avoid donations, generic templates, broad world generation and a duplicate workshop history. Keep finite immutable records and reuse planner/executor/location behavior. | Small integration changes; strict schema/finite template tests |
| Performance | Scanning all history for each workshop offer would scale with run length. Scan only the trailing current-tick records; project work scans at most 16 contributions. | History-size spot benchmark and bounded-offer test |

Additional corruption tests cover duplicate IDs, another actor's activity index,
wrong project/institution/location, missing proof/prerequisite/authority,
unsupported templates/resource parameters, booleans/invalid bounds, stale/future
clocks, canonical ordering, premature/duplicate effects, removed work, review
rewinds/jumps, terminal replay, null/schema corruption, disabled policy with effects
or RNG authority, malformed activity history and private narrative. Rejected
execution attempts leave project/effect authority unchanged; failed loads leave
the caller RNG unchanged and do not rewrite source saves. Monetary/material
partial operations are outside V9's implemented scope: it performs none. Existing
transaction/replay tests and evaluator invariants remain the conservation gate.

Initial development failures were repaired; existing tests were not weakened or
removed. Duplicate inspector identities retain V8's stronger controlled-input
rejection rather than being treated as valid or speculative edges. Missing causal
proof remains unresolved. The read-only tests prohibit project constructors and
transitions, check unchanged save bytes, and verify narrative exclusion.

## Performance and bounded state

A model-free 100-day spot run measured 8.411 seconds disabled and 7.102 seconds
enabled, both with 537 activity records, while other assurance gates were running.
This noisy measurement is not a speedup claim. Twenty thousand workshop-opportunity
queries measured 0.0502 seconds with 537 records and 0.0503 seconds after adding
100,000 unrelated historical records in memory. The query checks the current tick
only. The benchmark changed no saved authority and wrote only under `/tmp`.

Project authority stays bounded to one project, at most 16 contributions and one
effect; transient offers are capped at 64. Each future workshop execution uses the
existing activity history instead of creating another subsystem history. Loads
and inspection still process existing histories within their established budgets.

## Release status and limits

All required local gates passed. The [V9 freeze candidate](v9_freeze_candidate.md)
records release signatures and the implemented scope. PR #6 remains unmerged and
stacked on open PR #5. GitHub CI is reported separately; pending remote CI is not
a local test pass. CI
adds a V9 evaluator/lint job and uploads controlled reports without generated
saves or private dialogue.

Implemented limitations: one garden template; activity work only; no money/material
contributions; no terminal retries; activation-time participant roster; no new
institution/place contraction; shared process RNG for simultaneous engines; old
UUID private memory identities excluded from authority comparison; and internal
save consistency rather than cryptographic authenticity. Incomplete projects can
expire under ordinary resident arbitration. See the architecture document for
strict compatibility and history-retention contracts.

## File inventory

New source: `src/systems/collective_projects.py`,
`src/simulation/project_random_state.py`, `src/analysis/causal_projects.py`,
`src/analysis/collective_project_evaluation.py` and
`scripts/evaluate_v9_collective_projects.py`.

New tests: `tests/systems/test_collective_projects.py`,
`tests/simulation/test_project_persistence.py` and
`tests/analysis/test_collective_project_evaluation.py`.

New documentation: `docs/v9_collective_projects.md`, `docs/v9_verification.md`,
and `docs/v9_freeze_candidate.md`.

Modified integration: `src/behavior/activity.py`, `src/behavior/planner.py`,
`src/simulation/activity_system.py`, `src/simulation/engine.py`,
`src/simulation/simulation_loop.py`, `src/simulation/state.py` and
`src/systems/town_growth.py`.

Modified observation/delivery: `src/analysis/causal_evidence.py`,
`src/analysis/causal_inspector.py`, `src/analysis/inspection_presentation.py`,
`src/analysis/inspection_records.py`, `src/analysis/inspection_save.py`,
`scripts/inspect_town.py`, `README.md` and `.github/workflows/tests.yml`.
