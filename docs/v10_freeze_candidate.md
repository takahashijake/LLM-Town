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

## Product contract

A new one-command runner exports eight public checkpoints, complete sanitized
histories, typed causal reports, differences, deterministic manifests,
a walkthrough and an offline responsive interface. It reuses the real V9
canonical trajectory and separately labels the existing V8 commerce fixture.
Raw saves/logs and private narrative stay temporary. Independent verification
regenerates trusted scenarios and resumes multiple meaningful checkpoints.

Projection, validation, orchestration and rendering are separate modules. The only
V8 implementation extension retains existing replay audit results on the graph
for reuse; trace output/signatures remain unchanged. The simulation engine,
authoritative systems, configuration, persistence schemas and freeze baselines
are unchanged. The new `inspect_town.py report` command is read-only and bounded.

## Executed verification

This section is updated after gates finish; pending work is not a pass.

| Gate | Result |
| --- | --- |
| Baseline full V9 pytest | Running |
| Compilation | Passed during implementation; final rerun pending |
| Scoped Ruff E9/F | Passed during implementation; final rerun pending |
| Observatory unit/adversarial tests | 51 passing during implementation |
| Observatory + V7/V8 integration tests | Running; final rerun required after presentation changes |
| Final complete pytest | Pending |
| Normal V6 freeze, hash seed 1 | Pending |
| Comprehensive V6 freeze, hash seed 77 | Running |
| Reused V9 evaluator | 29 checks passed in first generated package |
| Reused V8 showcase | Passed in first generated package |
| Independent whole-package replay, second hash seed | Pending final assets |
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
