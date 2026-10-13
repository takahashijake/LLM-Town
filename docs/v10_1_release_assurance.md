# V10.1 integrated release assurance

This is a stabilization review stacked on V10, not a merged release.
[PR #8](https://github.com/takahashijake/LLM-Town/pull/8) targets
`v10-town-observatory`. No PR was merged, shared history rewritten, assertion
weakened, golden output updated, or deterministic configuration changed.

## Exact baseline and dependency graph

Connected GitHub reads and a fresh `git fetch origin` verified on 2026-10-13:

| Reference | Exact revision | State / target | Latest-head project Actions |
| --- | --- | --- | --- |
| main | `cd55b2c40c37d078b2d6ae9df705405f141155cc` | V7 | No run returned by exact-commit lookup; focused regression reproduced below |
| V8 #5 | `83a99244b6df19f876a43b5953681c7045c2d936` | Open, targets main | Run `37734919227`, success |
| V9 #6 | `4c005355107ade7f40f6fa9588e5a64a7a626cda` | Open, targets V8 | Run `38098523328`, success |
| V10 #7 / starting revision | `ed0424d404a2e56176f0ea845b70db302f3bb27b` | Open draft, targets V9 | Run `38102967621`, all seven jobs successful |
| Ending implementation/test revision | `0e3f0657473f613ebe96a606caeb827d44213bed` | V10.1, targets V10 | See final verification record below |

The initial working tree was clean and on main. Stabilization was branched from
the fetched V10 head. Each listed predecessor is an exact ancestor, verified
with `git merge-base --is-ancestor`. `git merge-tree --write-tree` for each
adjacent pair returned its successor's exact tree without conflicts. This is a
current-tree rehearsal, not evidence about future target changes. #8 is also
mergeable according to its refreshed GitHub metadata.

Separate commit-status reads found **Rubber Duck / CodeAnalyzer: failure** on
main, V8, V9, V10 and the V10.1 implementation head. Successful project Actions
are not a successful combined CI conclusion. This unresolved external review
status prevents declaring this milestone fully release-verified. Its concrete
finding disposition is recorded below; no check was disabled or bypassed.

No submitted reviews, inline review threads or requested reviewers were returned
for #5–#7. This does not imply review approval. The connected branch-protection
API returned **403, Resource not accessible by integration**. A later basic branch read reports main `protected: false` and required status
checks off with no contexts. Detailed protection/ruleset/review settings were not
accessible through the protection API; a maintainer must verify fresh settings
before integration.
Automated scanner comments are considered separately from approval; the V10
freeze document records its existing scanner dispositions.

Starting assurance already includes V6's 730 actual-save corruption cases,
35/69 checkpoint checks, rollback and same-tick material tests; V8's causal
reference/replay/privacy attacks; V9's contributions, stale offers, cancellation
and reconstruction; and V10's public metric validation, hostile manifests,
fresh package replay and Chromium checks. These implementations are reused.

## Confirmed defects and minimal reproductions

1. **Interrupted checkpoint destroys the previous world.** On untouched V10,
   save a real engine, patch `Path.write_text` to write its first 100 characters
   and raise `OSError`, then save again. The previous checkpoint is truncated.
   `test_interrupted_checkpoint_preserves_previous_save` failed before the fix.
2. **Ambiguous JSON enters reconstruction.** `SimulationState.load()` accepted
   duplicate top-level/nested keys, `NaN`, `Infinity`, numeric overflow `1e999`,
   and a list root. Empty files/objects silently selected a new world. The new
   bounded regression examples prove rejection before engine reconstruction;
   valid missing files still support fresh initialization.
3. **Inherited V7 fixture regression, already fixed in V8.** A detached checkout
   at exact main ran the six inspector tests: **1 failed, 5 passed**,
   `KeyError: transactions`. A real V9 engine save contains `economy.ledger`
   and no `economy.transactions`. Changing a copied ledger amount makes the
   repaired comparison report a changed ledger; original save bytes stay intact.
   V10.1 does not duplicate V8's repair.
4. **Inherited freeze RNG continuation, already fixed in V10.** `_horizon`
   restores its caller's global stream, so its capacity tail must explicitly
   resume the captured horizon stream. Existing two tests cover its helper and
   failure path. One added test exercises real engines, unrelated caller seeds
   and an intervening engine before reconstruction/continuation. No new runtime
   RNG defect was discovered and no production RNG behavior was changed.

Final review also caught a field-name echo in the new duplicate-key diagnostic.
A private sentinel in an actual-save mutation reproduced the disclosure; the
message is now fixed text and that regression passes. This is a review correction
to this PR, not a claim about V8 inspection, which already controls its messages.

The initial fault reproducer recorded six intended failures and one fixture
setup failure (the fresh engine has an empty ledger). After correcting that
fixture assertion, the exact authority-override case is protected. A second
pre-fix probe recorded **2 failed, 11 passed** for overflow/empty input. Failed
or interrupted development runs are not counted as successful release gates.

## Persistence correction and compatibility

Serialization completes before any file is opened, rejecting non-finite values.
A private temporary file is written beside the save, synchronized, then replaced
atomically on the same filesystem. Write, synchronization and replacement
exceptions propagate; cleanup removes the staged file. The last complete save
remains intact until the replacement succeeds. JSON bytes, field layout and
schema versions for valid saves are preserved; new checkpoint files use private
permissions from `mkstemp`.

The loader rejects duplicate keys recursively, non-finite constants/overflow,
non-object roots, empty objects and empty existing files. It does not migrate, validate missing
historical evidence, call a provider or confer authority. Domain reconstruction
retains its existing validators. Clean legacy saves retain optional V9 omission
and explicit opt-in; disabled worlds do not acquire RNG/project sections.

Disk checkpoint atomicity does **not** roll back an already executed in-memory
tick. This is a single-writer checkpoint contract, not a concurrent-writer lock
or a guarantee against storage failure/power loss. An abrupt process kill can
leave a private staging file; it cannot make that file the authoritative save.
Directory durability across power loss remains filesystem-dependent.

## Named regression boundaries

| Test / contract | Mutation or interruption | Exact protected assertion |
| --- | --- | --- |
| `test_interrupted_checkpoint_preserves_previous_save` | Partial staged write then exception | Prior bytes and saved day unchanged, staged file absent, later save succeeds |
| `test_checkpoint_failure_before_commit_preserves_world` | Serialization, fsync or replace failure | Prior bytes and monetary/material state identical |
| `test_nonfinite_engine_state_cannot_replace_checkpoint` | NaN resident need | Serialization rejects, previous checkpoint intact |
| `test_ambiguous_save_rejected_without_mutation` | Duplicate keys, non-finite/overflow, empty file/object or list | ValueError, input bytes, RNG and file set unchanged; private duplicate field names never appear in diagnostics |
| `test_failed_checkpoint_commit_preserves_actual_lifecycle_boundary` | Replacement failure at formation, one contribution, before completion and after completion | Actual persisted institution/project/effect authority reconstructs to the same signature |
| `test_contradictory_authority_rejected_by_loader_and_inspector` | Swap valid contribution execution indices, another migrant actor, another sponsor employee, remove required work, premature workshop, alter ledger amount | Reconstruction rejects; caller RNG, input bytes and file set unchanged; invalid civic proof cannot expose progress/unlock edges |
| `test_legacy_fresh_process_continuation_with_explicit_rng_witness` | Unrelated child-process RNG and hash seeds 1/77 | Three-day checkpoint + five-day continuation equals uninterrupted eight-day authoritative and public signatures |
| `test_actual_horizon_continuation_is_independent_of_intervening_engine` | Caller seeds 1/77 and intervening real engine | Captured continuation yields identical authoritative growth state |
| `test_release_runner_keeps_independent_gates_after_failure` | Nonzero exit, timeout or missing executable | Failed status retained; next independent gate still runs; persisted JSON matches returned report |
| `test_actual_benchmark_profiles_reconstruct_and_retain_history` | Legacy, V6 and V9 real profiles | Reconstruction signature matches, input bytes intact, history increases, V9 optional sections follow policy |

Money corruption is globally rejected by reconstruction; unrelated civic edges
need not be invalidated solely because money is corrupt. Inspector assertions
for that case do not claim monetary corruption disables every independent proof.
Missing/pruned historical witnesses remain uncertainty under the existing V8
contract. Consistent attacker-rewritten histories are not cryptographically
authenticated by hashes or internal reconciliation. No new test pretends otherwise.
Existing negative suites retain replay, cross-branch, resource reservation,
dialogue-authority, network/model/transition guards and malicious browser strings.

Legacy replay's RNG witness is evaluator-owned and separate from the legacy save.
It tests a precise continuation without changing the V6 freeze schema. Disabled
legacy saves alone do not promise fresh-process RNG continuation. Simultaneous
runtime engines still share Python's process RNG; the evaluator explicitly
controls it instead of concealing that limitation. Different simulation seeds
are never required to produce identical trajectories.

## Repeatable verification and CI

Run from the repository root, with installed requirements and development tools:

```bash
python scripts/verify_release.py --output /tmp/llm-town-release-NEW
```

The selected directory must not exist. The command invokes the original compile,
scoped lint, JS syntax, diff, full pytest, both freeze modes, V8, V9, V10 generation,
independent replay and browser gates. It records revision, dirty state, Python,
platform, command, hash seed, exit/timeout and elapsed time in `release.json`.
Failures do not skip subsequent independent gates. `--gate NAME` permits fast
feedback and marks its result as **selected**, never full release verification.
Its local logs can contain private test diagnostics and must not be uploaded.
Browser tools must already be installed; deterministic runtime has no browser,
model-download or GPU dependency.

CI preserves all existing independent jobs and adds independently reported
integration regressions and a fail-fast-disabled stability matrix:
legacy/100 days/seed 23, V6/390 days/seed 23, V9/100 days/seed 11. Stability uses
hash seed 77. Required correctness is reconstruction/input preservation;
absolute timing has no pass/fail threshold. Existing normal/comprehensive freeze
and Observatory generation/replay keep hash seeds 1/77. CI publishes only explicit
JUnit reports, existing controlled reports, the public Observatory package and
`assurance.json`; never private benchmark worlds, logs or general quality metrics.

## Performance observations and limits

The existing `benchmark_simulation.py` now accepts `--assurance-profile` with
`legacy`, `v6` or `v9`. Profiles require fake LLM, run from the repository root,
and permit at most 400 days. The V6 provider/configuration is reused from the
freeze evaluator. Seed controls both engine identity selection and the process
activity stream. Default benchmarking remains available without a profile.

```bash
python scripts/benchmark_simulation.py --fake-llm --hours 8 --days 100 \
  --seeds 23 --assurance-profile legacy --output-dir /tmp/stability-legacy-NEW
python scripts/benchmark_simulation.py --fake-llm --hours 8 --days 390 \
  --seeds 23 --assurance-profile v6 --output-dir /tmp/stability-v6-NEW
python scripts/benchmark_simulation.py --fake-llm --hours 8 --days 100 \
  --seeds 11 --assurance-profile v9 --output-dir /tmp/stability-v9-NEW
```

| Profile | Run seconds | Save seconds/count | Final bytes | Reconstruct seconds | Public projection seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Legacy, 100 days | 25.694 | 13.256 / 200 | 3,535,945 | 0.106 | 0.409 |
| V6, 390 days | 217.540 | 98.671 / 780 | 15,390,517 | 0.218 | 0.504 |
| V9, 100 days | 26.090 | 12.442 / 200 | 3,503,470 | 0.180 | 0.491 |

These exploratory runs were concurrent with other gates and are not isolated
performance comparisons. RSS lifetime peaks on Linux were 59,472 / 151,812 /
65,404 KiB; this is process high-water memory, not isolated system allocation.
Daily public counts show V6 population/locations 4/4 → 8/8, institutions 0 → 3,
transactions 1 → 302, activities 4 → 2,854 and daily history 1 → 390. V9 completed
four contributions and retained its original signature
`cc7883f38f910375e390c773e217eb796d13c109e7f58cd9c09e37462b2664a5`.
All three reconstructed identical authority and left inspection input unchanged.
Ten repeated causal institution traces averaged 0.060 s on the 3.50 MB V9 save
and 0.246 s on the 15.39 MB V6 save. Each repeated report was identical, original
bytes stayed unchanged and both retained two explicit uncertainties; latency
measurements did not fabricate historical eligibility evidence.

A separate 100-day legacy `cProfile` run measured 28.229 seconds of profiled
execution: conversation realization replicas spent 17.722 cumulative seconds in
`_make_realization_replica` and persistence 8.110 seconds. Deep-copying authority
is a growing cost and also an isolation boundary preventing dialogue realization
from changing authoritative systems. No optimization or history pruning was made
without a separately reviewed replacement for that boundary. Full-save JSON
serialization likewise grows with retained authority; checks intentionally do
not claim constant memory or save size. Public projection uses V10's existing
shared graph/audit machinery. Inspector input/output budgets may limit larger
worlds before a 400-day engine horizon; failure must remain explicit.

## Ordered integration plan

1. Review #8 against V10 and retain its independent checks. A maintainer may
   integrate the stabilization PR into the V10 branch after approval; do not
   merge a draft or rewrite V10 history. Re-run the V10 package and gates on
   that resulting head. This preparatory step does not merge V10 into main.
2. Fetch main and #5 again. Verify the actual head/target pair, protections,
   reviews, changed files and conflicts. Test the actual candidate merge tree
   for V8 against main (full pytest, both freezes, V8 showcase). Only then may
   the maintainer merge V8 into main. Recheck resulting main CI and digest.
3. Retarget #6 to the updated main, preserving shared history. Re-fetch and test
   its actual candidate merge tree: full pytest, both freezes, V8 and V9 gates.
   Merge only after review/check requirements pass; verify resulting main again.
4. Retarget #7, including approved #8 changes, to that actual main. Resolve any
   changed-target conflicts in ordinary commits. Explicitly obtain draft/review
   readiness. Run every release gate, independent checkpoint replay and Chromium
   QA on the actual candidate merge tree and final commit, then verify main
   after the maintainer's merge.

If dependencies were squash-merged, ancestor equality can change: inspect tree
and patch equivalence and use an ordinary merge from the updated target; never
copy the stack blindly or force-push it. Stop integration on any authority,
digest, privacy or replay failure. Current feature-head CI and conflict-free
ancestor checks do not establish any future merged-main result.

## Final verification record

Local environment: Python 3.13.11, pytest 8.3.4, Linux. CI uses Python 3.11.
The final PR description records the final documentation head, machine-readable
result paths and final-head GitHub CI URL. This document's ending implementation
revision is exact; the later evidence-only commit changes no executable source.

All required local deterministic gates passed on the final implementation. This
is **not a fully release-verified milestone while the external CodeAnalyzer
status fails**. Final documentation-head Actions/status evidence is maintained in
[PR #8's verification record](https://github.com/takahashijake/LLM-Town/pull/8),
which identifies its exact head and run URL without claiming a pending result.

| Gate | Executed result |
| --- | --- |
| Compileall, scoped Ruff E9/F, JS syntax, diff check | PASS |
| Final complete pytest | **1,247 passed**, 0 failures/errors/skips; 1,377.41 s; JUnit at `/tmp/llm-town-release-pytest.xml` |
| Focused persistence/replay/helper tests | **30 passed**, 1 full-freeze test deselected; 1.40 s |
| Real V9 lifecycle and joined-authority integration module | **22 passed**, 0 failures; all also passed in final full suite |
| Existing benchmark regressions | **3 passed** |
| Fast inspector/Observatory CI-equivalent gate | **143 passed**, 25 integration tests deselected; 4.43 s |
| Final-source normal V6, hash seed 1 | **77/77 scenarios, 42/42 invariants, 35/35 checkpoints, 730/730 mutations**; `/tmp/llm-town-freeze-release.json` |
| Final-source comprehensive V6, hash seed 77 | **77/77, 42/42, 69/69, 730/730**; `/tmp/llm-town-freeze-comprehensive-release.json` |
| V8 two-branch showcase | PASS, 90+90 reconstruction and branch checks |
| V9 project showcase, hash seed 77 | **29/29 checks**, all four independent checkpoint signatures match |
| V10 generation and second-hash-seed replay | PASS at `0e3f065`: fingerprint `4bb55219f906a2b59c9b3e97f8fe026642cf471c4f40b03b12050830b1d9e80a`; documentation-head replay repeated before delivery |
| Chromium offline/mobile/injection QA | PASS: six views, widths 1440/390, 0 external requests, 0 JS errors |
| Long-horizon legacy/V6/V9 observations | PASS reconstruction and read-only assertions; no absolute timing gate |
| Release command selected smoke | compile/lint/javascript/diff all PASS; explicitly selected scope |
| Implementation-head project Actions, run `38472446769` | Nine of eleven jobs passed at document preparation; full pytest/comprehensive pending. Final-head result is recorded in the PR. |
| Implementation-head external status | **Rubber Duck / CodeAnalyzer: failure**, two flagged imports with concrete disposition above |

Both final-source freeze reports have empty scenario/invariant/checkpoint/mutation
failure lists and exactly preserve
`9aec1a80d08364b98816a0607c719933ff41420abedf99e49e929c5b6f0760df`.
The final suite adds **38 cases** to the V10 1,209-test baseline. Earlier
interrupted full-suite attempts were discarded after regression additions and
final boundary corrections; only the complete final run is reported. No real
LLM or GPU run was performed or required. The source-head status is not falsely
represented as combined CI success, and draft readiness/review approval is not
inferred from passing deterministic tests.

## Automated review disposition

RubberDuck's comment on `75fd38f` classifies twelve new findings as high:
subprocess calls, unresolved imports and two tainted-flow categories. The
inspected subprocess sites use argument lists with `shell=False` (the default).
Benchmark metadata invokes fixed Git commands; replay tests execute literal
repository-owned Python source with only a temporary directory supplied as an
argument; the release runner's executable/arguments come from its fixed gate
allowlist. Neither save text nor manifest fields become executable code.

The indicated imports resolve in compilation, scoped Ruff and actual CLI/tests.
The later `0e3f065` scanner comment reports two new high findings, both
`UNRESOLVED_IMPORT`: the engine annotation under `TYPE_CHECKING` in `state.py`,
and the real evaluator import in the persistence test. A clean process imported
`src.simulation.state` with neither engine nor LLM module loaded; the evaluator
import separately resolved. That is concrete evidence for these import
dispositions, not permission to change the scanner status ourselves.
Output paths are explicitly caller-selected benchmark/verification directories;
existing-directory refusal prevents accidental replacement of prior runs.
General benchmark quality metrics may expose private synthetic social information,
so only the new explicit `assurance.json` projection is eligible for CI upload.
The artifact intentionally omits metrics, general configuration, agent details,
private histories and artifact-path lists. Scanner classifications were reviewed,
not disabled, and this disposition is not independent security certification.

The comment's critical secret examples are classified as pre-existing and point
to the existing inspector's privacy sentinels. No secret or credential was added.
A repository-wide credential audit or resolution of every pre-existing scanner
finding is outside this focused PR; maintainers should review that backlog
separately. Human review remains outstanding. The external CodeAnalyzer status is failing,
including on the final implementation. No repository-owned scanner configuration
was found. Changing subprocess spellings or suppressing whole finding categories
to evade that check would not improve safety, so it was not done. Maintainer
triage of the scanner findings/service configuration is required before this
milestone can be described as fully release-verified.

## Exact local commands

Executed from the project root. Output directories were new; earlier artifacts
were preserved under distinct names instead of overwritten. Test logs and raw
worlds remain in `/tmp`, outside Git and the public CI artifact allowlist.

```bash
python -m compileall -q src scripts tests
python -m pytest tests/simulation/test_state_atomicity.py \
  tests/analysis/test_release_assurance.py tests/analysis/test_v6_freeze_evaluation.py \
  -k 'not test_v6_freeze_passes' -q
python -m pytest tests/analysis/test_collective_project_evaluation.py -q
python -m pytest tests/analysis/test_benchmark.py -q
python -m pytest tests/analysis/test_simulation_inspector.py \
  tests/analysis/test_v6_freeze_evaluation.py -m 'not integration' -q
python -m pytest -q --junitxml=/tmp/llm-town-release-pytest.xml
PYTHONHASHSEED=1 python scripts/evaluate_v6_freeze.py \
  --output /tmp/llm-town-freeze-normal.json
PYTHONHASHSEED=77 python scripts/evaluate_v6_freeze.py --comprehensive \
  --output /tmp/llm-town-freeze-comprehensive.json
PYTHONHASHSEED=1 python scripts/evaluate_v6_freeze.py \
  --output /tmp/llm-town-freeze-final-code.json
PYTHONHASHSEED=1 python scripts/evaluate_v6_freeze.py \
  --output /tmp/llm-town-freeze-release.json
PYTHONHASHSEED=77 python scripts/evaluate_v6_freeze.py --comprehensive \
  --output /tmp/llm-town-freeze-comprehensive-release.json
python scripts/showcase_v8.py --output /tmp/llm-town-v8-verification
PYTHONHASHSEED=77 python scripts/evaluate_v9_collective_projects.py \
  --output /tmp/llm-town-v9-verification
PYTHONHASHSEED=1 python scripts/showcase_town.py \
  --output /tmp/llm-town-v10-verification
PYTHONHASHSEED=77 python scripts/showcase_town.py \
  --verify /tmp/llm-town-v10-verification
LD_LIBRARY_PATH=/tmp/v10-browser-libs/extracted/usr/lib/x86_64-linux-gnu \
  python scripts/check_observatory_browser.py \
  --report /tmp/llm-town-v10-verification/index.html
python -m ruff check --select E9,F \
  src/simulation/state.py src/analysis/benchmark*.py \
  scripts/verify_release.py scripts/benchmark_simulation.py \
  tests/analysis/test_release_assurance.py \
  tests/analysis/test_collective_project_evaluation.py \
  tests/analysis/test_v6_freeze_evaluation.py tests/simulation/test_state_atomicity.py
node --check src/analysis/observatory_assets/report.js
git diff --check
python scripts/verify_release.py --output /tmp/llm-town-v101-final-runner-smoke \
  --gate compile --gate lint --gate javascript --gate diff
```

The local browser command uses previously installed Chromium dependency libraries
in a temporary library directory; CI retains standard Playwright `--with-deps`.
No system/browser requirement was added to deterministic runtime dependencies.
After the implementation endpoint, the same generation/replay/browser commands
passed using `/tmp/llm-town-v10-release-source`. The earlier
`/tmp/llm-town-v10-final-verification` package belongs to the intermediate
`df842aa` revision. The documentation head is verified using a further new
directory `/tmp/llm-town-v10-delivery-verification`. Frozen baseline SHA-256 must be
exactly `9aec1a80d08364b98816a0607c719933ff41420abedf99e49e929c5b6f0760df`.
