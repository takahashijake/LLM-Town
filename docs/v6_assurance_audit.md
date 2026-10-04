# V6 assurance audit

## Starting state

Audited `main` at `ef09becadf3e6ffc819acb532ec5a7f8391e19f3`
(`Reject authority fields in legacy proposal records`), following
`99512e1062271336fa3e378d6a26845560645b95`.
The working tree was clean, with no pre-existing untracked files.

`python -m pytest -q`: **841 passed**, 812.52 seconds.
`python -m compileall -q src scripts tests`: **PASS**.

| Baseline evaluator script suffix | Scenarios | Invariants | Status |
| --- | ---: | ---: | --- |
| v3_freeze | 25/25 | 9/9 | PASS |
| v4_freeze | 71/71 | 16/16 | PASS |
| v5_freeze | 10/10 | 11/11 | PASS |
| growth_proposals | 28/28 | 7/7 | PASS |
| procedural_events | 16/16 | 3/3 | PASS |
| procedural_institutions | 20/20 | 4/4 | PASS |
| procedural_commerce | 63/63 | 7/7 | PASS |
| population_growth | 43/43 | 14/14 | PASS |
| location_growth | 42/42 | 16/16 | PASS |
| event_ecology | 28/28 | 21/21 | PASS |
| institution_growth | 30/30 | 22/22 | PASS |
| commerce_growth | 45/45 | 17/17 | PASS |
| multi_site_growth | 48/48 | 28/28 | PASS |

Run each as `python scripts/evaluate_SUFFIX.py`. The V5 freeze evaluator also
runs the frozen economy, materials, production, crime, justice, commitments,
causal-memory and V2 gates, alongside V3/V4 and multi-site growth.

## Architecture findings

The existing template namespaces and target selectors already support multiple
generated branches. A two-branch probe on unchanged main completed both commerce
lifecycles. The feature gap was integrated assurance, rather than a missing
arbitrary economic contract. Static Garden and Pavilion templates remain exact
and separate; the generator receives display semantics without authoritative
identities. Admission ordering correctly separates templates from activation.

Weak boundaries were persistence shapes, unchecked valid role references,
commit-time material failures, growth-memory place/time/owner validation, and
historical evidence retention when the bounded occurrence window fills.

## Defects and regressions

| Root cause | Corruption or failure | Fix | Regression coverage |
| --- | --- | --- | --- |
| Purchase preflight assumed the goods commit could not fail | Exception after payment or lot movement left money/goods partially committed | Coordinated in-place material and monetary rollback, then re-raise | `test_material_commit_rollback.py`; integrated generated procurement/purchase failures |
| Production preflight assumed input mutation could not fail | Exception after consuming input lots left partial lineage/holdings | Restore lots, holdings, histories, guards and counters | `test_material_commit_rollback.py`; integrated generated production failure |
| Growth memory checked source existence but omitted place/time and containing owner | Valid other-branch source, pre-activation claim, or another resident's private memory | Exact activation day/place and owner-container binding, plus existing private owner checks | Integrated recomputed-ID memory mutation matrix |
| Formation validator checked employment role but omitted the record's role | Replace a formation role with the valid Pavilion role | Bind formation role, employment role and exact template role together | `test_valid_other_role_cannot_replace_formation_role` |
| Constructors truncated persisted review/public histories before validation | Append an old valid review at capacity; slicing hid malformed history | Validate complete input and bounds; trim only during ordinary runtime reviews | `test_load_cannot_truncate_overlong_duplicate_reviews`; generated duplicate mutations |
| Waiting reviews used truthiness for nullable authority | Empty lists/strings or false values masqueraded as absent activation IDs | Require literal null and string identities according to review status | `test_waiting_reviews_require_null_authority` |
| Equality admitted booleans/floats as schema integers; optional dataclass defaults concealed missing persisted fields | Wrong version types, omitted nullable fields, malformed needs | Exact integer schema versions, complete persisted field sets, explicit collection shapes | `test_growth_persistence_contract.py`; field-derived mutation matrix |
| Counter validation rejected rewinds but allowed jumps, and economy/material constructors coerced counter types without binding them to histories | Skip or reuse authoritative migration/location/institution/commerce/ledger/material identities | Exact typed next counters from retained latest/complete histories | Shared sequence tests, `test_material_replay_order.py`, and integrated counter rollback/jump/type mutations |
| Save validation did not uniformly bind child dates to admission | Downstream authority placed on the template admission day | Explicit generated migration/location/event/institution admission ordering | Integrated ordering mutations and observed branch checks |
| Occurrence history discarded old institution proof | After 400 days a completed two-branch save failed to load with invalid institution target selection | Retain earliest eligibility/target-age occurrences and actual formation candidate attendance within the same bounded authoritative registry | `test_event_evidence_retention.py`; integrated 390-day exhaustion/reload |
| Material replay imposed production-before-transfer priority within a tick | Valid same-tick procurement → production → sale failed inventory reconstruction | Order modern events by their sole persisted lot-movement commit sequence; retain legacy priority only for records lacking movement history | `test_procurement_production_and_sale_in_same_tick_replay_in_commit_order`; integrated generated atomic operations |
| Event replay guard covered only the chosen occurrence ID | Historical selection could reconsider other branches; corrupted history could contain two occurrences on one day | Reject historical dynamic selection and duplicate/nonmonotonic occurrence days | Event retention replay regression and integrated historical review replay |

No baseline test failed. These defects were exposed by new probes and attacks.

During implementation, the first integrated signature included legacy UUID
memories and reported false nondeterminism. It now compares authoritative causal
memories and excludes legacy random memory identities. Adding a separate owner
audit key also broke an existing evaluator's fixed invariant-count expectation;
the stronger owner-container check now lives in its existing `known_owners`
invariant, preserving the evaluator contract. An initial comprehensive-fork
implementation also shared the resumed save path and caller random state; code
review corrected it to an isolated fork file with restored random state. The final
34 independent continuations validate the corrected path. No acceptance assertion
was weakened.

## QA surface

The integrated evaluator hydrates real saved engines for field-shape corruption,
valid-but-wrong-branch references, coherent proposal/template rebindings, missing
parents, digest/payload/kind/status/schema/counter attacks, and causal-memory
forgeries. For corruption loads only, journals and noncausal UUID memories are
removed from the real saved fixture; a control load verifies intact authority.
All causal memories and authoritative systems/records remain present. This keeps
the CI gate practical without replacing real simulation or persisted authority.
It observes real proposal, activation, occurrence, formation,
procurement, production and revenue boundaries. The model-free provider supplies
semantics only. A throwing and counting provider verifies reconstruction and
exhaustion without masking swallowed provider exceptions.

The normal mode reloads at every distinct boundary in one trajectory and compares
its final authority with repeated uninterrupted worlds. Comprehensive mode also
forks every positive checkpoint and continues it independently. Shared audits
reconcile ledger balances, material quantities, transfers, consumption, output
lineage, lot movements and owner-scoped memories. Generated branch B transaction
failures must preserve existing branch A authority.

The checked-in `data/` configuration is unchanged. Existing default V5 acceptance
remains a separate regression gate. No real model, network service or external
fuzzing dependency is needed. See [the freeze contract](v6_freeze_candidate.md)
for commands, limitations and optional model smoke.

## Final verification

- `python -m pytest -q`: **942 passed**, 1120.39 seconds (18:40).
  This adds **101 regression/integration test cases** across seven new test files.
- `python -m compileall -q src scripts tests`: **PASS**.
- All thirteen baseline evaluator scripts above: **PASS** with the same scenario
  and invariant counts, except procedural commerce now has **10/10** shared
  conservation/provenance invariants instead of 7/7.
- `PYTHONHASHSEED=1 python scripts/evaluate_v6_freeze.py --output /tmp/v6-final-freeze.json`:
  **77/77 scenarios, 42/42 invariants, 35/35 replay checkpoints,
  730/730 adversarial mutations rejected**.
- `PYTHONHASHSEED=77 python scripts/evaluate_v6_freeze.py --comprehensive --output /tmp/v6-final-comprehensive.json`:
  **77/77 scenarios, 42/42 invariants, 69/69 checkpoint checks,
  730/730 adversarial mutations rejected**. These include 35 reconstruction
  checks and 34 independent continuations to the same final authority.
- Both modes/independent Python hash seeds produced the same authoritative digest:
  `9aec1a80d08364b98816a0607c719933ff41420abedf99e49e929c5b6f0760df`.
- The 390-day scenario fills the 64-occurrence bound, reloads without provider
  calls and retains valid historical institution proof.
- Optional model adapter/CLI and strict parser were checked with bounded test
  output. Real local-model weights were not run; this remains optional.
- `git diff --check`: **PASS**. No checked-in `data/` or output fixtures changed.
- HEAD remains `ef09becadf3e6ffc819acb532ec5a7f8391e19f3`.
  No commits or pushes were made. The working tree contains only the intended
  16 modified files and 13 new implementation/test/documentation files.
