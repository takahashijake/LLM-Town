# V5 bounded dynamic-town freeze candidate

## Architectural claim

LLM-Town can deterministically evolve a bounded town through repeated,
provenance-backed population, place, event, institution, employment, and
commerce formation while preserving the frozen social, economic, legal,
planning, and memory authority boundaries.

This is a finite-template freeze candidate, not procedural civilization
generation. The final default world can add two residents, two public places,
two institutions and jobs, and one institution-bound commerce entity.

## Starting architecture and phases

The V1–V4 core already separates generated behavior from deterministic state:
the economy owns money and employment, materials own goods and lots, crime and
justice own legal facts, commitments and plans own their lifecycles, and causal
memory can only project existing authoritative outcomes.

V5 composes six bounded phases:

1. Phase 1 admits a resident from a finite roster through a scheduled,
   activity-gated, funded migration transaction.
2. Phase 2 activates a finite public-place template from population and sustained
   activity evidence.
3. Phase 3 selects provenance-bearing local events at activated places while
   retaining one authoritative daily event.
4. Phase 4 forms a configured institution from exact place use and event evidence,
   then registers one institution account and employment.
5. Phase 5 activates the Garden institution's finite procurement, production,
   seller, and resident-purchase route.
6. Phase 6 repeats the population/place/event/institution/employment pipeline for
   the Civic Pavilion while keeping commerce scoped to the Garden.

## Final bounded evolution

```text
seed town
  -> migration:0001 / resident_template_001
  -> location-activation:0001 / Community Garden
  -> exact Garden occurrences
  -> institution-formation:0001 / Garden Stewardship / steward employment
  -> commerce-activation:0001 / procurement -> production -> sales -> wages

  -> migration:0002 / resident_template_002
  -> location-activation:0002 / Civic Pavilion
  -> exact Pavilion occurrences
  -> institution-formation:0002 / Pavilion Coordination / coordinator employment
```

The category cooldowns remain global growth throttles. Within an eligible
category, stable template ID is the explicit activation ordering. Dynamic-event
fairness uses least-served location and template counts followed by an oldest-use
and seeded SHA tie-break. Identical seed and authority state therefore produce
the same activation and event sequence without relying on Python `hash()`, set
order, ambient model output, or unseeded choice.

## Authority, isolation, and conservation

Every migration owns its resident, zero-baseline account, empty inventory,
settlement transfer, registry integration, and arrival memories. Every place owns
its activation record and public opening memories. Every institution owns its
formation, location activation, employee, employer account, employment contract,
startup transfer, public formation memories, and one private employment memory.

Branch evidence is exact: Garden events and activities cannot qualify the
Pavilion template, and Pavilion evidence cannot qualify Garden Stewardship. A
job pays only its employee for its configured activity at its configured location
after its start day, once per employment/day. The Pavilion coordinator cannot
operate the Garden recipe. Only the Garden formation named by the commerce
template receives inventory, seller, purchase-rule, and recipe authority.

Settlement and startup grants are ordinary conserved transfers. Wages and
purchases use the ordinary economy ledger. Procurement and sales use atomic
material exchanges, and production preserves lot ancestry. Institution accounts
begin at zero; dynamic inventories begin empty. No phase mints currency, initial
stock, or provenance.

## Persistence, replay, and memory

Save state persists stable records, next sequences, consumed-template sets,
cooldowns, bounded reviews, and replay keys. Load reconstructs dynamic locations
from activation authority and cross-checks all residents, accounts, inventories,
institutions, employments, startup transfers, event occurrences, commerce
registries, ledger entries, material histories, and causal memories.

Validation is collective as well as per-record. It rejects duplicate IDs and
sequences, duplicate templates, consumption mismatches, rewound counters, swapped
resident or location bindings, reused employees, wrong account ownership,
orphan jobs, missing startup transfers, wrong role/activity/location contracts,
cross-bound commerce, orphan dynamic inventories or sellers, and private growth
memories attached to the wrong resident. Stable memory IDs include owner, source
system, exact source record, and event type, preventing cross-branch collision.

After finite capacities are exhausted, growth allocates no further records or
sequence values. Review and occurrence histories remain bounded. Save/resume and
repeated same-seed runs have identical authoritative signatures.

## Freeze gates

Run the final growth gate and integrated freeze gate with:

```bash
python scripts/evaluate_multi_site_growth.py
python scripts/evaluate_v5_freeze.py
```

The multi-site evaluator compares uninterrupted, multi-resume, and repeated
260-day worlds; checks both complete branches, Garden commerce, conservation,
provenance, persistence, replay, stabilization, and adversarial multi-entity save
attacks. The V5 gate adds integrated final-world invariants and cross-checks the
economy, materials, production, crime, justice, commitments, causal memory, V2,
V3 freeze, and V4 freeze gates. It does not merely concatenate V5 phase results.

## Known limitations and post-V5 directions

V5 remains limited to two checked-in migrants, two checked-in places, two
single-role institutions, one commerce entity, and one authoritative event per
day. It has no departure, demographics, housing, roads, zoning, land ownership,
general labor market, job switching, arbitrary goods, dynamic pricing, finance,
taxation, politics, governance, arbitrary organizations, unrestricted supply
chains, or model-authored authority.

Possible post-V5 work can generate bounded proposals for already-proven
authority pipelines, broaden labor and organization contracts, or add other
domains behind equally strict provenance and conservation checks. Those
directions are not claims of this freeze candidate.
