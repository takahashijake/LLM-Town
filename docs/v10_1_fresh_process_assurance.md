# V10.1 fresh-process integration assurance

This document supplements [the integrated V10.1 assurance record](v10_1_release_assurance.md).
It describes the complementary work in PR #9. All required local gates passed
at the fixed implementation revision below. Final delivery-head CI is tracked
separately in the PR; local success alone is not a remote CI conclusion.
No existing release threshold, golden output, or authoritative transition changes.

## Refreshed dependency graph

Initial connected GitHub reconnaissance on 2026-10-17 found:

| Reference | Exact revision | Observed state |
| --- | --- | --- |
| main | `cd55b2c40c37d078b2d6ae9df705405f141155cc` | V7; CI run 37713791903 failed pytest and skipped its dependent freeze step |
| V8 #5 | `83a99244b6df19f876a43b5953681c7045c2d936` | open, target main; all 5 jobs passed in run 37734919227 |
| V9 #6 | `4c005355107ade7f40f6fa9588e5a64a7a626cda` | open, target V8; all 6 jobs passed in run 38098523328 |
| V10 #7 | `ed0424d404a2e56176f0ea845b70db302f3bb27b` | draft, target V9; all 7 jobs passed in run 38102967621 |

Each predecessor head was an exact ancestor of its successor. All three review
lists and review-thread lists were empty; no reviewers were requested. Read
`AGENTS.md`, workflow definitions, V6 freeze/audit/growth contracts, V8 evidence
contracts, V9 project/persistence contracts, V10 presentation/freeze contracts,
and existing benchmarks before implementation. The supplied workspace was an
empty directory inside another working tree; a dedicated clone avoids touching
that tree or its unrelated modified files.

The initial reconnaissance queried #5–#7 without enumerating every open PR.
It consequently missed assurance #8, created 2026-10-13, although that work was
already available. This was a reconnaissance gap. Before final acceptance its
implementation was integrated and duplicate work removed from the resulting diff.

During implementation, external repository activity merged assurance #8 into
V10 and merged #5 into main. A fresh fetch found:

- main: `fe577fe111c4645b950efc3e9b24272a49e10cde`, the merge of #5;
  its tree exactly equals the verified V8 head's tree.
- V9 #6: unchanged head, now targets main.
- V10 #7: `5be1b4c28e72b3ac76354b574f409c28e31a00ea`, including #8 head
  `9bacfd25a21d6704584540e126f078a0f7de872b`.
- QA #9: `v10.1-release-assurance`, targets `v10-town-observatory`.

The branch integrated updated V10 through merge commit
`9f77d10172973377f42f0fce7fe48a8ff9068397`, without rewriting history.
Conflicts in persistence, release orchestration, CI, and tests were resolved
by retaining upstream implementations and removing duplicate work. The
initial atomic-save correction is consequently inherited from #8, not an
additional production change in #9's final diff. Upstream stability jobs,
strict save parsing, all tests, and independent evaluator jobs remain intact.
V8 and V9 exact heads remain ancestors of V10; updated V10 is an ancestor of
this QA branch. No PR was merged by this task.

The final implementation revision is
`330dc3dfe7b345c681b270104064864a1d97c827`. The final delivery revision is
recorded in PR metadata after the evidence-only update; a document cannot contain its
own commit hash. Review `git log --oneline origin/v10-town-observatory..HEAD`
and `git diff origin/v10-town-observatory...HEAD` for the complete history and
focused resulting change.

Subsequent external activity merged V9 as
`d44bd3bfb09ddb10930fe5f0e82d93f59a8fd895` and V10 as
`2baed38cec383c0426b0786f5ff03bc2704cb471`. Only QA #9 remained open.
PR #9 was retargeted to actual main. `git diff` confirmed that main's tree
exactly equals V10 dependency `5be1b4c28e72b3ac76354b574f409c28e31a00ea`.
Read-only `git merge-tree --write-tree origin/main HEAD` produced exactly
HEAD's tree `fceacab6a429e3843c5d327718a12b497349d2a0` at revision 330dc3d,
with no conflicts. This checks the actual target integration tree without
creating a merge commit or changing the fixed evaluation checkout.

## Named regression boundaries

The existing 730-case V6 mutation gate, V8 material/monetary audits, V9
execution tests, and V10 privacy/browser tests remain the primary domain gates.
This addition does not replace them or reconstruct their authority separately.

`evaluate_release_replay.py` reuses real engine configurations, the existing
semantic-only multibranch provider, shared conservation/authority audits,
existing authoritative and behavior signatures, and the public Observatory
projection. Every trajectory runs in a new Python process; checkpoint files,
logs and RNG sidecars exist only in a temporary workspace. Only controlled
counts, timings, signatures, boundary coordinates and boolean checks escape.
A worker timeout produces a named scenario failure without exposing captured
stdout/stderr. Start/end source revision and code fingerprints, plus hashes of
all seven configured world JSON inputs, must match; source drift fails the gate
and both revisions remain in the machine report. This protects against the
runner mislabeling changes visible at its captured boundaries. It does not
authenticate source or detect every transient edit restored between captures;
use a fixed checkout, as in CI, for release verification. An existing output file is rejected before simulation begins.

| Scenario | Seed / duration | Fresh-process continuation boundaries |
| --- | --- | --- |
| Legacy frozen configuration, V9 disabled | 23 / 30 days | completed days 1 and 15 |
| V6 two-branch procedural / V8 commerce world | 23 / 180 days | actual institution formation and first generated inventory procurement |
| V9 real garden project | 11 / 100 days | formation, one contribution, final work before completion review, completed next-day effect |
| V10 Observatory | existing two scenarios | existing independent package regeneration and all V9 evaluator reconstruction boundaries |

Each new scenario compares uninterrupted execution at hash seed 1, repeated
execution of identical simulation seed/configuration at hash seed 77, and
fresh-process continuation of every required boundary at hash seed 77. Missing
boundaries fail rather than silently reducing coverage. The checker compares
all three scopes: existing growth/economic evidence with causal owner memories;
existing social behavior authority (crime, justice, commitments, plans, goals,
needs, activities and relationships); and canonical scoped public Observatory
output. UUID-bearing private narrative is deliberately outside those scopes.
Distinct simulation seeds are never required to produce equal worlds.

Legacy/V6 saves do not persist the global arbitration RNG. Their evaluator
records and explicitly restores an RNG sidecar, together with semantic provider
call counters. This proves continuation with an explicit execution environment,
not native legacy-save self sufficiency. V9 independently restores persisted
RNG from its save, and the checker verifies that it equals the captured boundary
before continuing. Engines remain isolated processes; this does not fix shared
in-process global randomness. The existing V10 horizon correction now also has
a real-engine regression: unrelated engine execution between a prefix and its
restored continuation must preserve both callers and final authority.

## Adversarial joined authority

The following additions mutate actual 100-day saves from the existing V9
module fixture. They do not invent substitute project systems.

| Valid contract | Bounded mutation | Exact required outcome |
| --- | --- | --- |
| Review day matches the checkpoint boundary | rewind last review by one day | loader raises; RNG and input bytes unchanged; no project progress/effect edges |
| Garden project binds its sponsor's exact location | substitute another real activated location | same rejection; public completed-effect metric is unknown |
| Completed work threshold precedes its effect | remove the final contribution and its actual executed row together, retain effect | incomplete authority rejected even after removing the reciprocal work witness |
| Sponsor funding matches the exact conserved ledger transaction | increment that transaction's amount | reconstruction rejects; downstream project effect remains unknown |
| One workshop execution per tick | replay a genuine workshop row | loader rejects and inspector rejects duplicate typed identity |
| Offers are ephemeral and cancellation grants no benefit | retain an actual offered object across cancellation, then reconstruct | stale execution returns false without money/material/project change; no restored opportunity or effect |
| Private prose and inspection confer no execution capability | inject secret canaries and hostile instructions into real memories/reasons | projection still reports the genuine single effect, leaks no canary, preserves input/RNG and calls no guarded capability |

The projection test guards Python file opening/writing, process/shell entry,
sockets, engine construction, and actual fake/real model generation methods.
The existing Chromium test separately covers hostile script-context strings,
offline file operation and mobile layouts. Test canaries are synthetic.

Internally consistent historical records are not independently authenticated.
A coherent rewrite of all supporting records may remain internally consistent;
no schema, adjacent digest or local manifest is claimed to be a cryptographic
signature. Missing historical eligibility evidence still produces uncertainty.

## Baseline defects and reviewed corrections

V7 inspector reproduction at initial main: **1 failed, 5 passed**; failure was
`KeyError: transactions` in the comparison test. The V8 repair is present in the
verified dependency: its inspector module passed **8/8** locally. The real V8
showcase also exercises comparison over genuine persisted engine saves whose
authoritative monetary records are `economy.ledger`.

Initial checkpoint fault injection exposed the in-place writer: an injected
replacement error did not interrupt saving because no atomic replacement
existed. Our focused atomic correction passed its three initial tests. Upstream
#8 subsequently supplied the broader atomic-write and strict-load correction,
so the final branch retains that implementation and its lifecycle-boundary
regressions, rather than maintaining two writers or duplicate tests.

Review also found that the first replay prototype sampled revision metadata
only at the end. The final runner records both execution boundaries and fails
on code/input/revision drift, with a regression test for changed provenance.
The initial 28-check matrix result therefore remains preliminary evidence;
final acceptance uses the revised immutable-source matrix, which passed all 29 checks at 330dc3d.

No new simulation RNG defect was found. An initial new test mistakenly reused
an engine's unchanged run-start coordinates and reran day 1; it was corrected
to reconstruct at the saved boundary before continuing. A prototype looked for
a nonexistent generated-inventory naming prefix; it now binds procurement to
actual activated commerce records. A prototype causal performance query used
an unsupported resident namespace; it now queries a real account or project/
institution. These were evaluator/test defects, not reasons to alter engine
behavior, frozen signatures, or acceptance thresholds.

## Verification commands and evidence

Use new output paths. Requested generic `/tmp` names included prior artifacts;
integrated verification uses `/tmp/llm-town-v101-integrated-20261017`.
Early checks against superseded revisions were interrupted and are not final
acceptance evidence. All model-free commands use the repository root as cwd.

```bash
python -m compileall -q src scripts tests
python -m pytest -q --junitxml=/tmp/llm-town-v101-integrated-20261017/pytest.xml
PYTHONHASHSEED=1 python scripts/evaluate_v6_freeze.py --output NEW_NORMAL_JSON
PYTHONHASHSEED=77 python scripts/evaluate_v6_freeze.py --comprehensive --output NEW_COMPREHENSIVE_JSON
PYTHONHASHSEED=1 python scripts/showcase_v8.py --output NEW_V8_DIRECTORY
PYTHONHASHSEED=77 python scripts/evaluate_v9_collective_projects.py --output NEW_V9_DIRECTORY
PYTHONHASHSEED=1 python scripts/showcase_town.py --output NEW_V10_DIRECTORY
PYTHONHASHSEED=77 python scripts/showcase_town.py --verify NEW_V10_DIRECTORY
python scripts/check_observatory_browser.py --report NEW_V10_DIRECTORY/index.html
python scripts/evaluate_release_replay.py --output NEW_REPLAY_JSON
PYTHONHASHSEED=77 python scripts/benchmark_simulation.py --fake-llm --hours 8 --days 390 --seeds 23 --assurance-profile v6 --output-dir NEW_STABILITY_DIRECTORY
node --check src/analysis/observatory_assets/report.js
git diff --check
```

Scoped Ruff E9/F includes all changed Python files and the existing persistence,
benchmark and release-runner modules. `scripts/verify_release.py --output NEW_DIR`
remains the single convenient release command, now also invoking fresh-process
replay. Existing optional `--gate` selection remains explicitly scoped, never
presented as a full release verification.

Completed local verification:

| Gate | Observed execution result |
| --- | --- |
| Compilation, scoped Ruff, JavaScript syntax, diff | PASS; also exercised through the existing release command's explicitly selected four-gate scope |
| New replay-focused module | 6 passed in 11.38 s after provenance hardening |
| Existing release-runner contract after adding the thirteenth gate | 13 passed in 4.39 s; exact gate set now requires fresh-process replay |
| Joined lifecycle/persistence/release focused run | 59 passed, 1 stale gate-set expectation failed; that expectation was corrected as described above and its 13-test module reran successfully |
| Fast inspector / Observatory CI-equivalent scope | 148 passed, 26 integration tests deselected in 6.85 s |
| Final complete pytest | **1,260 passed**, 0 failures/errors/skips, 1,665.08 s; all 13 new cases included |
| Normal V6 freeze / hash seed 1 | PASS: 77 scenarios, 42 invariants, 35 checkpoints, 730/730 rejected mutations; exact frozen digest preserved |
| Comprehensive V6 freeze / hash seed 77 | PASS: 77 scenarios, 42 invariants, 69 replay checks, 730/730 rejected mutations; exact frozen digest preserved |
| V8 showcase / simulation seed 23 / 180 days | PASS; 30 branch checks, two commerce branches, independent 90+90 reconstruction; actual save has 243 ledger entries and no transactions key |
| V9 showcase / simulation seed 11 / hash seed 77 | 29/29 PASS in 73.401 s; signature `cc7883f38f910375e390c773e217eb796d13c109e7f58cd9c09e37462b2664a5`; six workshops |
| V10 generation / hash seed 1 | PASS at `330dc3dfe7b345c681b270104064864a1d97c827`; fingerprint `b0d097a4df7c8c3270863b543c756d5fec65c6daed2c2f0d24ae7753098b2a3f` |
| V10 independent replay / hash seed 77 | PASS at fixed revision 330dc3d; fresh regeneration and all independent evaluator continuations matched |
| Chromium file/offline/injection/mobile QA | PASS: six sections, widths 1440/390, zero external requests and zero JS errors |
| New fresh-process matrix | 29/29 PASS at 330dc3d, including identical starting/ending execution revision and input hashes; 14 processes, eight independent checkpoint continuations; all three signature scopes match |
| Bare standard-library environment | Complete 29-check, 14-process matrix PASS; no model, numeric or test libraries installed |
| Existing V6 stability profile / seed 23 / hash seed 77 / 390 days | PASS again at fixed 330dc3d; reconstruction and inspection preserve authority/input; no retained history removed |

The browser initially failed to launch because the container lacks system NSS/
NSPR/AT-SPI libraries. The unchanged browser QA passed with
`LD_LIBRARY_PATH=/tmp/v10-browser-libs/extracted/usr/lib/x86_64-linux-gnu`,
using previously extracted local dependencies. A first library-path retry pointed
at the parent directory and likewise could not launch; neither environment
failure was represented as a browser product failure or successful check.
CI installs the required Chromium system dependencies normally.

Runtime: Python 3.13.11,
pytest 8.3.4, Ruff 0.16.10, Node 20.20.2, Playwright 1.63.0; Linux, CPU-only,
FakeLLMClient, no weights downloaded. CI retains Python 3.11.

The required frozen authoritative digest remains:
`9aec1a80d08364b98816a0607c719933ff41420abedf99e49e929c5b6f0760df`.
No golden output was updated.

## Performance interpretation and CI

The upstream benchmark remains the long-horizon measurement implementation.
Its real V6 profile runs 390 days with retained authority and daily population,
location, institution, event, transaction, activity and save-size observations.
The new replay report adds process-isolated reconstruction costs, save count/
time, simulation time per day, causal trace latency, combined signature/public
projection latency, final history counts, file bytes and process peak RSS
(KiB on supported Linux runners). None is an absolute wall-clock gate.
Resource peaks cover process lifetime; parallel local work distorts timings.
No algorithmic optimization or history truncation is justified by one noisy run.

Observed uninterrupted worlds in the new matrix (one concurrent local sample):

| World | Save bytes | Transactions / activities | Total simulation s | Causal trace s | Peak RSS KiB |
| --- | ---: | --- | ---: | ---: | ---: |
| Legacy, 30 days | 942,080 | 32 / 136 | 1.665 | 0.074 | 42,404 |
| Procedural, 180 days | 7,462,534 | 243 / 1,174 | 93.015 | 0.407 | 88,988 |
| Collective, 100 days | 3,503,470 | 118 / 537 | 15.103 | 0.099 | 62,112 |

The repeated 390-day profile at fixed revision 330dc3d observed **188.077 s**
(0.482 s/day), 780 saves taking 86.396 s, reconstruction 0.380 s, public
projection 0.718 s, and peak RSS 150,152 KiB. Its authoritative signature was
`272afa4d3309bd2beb3ab91b73e50606d01171d7577dc49b0318385358a982b8`,
identical to the earlier sample. Save size grew from 74,240 to 15,390,426 bytes;
population 4→8, locations 4→8, institutions 0→3, daily events 1→390,
transactions 1→302, and activities 4→2,854.

An earlier identical profile under heavier concurrent load took 413.198 s
(1.059 s/day), including 192.509 s saving. The large timing variation without
an authoritative-signature change demonstrates why these observations do not
set an absolute CI performance threshold. Whole-save serialization remains
proportional to retained history and accounts for a substantial observed cost.
No history was removed. Future optimization should profile serialization and
full-history audits before changing retention policy; public inspection already
reuses one graph per checkpoint rather than rebuilding it per query.

CI retains independent fast inspection, full pytest, both freeze modes, V8,
V9, V10 generation/replay/browser, joined integration regressions and existing
stability jobs. A second complete 29-check matrix passed in a bare Python virtual environment
without Torch, Transformers, NumPy, pytest or Ruff. The three new replay jobs
therefore install no Python packages; their engine/evaluation path uses the
standard library and FakeLLMClient. Existing full-suite adapter dependencies
and tests are retained. The added matrix has exactly three model-free replay jobs,
`fail-fast: false`, and no dependency on other jobs. Its 20-minute job deadline
and 900-second worker deadline bound evaluation. Only `outputs/replay.json` is
uploaded for seven days. Temporary private saves, narrative and uncontrolled
worker logs are never artifacts. V10 package exports remain public projections.

Implementation-head CI is tracked in
[run 39072445799](https://github.com/takahashijake/LLM-Town/actions/runs/39072445799).
At evidence preparation, 12/14 jobs passed and full pytest/comprehensive freeze
were still running, with no failures. Earlier runs using the pre-integration
12-gate expectation are superseded. The final evidence/CI-only commit preserves
implementation source hash
`884bdf326248e7c049803bef5e7bee5dc86ca50f3d8bef666c71d7a0c67c4b91`.
Its exact ending SHA and final-head CI conclusion are recorded in
[PR #9](https://github.com/takahashijake/LLM-Town/pull/9) and the
[branch checks](https://github.com/takahashijake/LLM-Town/actions?query=branch%3Av10.1-release-assurance).
Do not infer remote success from this local table.

## Ordered integration plan and observed disposition

External activity completed the required original order; no PR was merged by
this task. Do not attempt to merge already merged feature PRs again.

| Stage | Actual merge into main | Independently observed post-merge CI |
| --- | --- | --- |
| V8 #5 | `fe577fe111c4645b950efc3e9b24272a49e10cde` | run 39071472049 completed successfully; a separate run was still executing at inspection |
| V9 #6 | `d44bd3bfb09ddb10930fe5f0e82d93f59a8fd895` | push run 39072444399 in progress at inspection |
| V10 #7, including assurance #8 | `2baed38cec383c0426b0786f5ff03bc2704cb471` | push run 39072517266 queued at inspection |

Those are observed conclusions, not inferred success from predecessor branches.
Exact predecessor heads remain ancestors. Current main's tree equals the
integrated V10 dependency, and the read-only QA merge calculation equals the
fixed 330dc3d implementation tree. The final PR update records fresh conclusions.

The remaining integration steps are:

1. Re-fetch main, QA #9's head, review threads and branch/ruleset policy. If the
   target changed, inspect its changes and recalculate the integration tree;
   repeat affected correctness/replay gates against that actual candidate.
2. Review QA #9's focused diff against main, require every final-head independent
   CI job to pass, and obtain any required maintainer reviews. Preserve the
   previous feature and assurance history; do not duplicate or revert it.
3. Only an authorized maintainer then merges QA #9. Run
   `python scripts/verify_release.py --output NEW_DIRECTORY` against the resulting
   main commit, and record its exact merge SHA and actual CI conclusions.

Do not force push, rewrite shared branches, bypass protection, automatically
merge a draft, or equate a feature-branch pass with post-integration assurance.
Both original main and re-fetched main at 2baed38 reported `protected: false`,
required status checks off, and the repository ruleset list was empty. QA #9
had no review submissions or review threads at the latest inspection. Absence
of enforced policy is not a reason to skip independent release review.
