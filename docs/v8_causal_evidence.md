# V8 causal evidence architecture

## Design contract

The investigator reads persisted JSON. It does not instantiate the simulation,
load an LLM, alter a save, reconstruct missing authority, or invoke transitions.
Its report is an observation and must never be accepted as simulation input.
The LLM's prose and proposals cannot prove a transfer, formation or execution.

Separate responsibilities are essential: input budgets and schema handling;
allowlisted record projection; typed namespace/reference resolution; explicit
relationship contracts; bounded traversal; and CLI serialization. A generic
join on IDs is insufficient because resident/location/time co-occurrence supplies
no causal direction. Rehydrating an engine is also unsuitable: it needs external
configuration and can migrate old state. Existing replay contracts are the
reference for pure observation checks, not a reason to run transitions.

Facts are persisted authority observations. Verified dependencies must include
source and target typed identities, a closed relationship label, source paths
and the deterministic contract checked. Associations explicitly leave causation
unproven. Missing, pruned, legacy or contradictory evidence remains unresolved.
"Verified" describes internal persisted contract consistency, not authenticity
of a file supplied by an attacker and not proof that all eligibility policy was
satisfied. Operator reports do not grant residents global knowledge.

## Contract audit

| System | Persisted proof | Additional checks required |
| --- | --- | --- |
| Institution | location activation, employment, employer account, startup ledger reference | matching location, reciprocal formation/institution/employee/role bindings, canonical child IDs, startup event/type/accounts/metadata and chronology |
| Commerce | institution formation, location, operator, account, inventory/seller/recipe references | exact parent branch, reciprocal registered material bindings and activation chronology |
| Exchange | monetary transaction and inventory transfer IDs | purchase type, reciprocal exchange authorization and metadata, equal accounts, inventories, goods, quantities, amount and commit time |
| Production lot | production ID and parent lot IDs | exact output IDs, recipe/quantity/ancestry agreement, input movement group and ownership at commit; shared inputs are legitimate only through actual movements |
| Movement | typed movement kind and reference ID | matching transfer/consumption/production inputs, group quantities, lot goods and replay availability |
| Commitment | repair parent, execution and material-transfer evidence | same participants/type, terminal predecessor, acyclic chronology, exact actor/source and authorized goods transfer |
| Plan | source commitment and execution keys/step IDs | actor ownership, template/step contract, matching authoritative attempt/execution proof |

Configured growth policy/templates are not embedded in ordinary saves. Formation
records do not retain an exact eligibility witness set. Activities and occurrences
may be retained or pruned. Matching timestamps, local activity or event templates
cannot prove that a particular occurrence was the cause of formation. Reports
must expose this limitation without guessing a qualifying history.


## Regression strategy

Fast tests must exercise actual system `to_dict` records and engine saves as well
as malformed minimal dictionaries. Test filters after matching beyond 1000 rows,
namespace collisions, exact IDs, chronology fallbacks, missing/pruned proof,
read-only repeated queries and unchanged file bytes. Attack valid other-branch
IDs and reciprocal ancestry, rather than relying only on nonexistent IDs.
Test seeded repeated and resumed simulations; compare projections rather than
legacy UUID memories or dialogue text. Subprocesses vary Python hash seeds and
run CLI commands without `PYTHONPATH` or engine/model imports. Outputs must
remain deterministic under equivalent dictionary insertion orders.

Material tests must consume real procured lots, validate same-tick replay order,
match goods/payment legs, reject overspending/negative inventory histories,
reject future parents/cycles, and preserve shared upstream ancestry. Failed
contracts must withhold verified edges and report controlled uncertainty.
Formation and commerce tests must substitute each reciprocal parent binding and
check exact namespace resolution. Commitment coverage should include successful
transfer execution, terminal repair lineage, missing proof and invalid pair/type
references. General traversal tests cover cycles, fanout, depth and count caps.

Compilation and focused inspector tests comprise fast feedback. The unchanged
complete pytest suite is the regression gate. Normal and comprehensive V6 freeze
runs remain release gates; no assertion, threshold or existing test is removed.
Final adversarial review examines correctness, security, authority ownership,
test effectiveness, module cohesion and processing bounds separately.

## Implemented modules

- `inspection_save.py`: bounded JSON reading, duplicate-key/non-finite rejection,
  present-section shape checks, supported subsystem versions, output budgets.
- `inspection_records.py`: explicit scalar/list projection and lifecycle date
  fallback; no nested metadata or narrative output.
- `simulation_inspector.py`: compatible V7 timeline/show/compare facade.
- `causal_evidence.py`: frozen typed references, nodes, edges, associations and
  diagnostics; namespace index and deterministic bounded breadth-first traversal.
- `causal_materials.py`: pure monetary reconciliation and material commit replay;
  definitions come from existing dataclasses without constructing systems.
- `causal_growth.py`: exact location/employment binding, institution startup and
  registered authority, commerce parent and inventory/seller/recipe bindings.
- `causal_commitments.py`: bounded terminal repair lineage, exact transfer
  fulfillment, source plans and supported acquisition/delivery execution proofs.
- `causal_inspector.py`: read-only composition and public `trace` API.
- `inspection_presentation.py`: fixed human labels. The CLI defaults to JSON.

Existing timeline/show/compare report schema remains **1**, with expanded
allowlisted fields and corrected lifecycle chronology/filtering. The independent
causal evidence schema is **1**, identified by `kind: causal_trace`. A report's
`signature` hashes its canonical JSON before inserting the signature itself.
Edge IDs hash the typed endpoints, relationship, contract and evidence class.
Nodes retain their persisted collection path and source ordinal.
The separately bounded `ownership` array reports current inventory/owner/quantity
facts from saved `lot_holdings` only after replay reconciles them. It does not
introduce another causal edge or a new authoritative state. Institution
queries accept either institution ID or exact formation ID and return the
canonical formation reference. IDs in different namespaces cannot alias.

## Supported causal relationships

Activated institutions expose location dependencies bound to the employee's
work-location contract, reciprocal startup funding, their zero-baseline account
and exact employment. Commerce requires an exact activated formation branch and
reciprocal inventory, seller and recipe registries. These verify registration
and dependency references; they **do not** certify configured policy values or
complete eligibility/target selection from an ordinary save. Configured templates
are external; startup source and amount are reconciled ledger facts, not a claim
that the external configuration grant was the right one.

A lot's production link requires exact output identity, recipe, quantities and
parent ancestry. Input ownership must replay at the production's saved movement
commit position. Transfer/consumption/production movement groups must match
references, inventory legs, goods and quantities. Exchange payment and goods
edges additionally require reciprocal monetary metadata and exchange authorization,
accounts, price multiplication, seller/buyer bindings and equal commit dates.
Shared upstream lots can feed different inventories only through actual movements;
sharing ancestry never merges their separate production or commerce identities.

Repair references require a terminal predecessor, preserved participants/type,
acyclic bounded ancestry and nondecreasing dates/ticks where available. Transfer
fulfillment requires the exact authorized goods transfer, participant inventories,
quantity, event key and resolution time. Source-plan edges require an actor-owned
commitment and a supported bounded template. Acquisition/delivery plan execution
requires the exact completed step, execution key and authoritative supporting
purchase or fulfilled transfer record. Attempt/execution edges say that the
commitment identifies those records; those observations alone do not prove an
outcome. Creation and cancellation dialogue are not disclosed or treated as
causal proof. Help/meeting co-location, general failure reasons and full nested
plan transition histories are deliberately unresolved.

Same-location prior event occurrences are **association-only**, never eligibility
proof. They are not followed by causal traversal. At most 64 occurrence candidates
per formation are associated, with an explicit diagnostic when this cap applies.
An absent/pruned record remains unknown. There is no schema migration or new
simulation authority. Legacy material histories without full modern movements
can be projected as facts but cannot obtain verified material edges.

## Commands and bounds

```bash
python scripts/inspect_town.py timeline SAVE.json --limit 25 --offset 25
python scripts/inspect_town.py show SAVE.json institution --id institution:0001
python scripts/inspect_town.py trace SAVE.json --type institution --id institution:0001
python scripts/inspect_town.py trace SAVE.json --type lot --id LOT_ID --direction upstream
python scripts/inspect_town.py trace SAVE.json --type commitment --id COMMITMENT_ID
python scripts/inspect_town.py trace SAVE.json --type commerce --id commerce-activation:0001 --format text
python scripts/inspect_town.py compare BEFORE.json AFTER.json
```

Trace defaults: depth 6, limit 100, direction `both`. Depth is 0–32; limit is
1–1000 and independently caps nodes, edges, diagnostics and associations.
`upstream` follows dependencies; `downstream` follows effects. `both` can legitimately
reach other branches through shared upstream supply; every node remains typed and
separate. Traversal marks truncation, never interprets a cutoff as absence.
Timeline limits are 1–1000 with offset pagination. Show filters the complete
bounded input **before** applying its output limit and reports total matches.
Identity matching considers identifier fields, not statuses or narrative tokens.

Input limits: 64 MiB files/text budget, 2 million structural values, depth 64,
200,000 entries per collection and causal records/edges, 1 million characters per
input string, 512-bit integers. JSON duplicate keys, non-finite numbers, malformed
collections and incompatible explicit subsystem versions fail with controlled
errors. Missing legacy sections may project empty facts; missing causal evidence
cannot verify an edge. Reports are capped at 4 MiB serialized JSON; reduce query
limits if this cap is exceeded. Public identity tokens are ASCII, 1–200 characters,
with no whitespace/control characters. Long/nested/untrusted scalar prose is not
rendered. CLI failures return status 2 and a versioned JSON error on stderr.

This is an operator audit tool, not an authenticated resident interface. World
facts may include account/inventory identities and public-authority balances.
Private memories, archives, journals, beliefs, dialogues, raw proposals,
source-session IDs, descriptions, reasons and arbitrary nested metadata remain
excluded. An attacker can rewrite a whole consistent save; verification checks
persisted relationships, not cryptographic authenticity or historical execution.

## Reproducible demonstration

```bash
python scripts/showcase_v8.py --output /tmp/llm-town-v8
python scripts/inspect_town.py timeline /tmp/llm-town-v8/after.json --limit 25
python scripts/inspect_town.py trace /tmp/llm-town-v8/after.json --type institution --id institution:0001 --depth 2 --format text
python scripts/inspect_town.py trace /tmp/llm-town-v8/after.json --type lot --id lot:production:production-00000004:prepared_meal --direction upstream
python scripts/inspect_town.py compare /tmp/llm-town-v8/before.json /tmp/llm-town-v8/after.json
```

The script reuses the actual V6 configuration/provider and seed 23. It runs a
180-day world, a 90-day comparison world and an independently reconstructed
90+90 trajectory. Both generated branches must pass the existing branch audits;
configured Garden commerce remains separate. It derives selected production IDs
from actual records, asserts supported startup/lot edges, and compares each trace
after reconstruction. `institution-1.json`, `institution-2.json`, `lot-1.json`,
`lot-2.json`, `timeline.json`, `comparison.json` and `showcase.json` are generated
reports. `unresolved-lot.json` removes movement history from a **copy** and asserts
that no material dependency is verified. Worlds contain private simulation data;
CI publishes only controlled inspector reports. No model weights are downloaded.

The full trace signatures match after reconstruction. Raw legacy UUID relationship
histories are outside the typed causal graph; `compare` continues reporting their
projection differences honestly rather than demanding stochastic UUID equality.

## Extending and reviewing

Add an explicitly admitted collection and immutable typed identity; name the
existing deterministic contract; check reciprocal references, branch bindings,
chronology and replay availability before creating an edge. Do not join on prose,
resident IDs, location or date alone. Add real saved fixtures and valid-but-wrong
reference attacks; prove read-only behavior and safe diagnostics. Unsupported
proof should produce a controlled unresolved code. Keep presentation labels fixed.

Deliberate debt: a contradiction anywhere in material replay conservatively
withholds all material edges, even for otherwise intact branches. Future work can
localize proof failures without weakening conservation/replay checks. Formation
eligibility would benefit from a separately designed persisted witness contract;
this implementation does not invent one or expand save schemas. Large histories
are bounded and indexed, but reading a JSON snapshot still requires memory for
that snapshot; this is not a streaming forensic database.
