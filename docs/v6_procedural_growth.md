# V6 bounded procedural growth

V6 admits generated possibilities without giving a generator authority over the
simulated world. It is not unrestricted procedural civilization generation.
Phase 1 admits resident and public-location templates. Phase 2 additionally
admits bounded dynamic-event templates, but only for generated public locations
that passed ordinary V5 activation and accumulated sustained authoritative use.
Phase 3 may admit a bounded civic-institution template only after a generated
event at that exact place has actually occurred. Formation remains a separate
deterministic V5 decision. Phase 4 admits one closed commerce offer for a real
generated institution with ordinary work, use and demand evidence. Commerce
activation, procurement, production and sales remain ordinary V5 authority.

```text
authoritative state
       ↓
bounded context
       ↓
untrusted generator
       ↓
strict parser
       ↓
canonical proposal
       ↓
deterministic admission
       ↓
persisted template
       ↓
existing V5 lifecycle
       ↓
authoritative entity
```

## Provider boundary and bounded context

`GrowthProposalProvider` exposes `propose_resident(context)`,
`propose_location(context)`, `propose_event(context)`, and
`propose_institution(context)`, and `propose_commerce(context)`. The provider receives a copied JSON-compatible
context, never an engine or a state-mutating system. The context contains the
completed day, bounded resident and active-place identities, seven days of
aggregate activity counts, the closed affinity vocabulary, capacity counts, and
at most ten structured growth-history entries. Dialogue, journals, memories,
generated claims, and arbitrary summaries are excluded.

No provider means no procedural calls. The checked-in V5 configuration contains
no `procedural_growth` section, so its six-resident/six-location freeze signature
is unchanged. An enabled policy bounds the first day, review interval, cooldown,
resident and location attempt capacities, and complete proposal history. Rejected
candidates consume their kind's attempt capacity, preventing an invalid provider
from creating unbounded IDs or calls.

Event proposal context is narrower: it contains the completed day, the exact
deterministically selected generated location and its description/affinities,
bounded aggregate recent use, permitted vocabularies, existing event names, and
remaining capacities. It excludes balances, inventory, memories, relationships,
dialogue, journals, legal internals, and mutable system references.

Institution proposal context contains the deterministically selected generated
place, bounded aggregate use, and semantic names/descriptions of generated local
events with real occurrence history. It withholds template IDs, employee
candidates, accounts, balances, wages, grants, and formation controls.

## Strict candidate schemas

A resident candidate has exactly:

```json
{"name": "Mira", "personality": "curious", "goals": ["learn local customs"]}
```

Deterministic code adds neutral `social`, `wealth`, and `knowledge` needs of 50,
the `arrival_location` policy, and a
`generated_resident_template_0001` identity. The provider cannot supply an agent,
template, migration, account, or inventory ID; money or goods; employment,
occupation, relationships, reputation, commitments, legal state, goal progress,
or an authoritative location.

A location candidate has exactly:

```json
{
  "name": "Story Grove",
  "description": "A small public grove for conversation and reading.",
  "affinities": ["social", "knowledge", "community"]
}
```

Affinities must be a unique nonempty subset of the V5 closed vocabulary:
`social`, `knowledge`, and `community`. Deterministic code assigns paired
`generated_location_template_0001` and `generated_location_0001` identities.
The provider cannot specify activation IDs, event or institution authority,
seller or inventory state, commerce, production, employment, law, or goal
progress. Unknown keys, malformed JSON, wrong types, long or empty strings,
duplicates, reserved identities, and invalid affinities fail closed.

An event candidate has exactly:

```json
{
  "name": "Story Exchange",
  "description": "Residents share short stories and local knowledge.",
  "tags": ["community", "knowledge", "social"],
  "required_affinities": ["community", "knowledge"]
}
```

Tags and affinities must be unique values from the existing event-ecology closed
vocabularies; required affinities must exist at the selected location. The
provider cannot choose event or occurrence IDs, target, timing, thresholds,
cooldown, capacity, institutions, roles, jobs, money, goods, commerce, law,
memories, relationships, commitments, or plans.

An institution candidate has exactly:

```json
{
  "name": "Story Grove Commons",
  "role_title": "story grove coordinator",
  "work_activity_name": "Coordinate Story Grove programs"
}
```

The provider supplies only these display semantics. It cannot choose the target,
event allowlist, employee, institution/key/formation/account/employment IDs,
role or activity IDs, wage, grant, funding source, review day, thresholds,
capacity, commerce, goods, recipes, legal powers, memories, or relationships.
Unknown keys reject the entire bounded attempt.

## Canonical IDs, persistence, and replay

Attempts use contiguous monotonic `growth-proposal:0001` identities. Resident,
location, event, and institution template namespaces have independent monotonic
sequences and never use
Python `hash()`, model text, slugified names, wall-clock time, object identity, or
set order.

An admitted record stores the canonical payload, SHA-256 of sorted compact JSON,
generated template ID, provider metadata, proposal day, and admission day. Save
state also stores the exact resulting template. Load strictly reconstructs both,
checks their equality and digest binding, validates complete admitted-template
sets and monotonic counters, and then supplies them to the ordinary V5 systems.
The model is not called to reconstruct history.

Load rejects altered proposal IDs, kinds, statuses, payloads, digests, generated
IDs, template contents, admitted-template lists, and counters. It also rejects a
migration or location activation referencing an unknown generated template.
Old V5 saves without `growth_proposals` remain valid.
Phase 1 schema-v1 proposal state migrates strictly to schema v2 with an empty
event-template roster and event sequence 1; it fabricates no proposals, history,
or occurrence authority. Phase 2 schema-v2 state migrates to schema v3 with an
empty institution-template roster and institution sequence 1. It fabricates no
institution proposal, formation, employment, account, or money. Unknown future
versions fail closed.

## V5 reuse and causal separation

Admission only expands a finite roster through
`register_generated_template`. Proposal review runs after the completed day's V5
growth reviews, so an admitted possibility cannot be proposed for migration or
activation on the same day.

```text
resident candidate → admitted proposal → ResidentTemplate
                   → later TownGrowthSystem review → MigrationRecord
                   → existing atomic activation → Agent/account/inventory/settlement

location candidate → admitted proposal → LocationTemplate
                   → later LocationGrowthSystem review → LocationActivationRecord
                   → existing activation → authoritative Location

activated generated location + sustained use
                   → deterministic target selection
                   → semantic event candidate → admitted DynamicEventTemplate
                   → later ordinary EventEcologySystem eligibility/selection
                   → authoritative DynamicEventOccurrenceRecord

generated location + sustained use + generated event occurrences
                   → deterministic institution target and exact event allowlist
                   → semantic institution candidate → admitted InstitutionTemplate
                   → later ordinary InstitutionGrowthSystem review
                   → deterministic employee + InstitutionFormationRecord
                   → existing atomic activation → account + one employment
                   → ordinary generated work activity + conserved wages
```

Event targets are selected by fewest admitted events, oldest activation, least
recently targeted location, then stable generated template ID. Admission uses
the existing event-ecology eligibility floors and a deterministic bounded
cooldown. It creates only a possibility. An event admitted after day D cannot
occur on day D.

Institution targets are selected by fewest admitted generated institution
templates, oldest qualifying activation, oldest qualifying generated-event
evidence, least recent institution targeting, then stable generated location ID.
The exact finite event allowlist is derived from admitted generated events at
that location with occurrence authority no later than the proposal day. The
model never supplies it.

Admission transfers no money and creates no institution or job. A later ordinary
institution review retains configured timing, capacity, cooldown, sustained-use,
distinct-resident, event-occurrence, candidate-activity, unemployment, account,
funding, and deterministic employee-selection checks. Deterministic policy adds
the institution, key, role, and activity IDs and fixes wage, startup grant, and
funding source. The existing engine transaction creates the account and one
next-day employment, performs the conserved transfer, projects memories, and
rolls back on failure. The ordinary planner and economy then produce work and
wages.

All V5 preflight, rollback, replay, settlement, conservation, registry, causal
memory, and activity behavior remains on these existing paths.

## Branch isolation

A generated location may receive bounded local event and institution-template
authority after the complete causal evidence chain. A real generated institution
may subsequently qualify for the bounded Phase 4 commerce lifecycle. No proposal
grants direct production, seller, evidence override, or legal authority. A
generated resident receives no Garden or Pavilion role merely by visiting either
place.

The Garden retains its global seven-day/three-candidate evidence floor. The
checked-in Pavilion keeps only its explicit five-day/one-candidate local override.
Exact location-template, event-template, employment, work-location, and commerce
bindings therefore continue to prevent cross-branch wages and Garden commerce by
the Pavilion employee.
Generated events are absent from the exact configured Garden and Pavilion event
allowlists, so their occurrences cannot qualify either institution or downstream
employment or commerce.
Conversely, a generated institution accepts only generated events bound to its
own generated place. It cannot bind Garden/Pavilion events, roles, accounts,
employment identities, or commerce templates. Each commerce template references its exact institution
and generated location; child authority comes only from its own activation.

## Evaluation and optional model path

Run the model-free real-engine gate with:

```bash
python scripts/evaluate_growth_proposals.py
python scripts/evaluate_procedural_events.py
python scripts/evaluate_procedural_institutions.py
python scripts/evaluate_procedural_commerce.py
```

Its static provider exercises admission, save immediately after the first
proposal, resume with a provider that refuses to reproduce that proposal, V5
migration and location activation, ordinary next-day participation, conservation,
repeatability, capacity stabilization, and adversarial save mutations.

An optional local-model run reuses `TransformersLLMClient` and sends JSON-only
instructions through the same parser and admission code:

```bash
python scripts/evaluate_growth_proposals_real.py --local-files-only
python scripts/evaluate_procedural_institutions_real.py --local-files-only
python scripts/evaluate_procedural_commerce_real.py --local-files-only
```

This path is intentionally excluded from ordinary CI. Text generation need not
be identical across hardware; deterministic replay begins after admission.

## Phase 4: bounded institutional commerce

The full chain is:

```text
generated resident/location → activation → sustained place use
→ generated event → real occurrence → generated institution template
→ deterministic formation → account + employment → ordinary work + wages
→ sustained work/use + actual meal demand → semantic commerce proposal
→ persisted generated CommerceTemplate → later ordinary commerce review
→ atomic inventory/seller/purchase-rule/recipe activation
→ real upstream procurement → input-consuming production
→ resident purchases → conserved institution revenue → ordinary wages
```

The exact candidate schema is:

```json
{"offer":"community_meals"}
```

`commerce_proposal_capacity` bounds attempts (default zero). Rejections and
provider exceptions consume capacity. `commerce_archetypes` is the closed list
`["community_meals"]`; arbitrary economic parameters are rejected. History must
hold all attempts across all five kinds. One admitted commerce template per
generated institution is permitted.

The entire model-visible context is:

```json
{
  "target_institution":"Story Grove Commons",
  "target_place":"Story Grove",
  "observed_evidence":"sustained work, local use and meal purchases",
  "permitted_offers":["community_meals"]
}
```

These are semantic names and an evidence summary; names never resolve authority.
The provider sees no account, institution, formation, employment, employee,
inventory, seller, recipe, activity or provenance IDs; prices, quantities,
balances, stock, demand records and activation dates are excluded. Its output
cannot select a target or change the fixed material contract.

Deterministic code considers only admitted generated institutions registered in
ordinary institution growth. It recomputes commerce readiness from the exact
activated formation, generated place activation, real institution account and
active employment, prior eligible operator work, distinct residents/use days,
actual prepared-meal exchanges, authoritative upstream seller/stock and funds.
At the end of day D, evidence includes D; ordinary activation review on a later
day uses its previous-day evidence window. Eligible unused institutions sort by
formation activation day then generated institution template ID. The model
cannot alter this ordering.

`generated_commerce_template_0001` and
`generated_purchase_activity_0001` use contiguous admission sequences. Production
uses the target institution's existing work activity. The fixed offer transforms
2 `meal_ingredients` into 4 `prepared_meal`, with target stock 8, and procures
from the configured `seller:market_stall`. Prices remain material catalog prices.
The recipe suffix is `generated_meals_0001`. Inventory, seller and full recipe IDs
come from the ordinary commerce activation sequence, independently of proposal
text. Registration requires exact admitted proposal provenance and collision
checks.

Admission changes only proposal/template rosters. Engine ordering places it after
ordinary commerce review, and replay validation requires review day strictly
after admission day. It creates no material registry, stock, money transfer,
production or sale. Later V5 readiness, capacity, review cadence and cooldown
remain in charge. Engine preflight and atomic material registration create the
empty institution inventory, account/location-bound seller, one purchase rule
and recipe restricted to the exact employee and employment. Normal material
operations procure existing lots, consume inputs, produce traceable output lots
and atomically transfer purchased goods and currency. Revenue becomes ordinary
institution money.

Proposal schema **4** adds `commerce_templates`,
`next_commerce_template_sequence`, and explicit
`target_institution_template_id` on records. Strict schemas 1→2→3→4 migrations
add empty commerce state and null institution targets, without fabricating any
economic authority. Canonical SHA-256 payloads and exact template derivation bind
both target IDs and the semantic offer. Commerce system schema remains 1: its
generated roster is reconstructed from admitted proposal state before replaying
activation records, never from another model call. Missing/fabricated proposals,
templates and downstream registries fail closed. Historical funds and stock are
reconstructed from initial balances, ledger, production and lot movements;
work/use/demand are replayed from authoritative histories.

Garden retains its configured contract. Pavilion has no commerce template.
Generated commerce binds its own exact formation, location activation, account,
employment, inventory, seller, recipe and activation provenance. Similar goods or
names cannot grant another branch's authority.

The Phase 4 evaluator uses a bounded static provider and the real engine. It checks
repeatability, saves before admission, after admission and after activation,
provider exhaustion, economic/material reconstruction, procurement/production/
sales/revenue, static branch isolation and adversarial replay mutations. Its
configuration raises finite commerce capacity to two to accommodate Garden and
the generated branch; checked-in defaults remain unchanged.

## Explicit limitations

Phase 4 offers only one fixed food-production archetype and one existing employee
per institution. LLM-Town does **not** yet provide unrestricted generation of
arbitrary goods, arbitrary prices, arbitrary recipes, arbitrary supply chains,
multiple arbitrary roles, free hiring/firing or job switching, housing, land,
roads, zoning, demographics, birth/death, departures, taxation, banking/finance,
government, politics or law. Generated events cannot declare occurrences,
institution prose cannot declare formation, and commerce candidates cannot
create stock, purchases or revenue. Broader closed, independently validated
commerce archetypes are a possible next slice, without unrestricted economic
JSON.

## V6 integrated release assurance

The [V6 freeze contract](v6_freeze_candidate.md) defines concurrent generated
branches, exact persisted record schemas, transaction rollback, migration policy
and the integrated corruption/replay gate. Run:

```bash
python scripts/evaluate_v6_freeze.py
python scripts/evaluate_v6_freeze.py --comprehensive
```

Both branches reuse `community_meals`; this adds assurance of multiplicity,
without expanding economic authority. Compileall and the integrated model-free
gate now run in CI alongside pytest. The optional commerce-model script accepts
`--multi-branch`; model output is never used for historical reconstruction.
