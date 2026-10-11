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
  V9 remained open at the final verification check. Pending dependency CI is
  not represented as successful.

Main's inherited V7 `transactions`/`ledger` fixture regression was independently
reproduced on an isolated checkout (**1 failed, 5 passed**, `KeyError: transactions`)
and is already repaired
by V8; V10 retains that dependency and does not duplicate its repair. No frozen
configuration, deterministic transition, threshold or expected digest is changed.
The inherited long-tail evaluator RNG defect described below is repaired in V10.

Runtime implementation revision: `bd2ebda41eaea507fcda971083322ccbdd4e7810`.
Final delivery additionally records completed verification without changing runtime.
Review: [PR #7](https://github.com/takahashijake/LLM-Town/pull/7), a draft targeting
`v9-collective-projects`. No dependency is merged.

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

Local verification is complete. Pending remote jobs are reported separately.

| Gate | Result |
| --- | --- |
| Baseline full V9 pytest | 1,139 passed, 0 failures/errors/skips, 1,385.79 s |
| Compilation | PASS on final runtime revision |
| Scoped Ruff E9/F and JS syntax | PASS on final runtime revision |
| Observatory unit/adversarial tests | 54 passed after empty-civic correction |
| Observatory + V7/V8/V9 feature and persistence acceptance | 265 passed, 0 failures/errors/skips, 274.83 s |
| Fast CI-equivalent verification | 142 passed, 25 integration tests deselected; 4.33 s |
| Final complete pytest | 1,209 passed, 0 failures/errors/skips, 1,421.78 s |
| Normal V6 freeze, hash seed 1 | Post-repair PASS: 77/77 scenarios, 42/42 invariants, 35/35 checkpoints, 730/730 mutations; 259.99 s |
| Comprehensive V6 freeze, hash seed 77 | Post-repair PASS: 77/77 scenarios, 42/42 invariants, 69/69 checkpoints, 730/730 mutations; 1,117.84 s |
| Reused V9 evaluator | 29 checks passed in first generated package |
| Reused V8 showcase | Passed in first generated package |
| Independent whole-package replay, second hash seed | Passed at initial runtime revision; final-delivery rerun recorded in PR |
| Chromium file-protocol / desktop / mobile / injection smoke | Passed: 0 external requests, 0 JS errors, widths 1440 and 390 |
| Git diff checks | PASS; documentation-only verification update pending commit |

Initial spot measurement: generation 82.67 s (garden 19.37 s, commerce 62.04 s),
projection 1.07 s, presentation/export 0.075 s, public package 10,980,159 bytes.
These are measured local values, not performance thresholds. Runtime-head generation under concurrent regression load took 130.37 s; projection
1.69 s, export 0.108 s, public package 10,997,229 bytes. Twenty inspections of a
3,503,470-byte final save averaged 0.154 s; its public checkpoint contains 775
events and 38 entities (391,002 bytes). Final-delivery example generation and replay
are repeated after the documentation commit; their results belong in the PR.

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
checkpoint publication after a failed horizon. Both final freeze gates passed as recorded above.
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

## Exact executed commands

Run from the repository root; generated worlds and diagnostics stay outside Git.

```bash
python -m compileall -q src scripts tests
python -m ruff check --select E9,F \
  src/analysis/inspection_*.py src/analysis/simulation_inspector.py \
  src/analysis/causal*.py src/analysis/observatory*.py \
  src/analysis/town_showcase.py src/analysis/procedural_institution_evaluation.py \
  src/analysis/v6_freeze_evaluation.py scripts/inspect_town.py \
  scripts/showcase_v8.py scripts/showcase_town.py scripts/check_observatory_browser.py \
  tests/analysis/test_observatory.py tests/analysis/test_town_showcase.py \
  tests/analysis/test_causal_inspector.py tests/analysis/test_simulation_inspector.py \
  tests/analysis/test_v6_freeze_evaluation.py
node --check src/analysis/observatory_assets/report.js
python -m pytest tests/analysis/test_observatory.py tests/analysis/test_town_showcase.py \
  tests/analysis/test_simulation_inspector.py tests/analysis/test_causal_inspector.py \
  tests/analysis/test_collective_project_evaluation.py \
  tests/simulation/test_project_persistence.py tests/systems/test_collective_projects.py \
  -q --junitxml=/tmp/v10-final-feature.xml
python -m pytest tests/analysis/test_v6_freeze_evaluation.py -m 'not integration' -q
python -m pytest -q --junitxml=/tmp/v10-complete.xml
PYTHONHASHSEED=1 python scripts/evaluate_v6_freeze.py --output /tmp/v10-normal-final.json
PYTHONHASHSEED=77 python scripts/evaluate_v6_freeze.py --comprehensive --output /tmp/v10-comprehensive-final.json
PYTHONHASHSEED=1 python scripts/showcase_town.py --output /tmp/llm-town-v10-runtime
PYTHONHASHSEED=77 python scripts/showcase_town.py --verify /tmp/llm-town-v10-runtime
python scripts/check_observatory_browser.py --report /tmp/llm-town-v10-runtime/index.html
git diff --check
```

The unified runner executes these real existing commands in disposable directories:

```bash
python scripts/evaluate_v9_collective_projects.py --output TEMP_GARDEN
python scripts/showcase_v8.py --output TEMP_COMMERCE
```

The complete suite includes existing persistence, economy, materials, commitment,
plan and town-growth integrations; none is replaced by new Observatory tests.
Browser QA ran locally with the downloaded Chromium dependency libraries in a
temporary `LD_LIBRARY_PATH` because this container could not install system
packages via sudo. CI uses the standard Playwright `--with-deps` setup. No
browser dependency or system-library change was added to runtime requirements.

Post-repair normal and comprehensive modes both retain the exact frozen digest:
`9aec1a80d08364b98816a0607c719933ff41420abedf99e49e929c5b6f0760df`.
Both diagnostics contain empty failure lists. Neither gate is a retry with altered
thresholds: both run the corrected seeded continuation and all original checks.

Runtime-head GitHub Actions run `38101369987` has successful fast-inspector, V8
showcase, V9 collective-project, normal freeze and Observatory jobs. The
Observatory job includes real package generation, hash-seed replay and Chromium
checks. Comprehensive freeze and full pytest were pending at this status read;
local success is not represented as their CI conclusion.

## Changed boundaries

New public projection, presentation and runner modules live in `src/analysis/`
with three local report assets. New CLI/browser QA scripts and two test modules
cover the product contract. Existing causal modules retain audit metadata only;
`inspect_town.py` adds the report subcommand. Two evaluator modules and focused
freeze tests repair continuation RNG. README, V10 documents and GitHub Actions
provide reproduction and release gates. No runtime dependency is added.
