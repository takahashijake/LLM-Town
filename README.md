# LLM-Town

The current v1 verification record is in
[`docs/v1_freeze_report.md`](docs/v1_freeze_report.md).

LLM-Town is a persistent, text-based social simulation in which four residents
plan activities, pursue goals, remember events, and hold bounded multi-turn
conversations. It uses a hybrid architecture: deterministic code owns simulation
state and applies validated effects, while a local language model realizes
grounded dialogue. The model never receives arbitrary authority to mutate state.
V1 remains frozen; V2 integrates deterministic economy, material production and
provenance, crime/evidence, and justice without changing that boundary.

## Key capabilities

- Bounded, alternating conversation sessions (four utterances by default)
- Per-speaker context boundaries for memories, journals, goals, intents, and beliefs
- Deterministic semantic-action inference and conservative response outcomes
- Separate semantic action records and effect eligibility/rate limiting
- One bounded anti-echo regeneration attempt on the real-model path
- Persistent memories, daily journals, goals, intents, and adaptive goal strategies
- Persistent bounded plans whose steps invoke existing authoritative actions
- Directional relationship state plus a compatible shared relationship score
- Direct reputation observations and provenance-preserving hearsay
- Needs, occupations, activity planning, daily events, and town arcs
- Authoritative integer accounts, employment, wages, and an auditable ledger
- Closed-system currency conservation and idempotent daily wage events
- Persistent goods, inventory ownership, atomic purchases, and consumption records
- Configured material transformation, bounded restocking, and batch provenance
- Unauthorized material transfers, auditable theft incidents, and private evidence
- Deterministic witness opportunity and provenance-preserving crime hearsay
- Deterministic investigation, adjudication, restitution, and public consequence
- Save/resume semantics, isolated deterministic benchmarks, and real-LLM review artifacts
- A deterministic automated test suite that does not load or download a model

The repository implements the economic, material, narrow theft/evidence, justice,
and production/provenance foundations described below. General policing, courts, other crime types, debt,
taxes, dynamic markets, romance, factions, politics, a GUI, and semantic vector
memory remain outside the current scope.

## Architecture overview

```text
persistent agents
      ↓
needs / goals / planning
      ↓
activities
      ↓
work ───────────────→ wages
      ↓
production
      ↓
material lots / inventory
      ↓
purchase / ownership
      ↓
unauthorized theft
      ↓
observation / evidence
      ↓
justice
      ↓
restitution + reputation consequence
      ↓
future social context / behavior
```

Accounts, inventories, lots, incidents, evidence, cases, and consequences are
authoritative deterministic state. Agent knowledge is a bounded view acquired
through participation, observation, transmission, discovery, or public
adjudication. Public information is an explicit transition, not global access to
system records. LLM-generated dialogue receives only the current speaker's
bounded context and cannot invoke authoritative mutation APIs.

```text
agent state + town state + deterministic policy
                    |
                    v
        bounded, speaker-private context
                    |
                    v
       local LLM -> JSON dialogue proposal
                    |
                    v
 parsing -> semantic validation -> action + response outcome
                    |
                    v
 effect eligibility/deduplication -> deterministic state updates
                    |
                    v
 logs + session memory + journals + save state + evaluation
```

Dialogue never transfers money, goods, or ownership, and cannot create employment,
crime incidents, witnesses, evidence, cases, adjudications, or consequences.
Economic mutations can only
enter through `EconomySystem.transfer`, which validates stable account IDs,
positive integer amounts, distinct participants, available funds, and idempotency
keys before atomically replacing balances and appending a transaction. Material
mutations enter through `MaterialSystem`, whose exchange and consumption APIs use
configured goods, prices, owners, and activity rules.

Important directories:

```text
src/actions/       action vocabulary and deterministic inference
src/agents/        agents, goals, intents, memories, relationships
src/behavior/      activity, goal, intent, and social policy
src/llm/           prompt construction, local-model client, parser
src/simulation/    orchestration, sessions, effects, persistence, town arcs
src/systems/       economy, materials, crime/evidence, justice, and reputation
src/analysis/      benchmarks, metrics, and real-LLM review artifacts
tests/             deterministic unit and integration tests
```

## How a conversation works

At a shared location, deterministic policy selects a pair and prepares context for
the current speaker only. The first turn can choose a grounded focus. Follow-up
turns are prompted to answer or acknowledge the immediately preceding utterance
before changing topic. Each turn is parsed and checked against conservative action
language rules.

The recorded `final_action` describes what the line means. Effect eligibility is a
separate decision: an `offer_help` can remain an offer even when its relationship,
need, reputation, goal, intent, or town-arc effects are suppressed by a rate cap or
same-session deduplication. This preserves listener response and audit semantics
without allowing repeated actions to amplify state changes.

Offers, requests for help, and cooperation proposals receive deterministic,
conservative outcomes such as `accepted`, `declined`, `answered`, or `unresolved`.
Sessions stop at the configured bound or on closure, storm-off, generation failure,
repetition, or a policy termination. Each participant receives one session memory;
turn and session diagnostics remain reconstructable from JSONL logs.

## Simulation systems

Agents have needs, occupations, personalities, persistent goals, short-lived
intents, memories, daily journals, recent topics, and directional relationship
profiles. Activity and social policies use those structures to select behavior.
Public daily events and persistent town arcs provide shared context.

Reputation is distinct from pair relationships. Direct observations can update a
listener's belief about an actor; supported claims may propagate as hearsay with
provenance. Private beliefs and memories are rebuilt per speaker and are not copied
into the other participant's prompt context.

State can be saved and resumed. Structured goal evidence supports bounded strategy
selection/adaptation, while deterministic effect guards prevent repeated dialogue
actions from double-advancing goals or relationship state.

## V2 economic foundation

`data/economy.json` maps the four existing stable agent IDs to starting employment,
employer accounts, integer daily wages, and exact qualifying activity IDs. Agent
accounts and employer accounts are seeded once; initialization is the only
non-ledger balance creation. Thereafter all transfers are atomic ledger events in a
closed system, so total currency must remain equal to its initial value.

The activity planner explicitly tags grounded occupational activities as `work`.
After `ActivitySystem` selects and records an activity, `EconomySystem` requires
both that tag and an exact match in the employee's configured job. A successful
shift pays at most once per employment/day from the employer account and produces
a bounded wealth-need improvement. Reprocessing a tick, including after resume,
records a rejected duplicate attempt but cannot add a second ledger record or
change either balance. The legacy `Agent.occupation` field remains available to V1
behavior; authoritative employment is separate economic state.

Accounts, employment, transaction records, work-event evidence, rejection
diagnostics, and idempotency guards are all saved. Loading a V1 save without an
`economy` field deterministically initializes this configuration.

## V2 material foundation

`data/materials.json` defines a small fixed-price catalog, the market stall's stock,
and activity rules. Every agent has a stable inventory linked to its authoritative
account. The market stall is a seller entity with its own inventory and account;
its operator link uses the merchant employment ID rather than an agent name.
Inventory quantities are non-negative integers, and inventory ownership provides
the authoritative answer for fungible and durable catalog goods.

A purchase is one coordinated deterministic operation. It validates the buyer's
inventory/account linkage, seller ownership and location, configured unit price,
positive quantity, seller stock, buyer funds, and idempotency key before changing
state. It then writes a canonical monetary ledger transaction, an inventory
transfer, and an exchange record linking both IDs. All failure checks precede the
two commits, so a rejected purchase changes neither money nor stock. Generated
dialogue cannot supply a price or invoke this path.

The existing activity planner offers conservative `buy_meal` and `eat_meal`
activities. An exact configured purchase activity at the market can buy one meal;
a separate consumption activity succeeds only when the agent owns one. Consumption
removes exactly one item, records the explicit material sink, and applies a bounded
effect to the existing social need. Purchase and consumption guards survive
save/resume. V1 and Phase 1 saves without material state initialize it
deterministically.

The same authority supports one narrow production loop. The configured
`recipe:market_prepared_meals` transforms two finite meal ingredients into four
prepared meals in the market inventory. Only the configured merchant employment,
`restock_market` activity, and market location may invoke it. Production rejects
invalid requirements before mutation. The target of 24 is a pre-batch threshold,
not a hard cap: stock below 24 permits a four-unit batch, so 23 becomes 27. At 24
or above, later batches are rejected. Wages run first, so a legitimate restocking
shift may earn its wage even when the threshold prevents output.

Gameplay inventories remain fungible quantities, while an authoritative batch/lot
ledger tracks provenance. Initial holdings receive stable configuration lots.
Production consumes input-lot allocations and creates distinct output lots linked
to the recipe, production record, and parent lots. Transfers use oldest-created-lot
first with stable lot-ID tie-breaking. Purchases and theft inherit that path;
restitution returns only lots moved by the original theft while they remain with
the responsible actor. Unrelated fungible stock is not labeled as stolen property.
Consumption depletes holdings but retains their lineage in history.

Per-good accounting enforces
`initial + production outputs = current + consumed + production inputs`.
Inventory replay and active lot holdings independently reconcile with authoritative
quantities. Production and provenance state persists exactly; schema-v1 material
saves migrate deterministically by anchoring extant holdings as migration lots.

## V2 theft and evidence foundation

`CrimeSystem` implements one deliberately narrow crime: theft through an explicit
unauthorized inventory transfer. It validates the actor, controlled destination,
prior owner and stock, configured good/value, positive quantity, event guard, and
co-location of the actor and source property. A successful operation moves goods
once through `MaterialSystem`, transfers no currency, creates no exchange record,
and links the resulting transfer to one immutable crime incident. Legitimate
purchase, ordinary authorized transfer, consumption, and unauthorized taking
remain distinct recorded semantics.

Witnessing is deterministic but not automatic. Non-actor agents at the incident
location are potential witnesses; a stable hash rule selects actual observers
reproducibly. Only actual observers receive direct eyewitness evidence and a
private evidence-backed reputation observation. The actor receives private
participation knowledge. A victim who did not observe can later discover a loss
without thereby learning who committed it. Uninvolved agents receive nothing.

Crime evidence records retain incident IDs, holders, source evidence, originating
observer, and transmission chains. Explicit sharing creates hearsay and never
upgrades it to direct observation. Crime state is not injected globally into LLM
contexts. Incidents, opportunities, evidence, discovery, rejection diagnostics,
ID counters, and replay guards survive save/resume; older saves initialize an
empty configured crime layer safely.

## V2 deterministic justice foundation

`JusticeSystem` closes the theft loop without delegating authority to dialogue. A
case opens only from a victim's direct loss discovery or a direct eyewitness
record, references the existing crime incident, and admits references to immutable
crime evidence. Private cases are visible only to their reporter and investigator
until adjudication becomes an intentional public record.

The `theft-direct-eyewitness-v1` rule requires the authoritative unauthorized
material-transfer record to establish theft and one unique actor candidate from
admitted `eyewitness` / `direct_observation` evidence. The transfer record's actor
field is never actor-identifying evidence. Loss discovery, hearsay, accusation,
and reputation cannot support responsibility. Their absence produces
`insufficient_evidence`, not a finding of innocence. Decisions persist the exact
evidence IDs and rule version.

A responsible finding permits one idempotent consequence operation. It returns up
to the stolen quantity still held by that actor using a `justice_restitution`
material transfer, never an exchange or currency transfer. Missing goods produce
`partial` or `unresolved` restitution without minting stock. A separate bounded
public-event trust consequence is keyed to the adjudication and cannot duplicate
the eyewitness penalty. All justice records, counters, diagnostics, and replay
guards survive save/resume; saves without `justice` initialize an empty layer.

## Evaluation and reproducibility

Run an isolated deterministic benchmark:

```bash
python scripts/benchmark_simulation.py \
  --fake-llm --days 10 --seeds 1 2 3 \
  --max-conversation-turns 4
```

Each seed receives isolated logs and save state under `outputs/benchmarks/`. The
benchmark records configuration, input hashes, revision metadata, per-run metrics,
and aggregate results without touching ordinary `logs/` or `data/save_state.json`.
Generated benchmark and evaluation directories are ignored; the compact structured
relationship evaluation under `outputs/prompt5_relationship_evaluation/` is kept as
curated reproducibility evidence.

Run the model-free economic acceptance evaluation:

```bash
python scripts/evaluate_economy.py
```

It writes machine-readable diagnostics to `outputs/economy_evaluation.json` and
checks wage eligibility, duplicate prevention across resume, non-negative
balances, currency conservation, wealth feedback, persistence, and ledger replay.

Run the model-free material acceptance evaluation:

```bash
python scripts/evaluate_materials.py
```

It verifies successful and failed purchase atomicity, seller stock and buyer funds,
configured pricing, ledger/exchange reconciliation, inventory reconstruction,
material conservation with explicit consumption, bounded need feedback, and
purchase/consumption guards across resume.

Run the model-free crime/evidence acceptance evaluation:

```bash
python scripts/evaluate_crime.py
```

It constructs witnessed and unwitnessed thefts, atomic stock and location
rejections, direct-to-hearsay propagation, and a save/resume replay attempt. The
machine-readable result in `outputs/crime_evaluation.json` checks currency and
material conservation, transfer/incident linkage, witness opportunity, evidence
provenance, information boundaries, persistence, and idempotency.

Run the model-free justice acceptance evaluation:

```bash
python scripts/evaluate_justice.py
```

It writes `outputs/justice_evaluation.json` and covers witnessed responsibility,
unwitnessed discovery, hearsay-only accusation, restitution, conservation,
information boundaries, and exact save/resume replay behavior.

Run the production/provenance lifecycle evaluation:

```bash
python scripts/evaluate_production.py
```

It writes `outputs/production_evaluation.json` and checks successful and atomic
failed production, depletion/restocking, produced-lot purchase, theft, restitution,
consumption, accounting, provenance reconciliation, and resume replay safety.

Run the whole-V2 freeze acceptance evaluation:

```bash
python scripts/evaluate_v2.py
```

It writes `outputs/v2_evaluation.json`, returns nonzero on any hard invariant
failure, and exercises an integrated work/wage/production/purchase/theft/evidence/
justice/restitution chain. It also checks an unwitnessed negative case, exact-lot
and unavailable-lot restitution, two-boundary save/resume equivalence,
representative replay attacks, LLM information boundaries, and 30 deterministic
days of state-integrity checks.

Run a controlled real-model evaluation:

```bash
python scripts/evaluate_real_llm.py \
  --days 10 --seed 42 --max-conversation-turns 4
```

The evaluator writes metadata, metrics, a complete session transcript, and review
samples. Diagnostics include semantic versus effect-applied action distributions,
suppression reasons, parser/inference/final disagreements, response outcomes,
adjacent echoes, regeneration, and termination. Potential turn discontinuities
and lexical context matches are review candidates—not objective coherence or
causal-influence scores.

## Quick start

Python 3.11+ is recommended.

For the full local-transformer workflow:

```bash
./setup.sh
source .venv/bin/activate
```

`requirements.txt` contains the local-model runtime stack. Test-only contributors
can avoid installing PyTorch and Transformers:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Run the deterministic fake model (no model download or GPU required):

```bash
python main.py --fake-llm --days 2 --hours 8 12 18 22 --seed 42
```

Run the default local Qwen model after it is installed/cached:

```bash
python main.py \
  --days 2 --hours 8 12 18 22 --seed 42 \
  --model-name Qwen/Qwen2.5-3B-Instruct
```

Use `--load-state --no-clear` to resume rather than clear the ordinary run state.

## Testing

```bash
./test.sh
# or
python -m pytest
```

Tests cover action inference/validation, bounded conversation sessions, echo retry,
effect suppression and deduplication, context privacy, response outcomes, memories,
journals, needs, activities, goals/intents, directional relationships, reputation,
town arcs, economic accounts/employment/wages, goods/inventory/exchange/consumption,
theft incidents/witness opportunity/evidence provenance, deterministic justice,
restitution/consequence replay safety, persistence/resume,
reporting, benchmarks, and evaluation artifacts.
CI installs only `requirements-dev.txt`, uses the fake/model-free paths, and never
downloads Qwen or requires CUDA.

## Post-V2 / V3 behavioral development

The `v2.0.0` world remains frozen. Post-V2 work improves agent behavioral
fidelity without changing the central authority boundary: generated dialogue may
suggest bounded choices, while deterministic systems validate and own every
state effect.

Conversation context now exposes prompt-local grounding references for supplied
memories, relationship events, public events, reputation claims, journals, and
town arcs. Deterministic checks use them to flag a narrow set of high-risk
unsupported-claim candidates, retry generation at most once, and otherwise use a
safe fallback. This is a bounded heuristic, not natural-language theorem proving.
Reference IDs are metadata and never belong in spoken dialogue.

Reputation now influences only existing social-target selection, through an
observer-private confidence-weighted adjustment capped at `-2.0` to `+2.0`.
Relationships and current intent remain important, negative reputation never
makes selection impossible, and positive reputation never guarantees it.
Dialogue remains probabilistic. Deterministic correctness is covered by the
model-free social-decision evaluator; real-model quality is evaluated separately.

### Persistent social commitments

V3 adds a deliberately narrow authoritative ledger for `help`, `meet`, and
`transfer` agreements. Dialogue is only evidence: a record is created when a
bounded proposal identifies both parties and a concrete action, and the existing
multi-turn response resolver finds a clear acceptance or decline. Vague proposals
or replies remain unresolved and create no active promise.

```text
finalized dialogue/action -> conservative response resolution -> commitment ledger
                                                              -> compact future context
authoritative activity/material event ------------------------> terminal resolution
                                                              -> bounded social effect
```

Legal transitions are `proposed -> accepted|declined|cancelled|expired` and
`accepted -> fulfilled|cancelled|failed|expired`; terminal records cannot be
reopened. Due commitments expire deterministically after the configured zero-day
grace window. A material promise is fulfilled only by a successful atomic
`MaterialSystem.transfer_good` record, never by dialogue claiming success.
Terminal effects are idempotent and small (at most one legacy relationship point
and a bounded direct reputation observation). The ledger, stable ID counter,
semantic evidence keys, resolution provenance, and effect guard are included in
normal save state, so resume neither duplicates nor resets commitments.

Run the deterministic evaluator with:

```bash
python scripts/evaluate_commitments.py
```

Run the controlled real-model A/B evaluator (same scenarios, seed, and prompt
grounding with commitment-aware execution pressure disabled/enabled) with:

```bash
python scripts/evaluate_commitments_real.py --model-name Qwen/Qwen2.5-3B-Instruct --seeds 42 73
python scripts/evaluate_commitments_real.py --model-name Qwen/Qwen2.5-7B-Instruct --seeds 42 73
```

Accepted commitments also produce ephemeral action opportunities for the
obligated agent during ordinary activity selection. Opportunity feasibility is
checked against the current agents, locations, date, material inventory, and
same-window attempt history. Phase 3 replaces the shallow selection coin flip
with an inspectable bounded priority comparison: urgency and current-due status
raise commitment pressure, prior attempts reduce it, and the strongest current
need, intent, or event remains a real competitor. A bounded stochastic
adjustment permits intelligible lapses without making every promise succeed.
Activity records retain the pressure, competitor, adjustment, feasibility, and
decision reason.

For a missing transfer resource, the derived opportunity may select a narrow
preparatory purchase only when an already configured active seller has the real
stock, the obligated agent has sufficient funds, and the existing location,
price, inventory, provenance, and conservation checks all pass. There is no
resource minting and no fabricated acquisition route. Selected help, meeting,
transfer, and preparation activities retain their `source_commitment_id`;
fulfillment still occurs only after co-located authoritative activity execution
or an atomic material transfer succeeds. Feasibility opportunities are
reconstructed each cycle from current authoritative state; the bounded causal
plan and completed-step evidence persist.

Expired, failed, and explicitly cancelled commitments produce a pair-private
repair opportunity for two days. It can focus later dialogue on acknowledgment,
apology, or a concrete replacement proposal, but it cannot rewrite the terminal
record. Explicit cancellation is conservative: only the obligated speaker,
talking to the original proposer, can cancel an active promise with language
that both states inability/refusal and identifies its terms. Exact session/turn
evidence makes cancellation idempotent.

A replacement follows normal proposal and clear-acceptance resolution. The new
record has its own ID and an explicit `repair_of_commitment_id`; its terminal
predecessor remains immutable and retains its social consequence. Cyclic or
missing lineage is rejected, as are successor links that change the original
participant pair or bounded commitment type. Production dialogue is also checked against only
the pair-private commitment records supplied to that speaker. A clear status
contradiction receives at most one regeneration, followed by a neutral fallback;
dialogue can never fulfill a promise.

Run the deterministic execution funnel with:

```bash
python scripts/evaluate_commitment_execution.py
python scripts/evaluate_commitment_accountability.py
```

The real-model script now compares prompt grounding alone against the same
grounding plus commitment-aware execution pressure, and reports the full
accepted → candidate → feasible → selected → executed → fulfilled funnel.
Phase 3 adds cancellation, repair-opportunity, successor-lineage,
authoritative-contradiction, false-fulfillment, and persistence scenarios.

### Persistent bounded plans

Plans provide temporal continuity without giving either dialogue or an LLM a task
queue. A goal describes a durable desired outcome; an intent is a short-lived
behavioral strategy; an activity is the single action selected for a tick; and a
commitment is a social obligation between two agents. A plan is narrower: a
small, deterministic sequence of known activity types linked to one authoritative
source. The current template exists only for accepted transfer commitments and
contains at most an acquisition step followed by a delivery step.

```text
accepted transfer commitment
        -> persistent plan (source ID + owner + bounded steps)
        -> current-state feasibility and bounded priority comparison
        -> one selected activity
        -> economy/material/commitment authority executes or rejects it
        -> execution proof advances exactly one step
        -> terminal plan + pair-private causal memory
```

Plan IDs and step IDs are stable. Active, completed, failed, and abandoned states
are persisted; terminal plans cannot resume. Steps name only registered action
types and cannot directly edit inventory, money, commitment status, relationships,
or memory. A missing resource can produce an acquisition candidate only from an
existing active seller with stock and at a price the agent can pay. Three distinct
blocked observations exhaust the current retry budget. A cancelled, fulfilled,
expired, or otherwise incompatible source invalidates its active plan before the
next action. Execution keys make resume/replay idempotent.

For example, Maya accepts a promise to bring Ethan one trade material. On day 2
she lacks it, so the plan selects an authorized market purchase; the material
system debits her account and transfers an existing unit with provenance. At a
later tick the persisted plan selects delivery; the material system transfers the
exact owned unit and the commitment system records fulfillment proof. Both parties
receive typed, pair-private memories grounded in those records. No dialogue line
causes either transfer.

The deterministic planning evaluator covers success, legitimate interruption and
resume, bounded resource failure, save/resume, terminal-source invalidation,
information boundaries, replay idempotency, memory provenance, and cleanup:

```bash
python scripts/evaluate_long_horizon_planning.py
```

This evaluator proves authoritative behavior without loading a model. Real-model
evaluation remains a separate measurement of whether generated dialogue notices
and verbalizes supplied grounded state; fluent text is never treated as execution
proof.

## Causal knowledge and historical recall

World records and agent knowledge are deliberately separate. Economy balances,
inventories and provenance, commitments, plans, crime/evidence, and justice
records are authoritative state. `OutcomeMemorySystem` can only project a
completed authoritative outcome into an agent's private `Memory`; changing or
deleting that memory cannot transfer goods or money, resolve a commitment,
create evidence, or alter an adjudication. Relationship state, social memories,
reputation beliefs, journal summaries, and prompt memories remain distinct:
relationships and reputation supply existing bounded decision pressure, journals
compress a private narrative, and prompt retrieval exposes only selected facts.

Every causal projection names its legitimate route: `self_action`, `participant`,
`counterparty`, `direct_observer`, `victim_discovery`, `explicit_transmission`, or
`public_event`. Callers enumerate recipients; global truth is never broadcast by
default. In particular, plan execution details remain actor-private, loss
discovery does not identify an unknown thief, evidence hearsay requires an
explicit transmission record, and justice reaches the town only when the
configured adjudication is public. Significant material acquisition is currently
limited to an authorized purchase made to execute a commitment plan; ordinary
meals and recurring purchases do not become permanent causal memories.

Causal memories carry structured, optional provenance alongside legacy fields:
owner, source system, source record ID, event type, knowledge basis, day,
location, and counterpart IDs. Their deterministic identity is
`memory:<owner>:<source-system>:<source-id>:<event-type>`, making projection
idempotent across replay and save/resume while allowing separate owners to know
the same outcome. Old saves and conversational memories omit these optional
fields and continue to load unchanged.

Active memory is capped at 200 entries and the archive at 500. Archive retention
reserves one fifth of its capacity for deterministically ranked causal or
high-importance history, then fills the remainder by recency. Conversation
context admits at most three memories, including at most one important,
provenance-backed archived event involving the listener; causal provenance,
listener involvement, location, importance, and recency are inspectable ranking
inputs. The overall prompt text budget remains enforced. Memory itself adds no
second trust adjustment: commitment consequences, relationship state, and
reputation continue to influence choices through their existing capped paths.

Run the deterministic causal-memory acceptance evaluation with:

```bash
python scripts/evaluate_causal_memory.py
```

It reports 12 scenarios and 14 invariants, including epistemic boundaries,
replay/save idempotency, authority independence, bounded retention and recall,
and bounded future-choice pressure. Existing long-run save files can be checked
without loading a model with:

```bash
python scripts/evaluate_causal_memory_stress.py path/to/save_state.json [...]
```

## Grounded dialogue and follow-through

Selected speaker-owned causal memories now enter prompts as a bounded typed
grounding packet with prompt-local references and explicit outcome polarity.
The optional response envelope records references and narrow social
follow-through intent; deterministic validation rejects fabricated references,
polarity reversals, unknown-culprit accusations, private-plan leakage, and
claims that dialogue completed an authoritative transition. Follow-through is
metadata only: repair commitments still require the existing proposal and
acceptance path, and no extra relationship or reputation effect is applied.

Run the deterministic and cached no-model evaluations with:

```bash
python scripts/evaluate_grounded_dialogue.py
python scripts/evaluate_grounded_dialogue.py --cached data/grounded_dialogue_cached_3b.json
python scripts/evaluate_grounded_dialogue.py --cached data/grounded_dialogue_cached_7b.json
```

See [the grounded-dialogue architecture and live 3B/7B commands](docs/grounded_dialogue.md)
for the packet contract, artifact metadata, authority boundary, metrics, and
known limitations.

## Current limitations

- Response outcome inference is deliberately conservative and lexical.
- Session effects are generally applied after dialogue generation, so relationship
  state does not change midway through the same conversation.
- The four-turn default bounds cost and failure propagation but limits depth.
- Commitments remain limited to `help`, `meet`, and `transfer`; proposal and
  cancellation grammar is intentionally narrow, preparation currently covers
  only an existing-seller transfer purchase, and there is no general calendar,
  contract engine, negotiation planner, multi-party promise, or hierarchical
  autonomous planner.
- Persistent plans currently have one deterministic two-step template for transfer
  commitments. There is no free-form decomposition, multi-party plan, general
  calendar, plan-to-plan dependency, or LLM-authored authoritative step. Blocked
  acquisition rediscovery can find a newly valid configured seller route, but the
  planner does not negotiate or synthesize alternate strategies.
- A local 3B model's instruction following and naturalness constrain dialogue quality.
- Same-action deduplication and rate suppression trade some behavioral fidelity for
  stable relationship, reputation, need, goal, intent, and town-arc progression.
- Reputation's downstream decision influence is deliberately modest and limited
  to the capped social-target term described above; it does not affect activities
  or goals.
- Wages and goods prices are fixed configuration. Wages are limited to one
  qualifying payment per employment/day, and purchases to one configured activity
  per buyer/day.
- Employer funds are finite and deliberately have no replenishment mechanism in
  this first closed-system slice.
- Material state remains a small catalog and one configured recipe. Provenance is
  batch/lot based, not unique physical serial numbers. Raw inputs are finite
  configured stock: there is no extraction, generalized manufacturing economy,
  external market, supply/demand pricing, bargaining, loans, debt, taxes, or
  business competition. Prices remain fixed.
- Theft uses co-location plus a simple reproducible one-in-three observation rule.
- Justice is intentionally not a realistic legal system. Theft is the only
  authoritative crime; evidence rules are simple; there are no lawyers, juries,
  appeals, generalized police, prisons, procedural-law simulation, or LLM
  adjudication. The designated investigator is configuration, not a profession.
- V2 has no dynamic pricing, debt, taxation, generalized manufacturing or resource
  extraction, police, prison, lawyers, juries, appeals, politics, factions,
  romance, organizations, large-population model, or GUI.

## Future directions

V1 remains frozen as the social core. V2 is scoped as a small auditable causal
loop, not realistic economics, law, or emergent civilization. A first V3 milestone
should continue deepening grounded response and social follow-through evaluation,
rather than adding another institution or broad simulation feature.
