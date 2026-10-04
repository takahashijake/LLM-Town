# V6 bounded procedural-growth assurance contract

The generator may propose bounded semantic possibilities, but only deterministic
simulation systems may grant authority. This is bounded procedural growth, not
unrestricted procedural civilization generation.

The complete causal chain is:

```text
semantic resident → admitted template → deterministic migration → resident
semantic place → admitted template → later deterministic activation → location
location + sustained local use → semantic event template → real local occurrence
location + exact generated occurrences → semantic institution template
→ later formation → distinct employee + employer account + employment
→ ordinary local work + conserved wages
→ semantic community_meals offer → admitted commerce template
→ later commerce activation → empty inventory + bound seller + route + recipe
→ upstream purchase of existing input lots → input-consuming production
→ resident purchases of actual output lots → conserved institution revenue
```

Admission creates only validated, persisted possibilities. Generated text cannot
create agents, locations, occurrences, institutions, employment, accounts,
balances, inventories, sellers, recipes, stock, production, purchases, revenue,
legal authority, commitments, goal progress, or arbitrary economic parameters.
Targets and all authority IDs are selected outside the provider. Display names,
including similar names and identical commerce offers, confer no authority.

## Concurrent branches

The release fixture admits two residents and two independent place/event/
institution/commerce branches. Both use the existing `community_meals` archetype:
2 existing meal ingredients become 4 prepared meals, with stock target 8 and
catalog prices. Both procure from the configured market. Procurement and sales
may legitimately share upstream lot ancestry; each production's consumed inputs
must have reached its own inventory through its own procurement transfers.

Identity counters derive from persisted records and independent monotonic
namespaces. Event target order uses admitted count, activation age, last targeting
and stable ID. Institution selection additionally uses qualifying occurrence age.
Commerce considers only unused generated institutions and orders by activation
age and stable template ID. Successful admission removes a saturated target;
rejected attempts consume finite capacity. This guarantees bounded deterministic
selection, not successful growth in a town lacking evidence, workers or money.

Every child must match its exact parent: template, activation, location,
occurrence allowlist, formation, employee, employment, account, commerce
activation, inventory, seller, activity and recipe. Valid authority in another
branch fails the same checks as fabricated authority. Generated event IDs never
enter the configured Garden or Pavilion allowlists. The checked-in default world
continues to run without procedural configuration or provider calls.

## Persistence and transactions

Canonical payloads bind admitted records to templates through sorted JSON SHA-256
and exact semantic equality. Historical reconstruction uses saved state alone;
future proposals can still use a provider if capacity remains. Growth schema
versions 1, 2 and 3 migrate to 4 only through explicit empty structural additions.
Historical record field sets are explicit fixed contracts, independent of
future dataclass additions. Legacy records cannot smuggle modern target fields. Unknown versions and malformed
persisted fields fail closed; configuration defaults are distinct from complete
persisted record schemas.

Admission occurs after ordinary growth reviews. Generated activation, occurrence,
formation and commerce must occur on a later day. Reviews of retained historical
days are idempotent. Proposal capacity bounds include rejections and provider
errors. Event history retains earliest qualifying occurrences and formation candidate
attendance referenced by historical authority while keeping its existing bound.
If the bound cannot accommodate required evidence plus a new occurrence, selection
fails before mutation. Lost evidence in an already-corrupted old save is not
reconstructed from names or model output. Review histories remain bounded; authoritative transaction histories are
retained for reconstruction and are not claimed to have constant save-file size.

Settlement and startup grants, wages, procurement and purchases transfer existing
currency. Empty dynamic inventories add no material baseline. Production records
account for consumed inputs and generated outputs, and output lots retain input
lineage. Purchases coordinate payment and the actual goods transfer. Same-tick material
replay uses the authoritative lot-movement commit order, including procurement
before production and sales. Ledger and material counters must exactly match
their persisted histories. Commit-time
exceptions roll back material and monetary authority and are re-raised; engine
formation/registration failures restore registries and memories and retain a
rejected lifecycle record for diagnostics.

Growth memories require an activated source, exact source place and activation
day, and the authorized owner for private employment/operator events. Public
memories can belong to any resident but cannot borrow another branch's place.

## Release gate

```bash
python -m compileall -q src scripts tests
python -m pytest
python scripts/evaluate_v6_freeze.py
python scripts/evaluate_v6_freeze.py --comprehensive
```

The normal gate runs repeated uninterrupted worlds, a trajectory that reloads at
every distinct authority boundary, provider-free reconstruction checks,
conservation and provenance audits, historical review replay, 390-day capacity
exhaustion with a full bounded occurrence history,
and generated field-shape and valid-but-wrong-branch corruption cases. It prints
a concise PASS/FAIL summary and structured JSON diagnostics, including a stable
authoritative signature digest. Legacy UUID conversation/event memories are
excluded from authoritative signatures; causal memories retain their stable IDs. `--output PATH` saves the complete report.

Comprehensive mode additionally continues each checkpoint independently to the
same final state. Both modes use identical audit and mutation logic. Normal CI
runs compileall, full model-free pytest and the normal integrated gate. Real
model execution remains optional and is never replay truth.

Optional model admission smoke:

```bash
python scripts/evaluate_procedural_commerce_real.py --local-files-only --multi-branch
```

The bootstrap uses deterministic proposals; only the closed commerce offer uses
the model. Output shows each bounded context, raw result, canonical parser result,
admission outcome and externally selected target. Model variation cannot weaken
strict admission or deterministic release checks.

## Deliberate limits

No arbitrary goods, prices, recipes, supply chains, jobs, hiring/firing, banking,
loans, taxation, government, law, land/housing, zoning, roads, births/deaths or
model-written state mutation. One real event per day and existing evidence,
funding, worker, material and capacity constraints remain in force. Optional
model smoke requires installed weights and is not a freeze prerequisite.

The [audit record](v6_assurance_audit.md) records the baseline and each discovered
defect with its regression coverage.
