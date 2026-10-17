# V10.1 fresh-process integration assurance

This document supplements [the integrated V10.1 assurance record](v10_1_release_assurance.md).
It describes the complementary work in PR #9. Verification remains incomplete
until the execution table and final-head CI evidence below are complete.
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

Ending implementation revision and final delivery revision are recorded with
the final execution evidence and PR metadata; a document cannot contain its
own commit hash. Review `git log --oneline origin/v10-town-observatory..HEAD`
and `git diff origin/v10-town-observatory...HEAD` for the complete history and
focused resulting change.

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
stdout/stderr. An existing output file is rejected before simulation begins.

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

Execution table: **pending integrated completion**. Runtime: Python 3.13.11,
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

CI retains independent fast inspection, full pytest, both freeze modes, V8,
V9, V10 generation/replay/browser, joined integration regressions and existing
stability jobs. The added matrix has exactly three model-free replay jobs,
`fail-fast: false`, and no dependency on other jobs. Its 20-minute job deadline
and 900-second worker deadline bound evaluation. Only `outputs/replay.json` is
uploaded for seven days. Temporary private saves, narrative and uncontrolled
worker logs are never artifacts. V10 package exports remain public projections.

Final-head CI status: **pending**; local success is not remote success.

## Ordered integration plan

1. Re-fetch every head, base and review/check state before acting. #5 was merged
   externally; verify the actual new main, including its complete required gates.
   Its initial post-merge tree equals V8, but a tree comparison is not a CI result.
2. Keep #6 targeted to the actual updated main. Inspect conflicts and reviews,
   verify its integration against that exact target, and rerun full pytest,
   freeze and domain gates before an authorized maintainer merges V9.
3. Review and integrate QA #9 into V10 only after its final-head independent
   checks pass. Preserve draft #7 until a maintainer explicitly approves readiness.
4. After V9 actually reaches main, retarget V10 (including #8 and #9) to that
   freshly fetched main. Revalidate ancestry, conflicts, private/public boundaries,
   full suite, both frozen digests, every showcase, independent replay and browser
   QA against the actual integration candidate. Obtain any required reviews.
5. Only an authorized maintainer then merges V10. Rerun release verification on
   the resulting main commit. Record final merge SHAs and actual CI conclusions.

Do not force push, rewrite shared branches, bypass protection, automatically
merge a draft, or equate a stacked-branch pass with post-integration assurance.
The observed original main had `protected: false`; absence of enforced checks
is not authorization to skip release review. Recheck current policy at each stage.
