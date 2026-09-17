# LLM-Town

The current v1 verification record is in
[`docs/v1_freeze_report.md`](docs/v1_freeze_report.md).

LLM-Town is a persistent, text-based social simulation in which four residents
plan activities, pursue goals, remember events, and hold bounded multi-turn
conversations. It uses a hybrid architecture: deterministic code owns simulation
state and applies validated effects, while a local language model realizes
grounded dialogue. The model never receives arbitrary authority to mutate state.
V1 remains frozen; the first three V2 slices add deliberately small deterministic
economic, material, and crime/evidence foundations without changing that boundary.

## Key capabilities

- Bounded, alternating conversation sessions (four utterances by default)
- Per-speaker context boundaries for memories, journals, goals, intents, and beliefs
- Deterministic semantic-action inference and conservative response outcomes
- Separate semantic action records and effect eligibility/rate limiting
- One bounded anti-echo regeneration attempt on the real-model path
- Persistent memories, daily journals, goals, intents, and adaptive goal strategies
- Directional relationship state plus a compatible shared relationship score
- Direct reputation observations and provenance-preserving hearsay
- Needs, occupations, activity planning, daily events, and town arcs
- Authoritative integer accounts, employment, wages, and an auditable ledger
- Closed-system currency conservation and idempotent daily wage events
- Persistent goods, inventory ownership, atomic purchases, and consumption records
- Unauthorized material transfers, auditable theft incidents, and private evidence
- Deterministic witness opportunity and provenance-preserving crime hearsay
- Save/resume semantics, isolated deterministic benchmarks, and real-LLM review artifacts
- A deterministic automated test suite that does not load or download a model

The repository implements the economic, material, and narrow theft/evidence
foundations described below. Justice, policing, courts, other crime types, debt,
taxes, dynamic markets, romance, factions, politics, a GUI, and semantic vector
memory remain outside the current scope.

## Architecture overview

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
crime incidents, witnesses, or evidence.
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
src/systems/       economy, materials, crime/evidence, and reputation
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
theft incidents/witness opportunity/evidence provenance, persistence/resume,
reporting, benchmarks, and evaluation artifacts.
CI installs only `requirements-dev.txt`, uses the fake/model-free paths, and never
downloads Qwen or requires CUDA.

## Current limitations

- Response outcome inference is deliberately conservative and lexical.
- Session effects are generally applied after dialogue generation, so relationship
  state does not change midway through the same conversation.
- The four-turn default bounds cost and failure propagation but limits depth.
- A local 3B model's instruction following and naturalness constrain dialogue quality.
- Same-action deduplication and rate suppression trade some behavioral fidelity for
  stable relationship, reputation, need, goal, intent, and town-arc progression.
- Reputation propagation is implemented, but downstream decision influence still
  benefits from controlled evaluation; lexical overlap alone does not establish it.
- Wages and goods prices are fixed configuration. Wages are limited to one
  qualifying payment per employment/day, and purchases to one configured activity
  per buyer/day.
- Employer funds are finite and deliberately have no replenishment mechanism in
  this first closed-system slice.
- Material state is a small catalog with inventory-level ownership. It has no
  production, restocking, per-instance serial numbers, bargaining, dynamic prices,
  loans, debt, taxes, or business competition.
- Theft uses co-location plus a simple reproducible one-in-three observation rule.
  There is no stealth, security, investigation, policing, adjudication,
  restitution, punishment, or authoritative guilt decision.

## Future directions

V1 remains frozen as the social core. The recommended next V2 milestone is a
deterministic investigation, adjudication, and consequence pipeline that consumes
the incidents and provenance-bearing evidence implemented here. It must not treat
accusation or reputation as guilt. Romance, factions, politics, large-population
work, and a GUI remain separate directions.
