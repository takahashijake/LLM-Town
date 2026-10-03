# V6 Phase 1: bounded procedural growth proposals

V6 Phase 1 admits generated possibilities without giving a generator authority
over the simulated world. It is not unrestricted procedural civilization
generation. Only resident templates and public-location templates may be
proposed.

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

`GrowthProposalProvider` exposes only `propose_resident(context)` and
`propose_location(context)`. The provider receives a copied JSON-compatible
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

## Canonical IDs, persistence, and replay

Attempts use contiguous monotonic `growth-proposal:0001` identities. Resident and
location template namespaces have independent monotonic sequences and never use
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
```

All V5 preflight, rollback, replay, settlement, conservation, registry, causal
memory, and activity behavior remains on these existing paths.

## Branch isolation

A generated location receives only public-place activation authority. It has no
dynamic-event, institution, role, job, commerce, production, seller, evidence
override, or legal authority. A generated resident receives no Garden or Pavilion
role merely by visiting either place.

The Garden retains its global seven-day/three-candidate evidence floor. The
checked-in Pavilion keeps only its explicit five-day/one-candidate local override.
Exact location-template, event-template, employment, work-location, and commerce
bindings therefore continue to prevent cross-branch wages and Garden commerce by
the Pavilion employee.

## Evaluation and optional model path

Run the model-free real-engine gate with:

```bash
python scripts/evaluate_growth_proposals.py
```

Its static provider exercises admission, save immediately after the first
proposal, resume with a provider that refuses to reproduce that proposal, V5
migration and location activation, ordinary next-day participation, conservation,
repeatability, capacity stabilization, and adversarial save mutations.

An optional local-model run reuses `TransformersLLMClient` and sends JSON-only
instructions through the same parser and admission code:

```bash
python scripts/evaluate_growth_proposals_real.py --local-files-only
```

This path is intentionally excluded from ordinary CI. Text generation need not
be identical across hardware; deterministic replay begins after admission.

## Explicit limitations

Phase 1 does not generate events, institutions, organizations, roles, jobs,
commerce, recipes, sellers, goods, prices, supply chains, housing, land, roads,
zoning, demographics, birth/death, departures, taxes, finance, government,
politics, or laws. Those domains remain finite and configured. This phase proves
only the reusable proposal → admission → persisted template → existing authority
architecture.
