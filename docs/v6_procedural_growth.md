# V6 bounded procedural growth

V6 admits generated possibilities without giving a generator authority over the
simulated world. It is not unrestricted procedural civilization generation.
Phase 1 admits resident and public-location templates. Phase 2 additionally
admits bounded dynamic-event templates, but only for generated public locations
that passed ordinary V5 activation and accumulated sustained authoritative use.
Phase 3 may admit a bounded civic-institution template only after a generated
event at that exact place has actually occurred. Formation remains a separate
deterministic V5 decision.

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
`propose_institution(context)`. The provider receives a copied JSON-compatible
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
authority after the complete causal evidence chain. It receives no commerce,
production, seller, evidence override, or legal authority. A
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
employment identities, or commerce templates. Existing commerce references only
exact checked-in institution-template IDs.

## Evaluation and optional model path

Run the model-free real-engine gate with:

```bash
python scripts/evaluate_growth_proposals.py
python scripts/evaluate_procedural_events.py
python scripts/evaluate_procedural_institutions.py
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
```

This path is intentionally excluded from ordinary CI. Text generation need not
be identical across hardware; deterministic replay begins after admission.

## Explicit limitations

Phase 3 stops at one bounded institution and one deterministic employment
contract. It does not generate commerce, sellers, goods, recipes, prices, supply
chains, multiple arbitrary roles, arbitrary hiring, job switching, housing,
land, roads, zoning, demographics, births/deaths, departures, taxes, finance,
government, politics, or law. Generated events cannot declare that they occurred,
and generated institution prose cannot declare that an institution exists.
Bounded procedural institutional commerce remains a separate future phase.
