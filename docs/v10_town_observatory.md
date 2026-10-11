# V10 Town Observatory

V10 is a read-only, offline product slice stacked on the open V9 and V8 pull
requests. It makes real town histories explorable without giving presentation or
generated language any authority over a town.

## One-command demonstration

From the repository root, install the existing runtime/test dependencies (or run
`./setup.sh`), then:

```bash
python scripts/showcase_town.py --output /tmp/llm-town-v10
```

Use a **new directory**. Open `/tmp/llm-town-v10/index.html` directly in a browser.
No server, model download, GPU, telemetry, CDN, account or network is used by the
report. Data, CSS and JavaScript are embedded; there is no local `fetch` request.
Generation runs trusted existing evaluators in temporary directories and removes
all raw saves, private narrative and runtime logs when done.

The canonical seed-11 garden world runs 100 days at 08:00 with V9 enabled. It
starts with four residents and four public places; the actual trajectory admits
two residents, activates two locations, forms a garden institution and job, and
executes procurement/production/purchases and civic work. The garden project
activates on day 70; four residents contribute on days 72, 75, 82 and 84. Completion
unlocks the workshop on day 85; six subsequent workshop sessions execute. These
are demonstrated outcomes of this seed, not guaranteed outcomes of every seed.

The **separate** existing V8 seed-23, 180-day two-branch fixture supplies stronger
commerce evidence. Its bounded deterministic proposal provider proposes semantic
templates; ordinary deterministic rules still admit and activate them. The two
worlds are never joined into a fabricated history. No commitment or legal incident
is invented for either scenario. Existing evaluators retain broader legal,
planning, commitment and corruption coverage.

## Files

| File | Purpose |
| --- | --- |
| `manifest.json` | Schema 1, revision, public fingerprint, exact file hashes/sizes |
| `index.html` | Self-contained, responsive report |
| `observatory.json` | All public checkpoint data and selected verified traces |
| `garden-initial.json`, `garden-final.json` | Initial/final authoritative public projections |
| `garden-formation.json`, `garden-one_contribution.json`, `garden-before_completion.json`, `garden-after_completion.json` | Meaningful intermediate checkpoints |
| `commerce-commerce_before.json`, `commerce-commerce_final.json` | Separately labeled fixture snapshots |
| `*-timeline.json` | Sanitized final chronological record projections |
| `*-traces.json` | V8/V9 causal reports, including uncertainty |
| `*-comparison.json` | Initial/before versus final state differences |
| `walkthrough.txt` | Concise evidence-backed tour and replay command |
| `benchmark.json` | Local durations/size; excluded from reproducibility hashes |

Public snapshots are **inspection artifacts, not engine save files**. No second
persistence model is introduced: simulation saves remain owned by
`SimulationState`. The package deliberately cannot disclose or restore private
memories. Independent verification regenerates the actual engine saves in
transient storage and resumes them through the existing engine.

## Exploration and definitions

Choose the scenario and checkpoint in the persistent toolbar. The six views are:

1. Town overview: metrics with expandable authoritative sources and definitions,
   plus buttons for the meaningful checkpoint sequence.
2. Timeline: category/day/exact-entity filters and bounded pages. Each row retains
   its subsystem path and persisted source ordinal.
3. Entities: resident IDs and current public location, activated locations,
   institutions, accounts/balances, employment/wages, inventories/quantities,
   sellers and civic projects. Exact-ID event links are associations only.
4. Causal investigation: typed dependency edges, associations, ownership facts,
   project requirements/progress, and explicit missing evidence.
5. Comparison: metric differences, added/removed entities and changed public
   contract/status fields between any two checkpoints in the same scenario.
6. Reproducibility: executed evaluator checks, signatures, revision and a trusted
   independent replay command.

Population counts unique saved IDs, employment counts active contracts whose start
day has arrived, and activity counts include saved executions without claiming
success. Currency and gross money flow require ledger reconciliation. Production
requires reconciled material history and verified production edges. Exchanges
require reconciliation **and both reciprocal verified goods/payment legs**. Civic
contributions/effects/workshops require the V9 audit and explicit dependency edges.
Unknown metrics are `null`, never an invented zero. Missing registry references
are reported; contradictory public identities and ownership fail closed.

## Architecture and authority

```text
Existing seeded evaluators -> SimulationEngine -> deterministic systems
                                  |                  |
                                  +-- SimulationState saves
                                               |
                                  bounded JSON validation
                                               |
                           V8 graph + V9 authority audit
                                               |
                          pure public checkpoint projection
                               /               \
                 structured JSON          escaped embedded data
                                               |
                                  offline read-only interface
```

`observatory.py` validates, aggregates, projects and compares. Existing
`inspection_save`, `inspection_records` and `causal_*` contracts supply JSON
budgets, privacy allowlists, typed indexing and verified evidence. The graph now
retains its existing replay audit results for reuse by metrics; trace serialization
and signatures remain unchanged. Each checkpoint builds one graph for all queries
and performs each ledger/material replay once. `observatory_presentation.py` only
assembles the document. Local assets hold presentation code. `town_showcase.py`
owns trusted generation, temporary-storage lifecycle, export and independent
verification. Neither projection nor rendering constructs a simulation system.

LLM dialogue can propose behavior and supply narrative; it cannot mint residents,
money, goods, jobs, crime, commitments, civic work or world transitions. The report
exposes deterministic records only. It excludes memories, beliefs, journals,
prompts, dialogue, private goal prose, free-text record fields and UUID-bearing
social histories. Trusted finite scenario configuration is included separately
from saved-state projections and is not interpreted as executable instructions.

## Evidence and uncertainty

A **verified dependency** checks an existing typed persisted contract. An
**association** identifies authoritative records sharing an exact identifier; it
makes no causal claim. **Unresolved evidence** records missing, conflicting or
unsupported witnesses. Names, dates, locations and descriptive text never prove
causality. Same-time source order is deterministic presentation order; ledger and
material commit sequences retain their authoritative order. Lists are not
reordered before audits. Reordered replay records invalidate proofs; changes to
source ordinals can change report fingerprints even when some current facts agree.
JSON object insertion order does not change serialization.

Formation eligibility witnesses that upstream saves did not persist remain
unresolved. A coherent forged save can be internally consistent: neither the V8
inspector nor the manifest certifies cryptographic authenticity. Independent replay
provides a stronger reproducibility check against trusted repository scenarios.

## Independent verification

```bash
PYTHONHASHSEED=77 python scripts/showcase_town.py --verify /tmp/llm-town-v10
```

The package must match the recorded repository revision and current input files.
Verification first rejects malformed manifests, unknown schema, missing/modified
files, unsafe filenames, symlinks and oversized artifacts. It then regenerates both
scenarios in fresh subprocesses, including V9's four independent checkpoint
continuations and V8's 90+90 reconstruction, and compares the complete deterministic
manifest. No command is ever taken from a loaded package.

The V9 evaluator's authority signature covers economy, materials, population,
locations, events, institutions, commerce, collective projects, crime, justice,
commitments, plans, growth proposals, public activity behavior, needs, relationships,
goals, intents and town arcs. Private UUID memories/narrative are excluded. This
is a seeded fake-LLM reproducibility contract, not a guarantee about stochastic
real-model text or arbitrary seeds. Use an unchanged checkout when verifying.

## Inspect your own save

```bash
python scripts/inspect_town.py report SAVE.json --before EARLIER.json --output /tmp/town.html
python scripts/inspect_town.py report SAVE.json --output /tmp/project.html \
  --type project --id civic-project:garden_learning
```

Inspection performs no transitions, inference, save migration or writes to the
input. Without explicit `--base-location ID` arguments, total active-location
count is unknown: a legacy save does not persist the base registry, so the
inspector refuses to infer it from local configuration. Public facts and causal
queries retain upstream limitations. Existing `timeline`, `show`, `trace` and
`compare` commands keep their behavior.

## Limits and performance

Inherited validation: 64 MiB save input, 2 million JSON nodes, nesting depth 64,
200,000 records per collection, 1-million-character string cap, finite numbers.
V10: 12,000 aggregate public/causal rows, 6,000 timeline events, 1,024 entities,
16 selected traces; each trace depth 6 and limit 150; 4 MiB per checkpoint,
16 MiB HTML, 32 MiB package and fewer than 64 files. Excess fails closed without
silent truncation. Timeline pages contain 20 rows; entity association previews
show the first 50 with the total count. Traces retain explicit truncation flags.

Each trusted evaluator subprocess has a 300-second execution deadline. The
arbitrary-save `report` CLI has a 60-second worker deadline; pure APIs use the
structural budgets rather than process cancellation. JSON uses ASCII escapes;
embedded `<`, `>` and `&` cannot break script context. UI rendering uses only DOM
nodes and `textContent`, with a network-blocking CSP. Output paths are selected by
the caller, not save contents; existing output files/directories are refused.

Generation costs dominate projection/rendering. The graph is built once per
checkpoint, instead of once per causal query; audit results eliminate duplicate
replay scans. Selecting example production lots is a single pass. Projection
sorting is O(n log n); authority audits retain their upstream costs. Checkpoint
histories repeat in the self-contained bundle to make each state independently
inspectable; the bounded export trades a modest file size for clarity. No
unbounded dashboard history or browser-side simulation is introduced.

Exact measured gates and runtimes belong in
[v10_freeze_candidate.md](v10_freeze_candidate.md). CI keeps full pytest and both
freeze modes, adds fast Observatory tests and a separate canonical package +
hash-seed replay + real Chromium file-protocol/injection/responsive gate. Browser
QA installs Playwright only in that job; runtime dependencies are unchanged.

## Limitations and next priorities

This report covers bounded seeded worlds, not an interactive simulation editor,
real-time server, map, unrestricted civilization engine or proof of all social
outcomes. No cross-scenario causal joins are supported. General social/private
knowledge and legal evidence are intentionally outside the public projection.
Longer histories must fit explicit budgets; whole-save growth remains upstream.
Future work should persist historical eligibility witnesses, broaden audited
public legal/commitment fixtures and offer compact history paging without
weakening authority or privacy.
