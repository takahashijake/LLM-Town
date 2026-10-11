# V10 release / freeze candidate

This is a stacked review candidate, not a merged release. V8 PR #5 and V9 PR #6
remain unmerged. No history is rewritten and neither dependency is merged by V10.

## Exact baseline

Connected GitHub metadata plus `git fetch origin` verified:

- Main: `cd55b2c40c37d078b2d6ae9df705405f141155cc`.
- V8 #5 head: `83a99244b6df19f876a43b5953681c7045c2d936`;
  target `main`; head CI run `37734919227` completed successfully.
- V9 #6 head / V10 starting SHA: `4c005355107ade7f40f6fa9588e5a64a7a626cda`;
  target `v8-causal-inspection`.
- Clean starting working tree; local HEAD already matched the fetched V9 head.
- V10 branch: `v10-town-observatory`; target `v9-collective-projects`.
- No inline review threads on #5/#6; no review submissions on #6 at inspection.
- V9 CI run `38098523328`: feature, fast inspector, V8 showcase and normal freeze
  succeeded at reconnaissance; full pytest and comprehensive freeze were pending.
  Dependency CI must be rechecked before final delivery.

Main's inherited V7 `transactions`/`ledger` fixture regression is already repaired
by V8; V10 retains that dependency and does not duplicate its repair. No frozen
configuration, deterministic transition, threshold or expected digest is changed.
The inherited long-tail evaluator RNG defect described below is repaired in V10.

## Product contract

A new one-command runner exports eight public checkpoints, complete sanitized
histories, typed causal reports, differences, deterministic manifests,
a walkthrough and an offline responsive interface. It reuses the real V9
canonical trajectory and separately labels the existing V8 commerce fixture.
Raw saves/logs and private narrative stay temporary. Independent verification
regenerates trusted scenarios and resumes multiple meaningful checkpoints.

Projection, validation, orchestration and rendering are separate modules. Read-only V8/V9 graph metadata retains replay results and empty-civic validation
status for metric reuse; trace output/signatures remain unchanged. A narrowly
scoped freeze-helper extension captures the actual seeded continuation stream. The simulation engine,
authoritative systems, configuration, persistence schemas and freeze baselines
are unchanged. The new `inspect_town.py report` command is read-only and bounded.

## Executed verification

This section is updated after gates finish; pending work is not a pass.

| Gate | Result |
| --- | --- |
| Baseline full V9 pytest | 1,139 passed, 0 failures/errors/skips, 1,385.79 s |
| Compilation | Passed during implementation; final rerun pending |
| Scoped Ruff E9/F | Passed during implementation; final rerun pending |
| Observatory unit/adversarial tests | 54 passed after empty-civic correction |
| Observatory + V7/V8/V9 feature and persistence acceptance | 265 passed, 0 failures/errors/skips, 274.83 s |
| Final complete pytest | Pending |
| Normal V6 freeze, hash seed 1 | Pending |
| Comprehensive V6 freeze, hash seed 77 | 77/77 scenarios, 42/42 invariants, 69/69 checkpoints, 730/730 mutations before tail repair; post-repair rerun pending |
| Reused V9 evaluator | 29 checks passed in first generated package |
| Reused V8 showcase | Passed in first generated package |
| Independent whole-package replay, second hash seed | Passed at initial runtime revision; final-revision rerun pending |
| Chromium file-protocol / desktop / mobile / injection smoke | Passed: 0 external requests, 0 JS errors, widths 1440 and 390 |
| Git diff checks | Pending final rerun |

Initial spot measurement: generation 82.67 s (garden 19.37 s, commerce 62.04 s),
projection 1.07 s, presentation/export 0.075 s, public package 10,980,159 bytes.
These are measured local values, not performance thresholds. Final artifacts and
measurements will be recorded after implementation freezes.

A negative test discovered and repaired a V10 metric error: reconciled material
holdings alone did not prove valid reciprocal exchange references. Exchange
metrics now require both verified V8 goods/payment legs. Production counts also
require verified output edges. Missing proof remains unknown; tests were not
relaxed. Browser QA prompted focused section navigation and fixed narrow-layout
wrapping. One graph and one ledger/material replay serve all queries per checkpoint.

## Reproduce

```bash
python scripts/showcase_town.py --output /tmp/llm-town-v10
PYTHONHASHSEED=77 python scripts/showcase_town.py --verify /tmp/llm-town-v10
python scripts/inspect_town.py report SAVE.json --output /tmp/town.html
```

Optional browser QA (no runtime dependency):

```bash
python -m pip install playwright==1.63.0
python -m playwright install --with-deps chromium
python scripts/check_observatory_browser.py --report /tmp/llm-town-v10/index.html
```

Known limits: internally consistent saves are not authenticated; historical
formation eligibility witnesses may be unavailable; private/social/legal fields
are excluded; no general public legal explorer is claimed; canonical seed success
is not a promise for every seed; bounded histories fail closed at capacity;
public snapshots are projections, not resumable saves. V9's shared process RNG
and upstream whole-save growth remain unchanged. See the
[architecture and supported limits](v10_town_observatory.md).

## Inherited assurance defect and correction

The first normal V6 command failed only `event_history_reaches_bound`: 76/77
scenarios, 42/42 invariants, 35/35 checkpoints, 730/730 rejected mutations. The
comprehensive command passed all 77 scenarios, 42 invariants, 69 checkpoints and
730 mutations. Both retained digest
`9aec1a80d08364b98816a0607c719933ff41420abedf99e49e929c5b6f0760df`.

An isolated worktree at exact V9 SHA `4c005355...` passed the normal command.
Inspection identified a pre-existing uncontrolled continuation: `_horizon` seeds
the 180-day trajectory, then restores its caller's process RNG; the capacity
stress subsequently resumes for 210 days on that unrelated caller stream.
The isolated actual seeded continuation reached 64/64 occurrences at day 390.
This explains a flaky assurance path without any changed world configuration.

V10 captures the actual end-of-horizon RNG in an optional evaluator-only sink and
uses it for the 210-day capacity stress, restoring the caller afterward. No engine
save field, policy, threshold, duration or expected digest changes. Two focused
tests prove caller isolation, exact continuation across seeds 1/77 and no
checkpoint publication after a failed horizon. Final freeze gates are rerun.
Full regression runs were deliberately interrupted/restarted after the empty
civic and evaluator corrections; their partial results are not full passes.

## Automated-review disposition

GitHub's RubberDuck review on runtime `e6a1737` flags subprocess calls, unresolved
imports and a tainted-flow category. Inspected command sites use fixed argument
lists with `shell=False` (default); no executable or serialized command comes
from a save or manifest. Tests and evaluators invoke repository-owned scripts.
Filename reads require an exact manifest allowlist and reject symlinks, traversal,
size/digest mismatches before replay; coherent manifest forgery cannot pass
independent regeneration. Compilation, scoped Ruff and actual CLI/browser tests
resolve the indicated imports. These broad scanner categories are assessed with
concrete tests, not suppressed or presented as independent proof of security.
Dependency bot comments report no introduced critical findings; their quoted
secret findings point to privacy-test sentinels, not newly introduced credentials.
