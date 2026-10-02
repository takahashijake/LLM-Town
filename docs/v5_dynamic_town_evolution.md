# V5 dynamic town evolution: migration, places, events, and institutions

## Scope and authority

V4 remains frozen. V5 Phase 1 adds one world-level lifecycle: after a completed
day, deterministic code may admit one resident from a finite checked-in roster.
It does not add a goal strategy, dependency, delegation route, generalized
planner, dynamic location, job, business, or model-authored authority.

```text
completed town days
      ↓
bounded readiness review
      ↓
capacity + activity + location + funding
      ↓
finite resident template
      ↓
atomic authority registration
      ├── Agent
      ├── zero-balance account
      ├── empty inventory
      ├── subsystem registries
      └── conserved settlement transfer
      ↓
public migration record
      ↓
ordinary next-day simulation participation
```

`TownGrowthSystem` owns eligibility, stable proposal identity, lifecycle records,
template consumption, replay keys, and bounded public history. `SimulationEngine`
orchestrates registration. Economy and material systems remain the only money and
goods authorities. Generated dialogue cannot propose, create, pay, employ, or
validate a resident.

## Population audit

Seed residents come from `data/agents.json`; locations remain static config from
`data/locations.json`. A migrated resident is serialized through the same `Agent`
state as a seed resident, but also has a provenance-bearing migration record.
Migration history is never fabricated for seed residents.

The runtime population assumptions found before implementation were:

| Component | Population behavior | Registration consequence |
| --- | --- | --- |
| Engine, activity, conversations, journals, intent updates | Read `engine.agents` at use time | Append only after complete preflight |
| `CommitmentSystem` | Previously retained the supplied list reference | Now copies and exposes explicit registration |
| `PlanSystem` | Copies the supplied list | Explicit registration required |
| Crime, justice, outcome memory | Build ID-indexed dictionaries | Explicit registration required |
| Economy | Builds one private account per initial agent | Add a zero account and zero reconstruction baseline |
| Materials | Builds one private inventory per initial agent | Add an empty inventory, baseline, and lot-holding entry |
| Conversation selector/scheduler | Receive the live population or capture it per tick | No persistent registry; newcomer appears next day |
| Relationship and reputation paths | Create neutral/private state lazily | No privileged or fabricated relationship state |

Economy reconstruction starts from `initial_balances` and replays the ledger.
Material reconstruction starts from `initial_quantities` plus lot provenance and
replays authoritative events. Registration therefore extends both baselines with
zero, without changing total currency or quantities.

## Readiness policy and finite templates

`data/town_growth.json` declares the closed policy. A scheduled review proposes a
resident only if all of these gates pass:

1. population is below capacity;
2. the earliest migration day and fixed review interval permit review;
3. the last successful activation is outside the cooldown;
4. the configured static arrival location exists;
5. the configured settlement source account exists and can afford the grant;
6. each day in the recent activity window has the configured number of distinct
   registered residents in authoritative activity records;
7. an unused valid finite template exists; and
8. the review event key has not already been processed.

New activity records carry stable `agent_id`. Old name-only records still load,
but are not guessed into authority for the activity gate.

Templates may contain only a stable template ID, unique name, personality, the
fixed arrival-location policy, legacy goal descriptions, and bounded initial
needs. Legacy goal text follows normal `Agent` initialization into structured
goals. Migrants are always `unemployed`; descriptive text cannot create a job.

## Identity, activation, and conservation

The persisted sequences allocate `migration:0001`, `agent_005`,
`account:agent:agent_005`, and `inventory:agent:agent_005` for the first default
migration. Numeric resident IDs are scanned safely when an old save lacks growth
state; malformed or nonstandard IDs cannot cause reuse. Names, agent IDs, account
IDs, and inventory IDs must all be unique.

A proposal is persisted before activation and can survive a save boundary.
Complete preflight checks template, identity, name, location, account, inventory,
settlement funds, and every cached resident registry. Commit then registers a
zero-balance account, an empty inventory, the resident, and each cache; performs
an ordinary `EconomySystem.transfer`; marks the migration activated; and projects
arrival knowledge. A narrow authority snapshot restores the whole activation set
if any commit operation unexpectedly fails. No general transaction framework was
introduced.

The snapshot is a deep value snapshot, including agent memory and the nested
economy/material reconstruction baselines. A failed activation retains a rejected
audit record but does not consume its template; a later scheduled review may retry
that template with new migration and resident IDs. Allocated IDs are never reused.

The settlement event key is `migration-settlement:<migration-id>`. Its source is
debited and the resident account is credited; the grant is never minted. The new
inventory contains no quantities or lots, so material totals and provenance are
unchanged. Existing employments, sellers, production actors, theft eligibility,
and justice investigators are unchanged.

## History, persistence, and replay

The activated migration record is the authoritative source for one direct arrival
memory owned by the newcomer and one public-event memory for each existing
resident. `OutcomeMemorySystem` validates `town_growth` provenance and derives
stable owner/source/event memory IDs. Failed reviews create no memories.

Save state includes schema version, both sequences, bounded review history,
migration records, last activation day, processed event keys, consumed templates,
and bounded public history. Unknown schemas and malformed records fail closed. An
old save without this section creates empty growth history and reconstructs the
next collision-free resident sequence. A post-activation reload cannot re-add the
resident, repay the grant, recreate the inventory, or duplicate arrival memory.
Loading also cross-checks the resident population against account, inventory,
plan, commitment, crime, justice, outcome-memory, and settlement-ledger authority;
partial or contradictory activation state is rejected.

Review runs after journals and memory maintenance for the completed day and before
the completed-day save. The newcomer first participates on the next day through
ordinary need decay, goals, planning, activity, location grouping, conversations,
relationships, reputation, commitments, purchases, memory, and journaling.

## Evaluation and limits

Run the deterministic acceptance and 90-day stabilization scenario with:

```bash
python scripts/evaluate_population_growth.py
```

It uses `FakeLLMClient`, exercises named gate, activation, conservation,
persistence, provenance, V3/V4 regression, repeatability, and long-horizon
scenarios, and exits nonzero on failure. An optional model-free 365-day soak can
be run outside ordinary CI with:

```bash
python main.py --fake-llm --seed 11 --days 365 --hours 8
```

This is not fully endogenous town growth. Phase 1 admits at most the configured
capacity from a finite roster. It does not model housing, labor demand,
demographics, resident departure, construction, dynamic places, businesses,
production redesign, negotiation, or model-generated residents. Dynamic places
should be considered only after this slice has had a stabilization and observation
period.

## Phase 2: authoritative public-place expansion

Phase 2 composes with the stabilized migration lifecycle without changing it. The
four locations in `data/locations.json` are base configured locations. A separate
finite roster in the `location_growth` section of `data/town_growth.json` contains
inactive public-place templates. A template is descriptive data only: stable
template and location IDs, a unique name and description, and a closed subset of
`social`, `knowledge`, and `community` affinities.

After each completed day, `LocationGrowthSystem` may perform a replay-safe
development review. The default policy requires five active residents, day 28,
the fixed seven-day review schedule, seven completed days in which all five
residents have authoritative activity, cooldown availability, unused capacity,
and an unused finite template. Readiness is recomputed from live population and
activity records. Serialized readiness, dialogue, memory, and model text have no
authority.

```text
four base residents / four base places
        ↓ day 14 migration authority
five residents participate normally
        ↓ seven completed active days
location-review:day:28
        ↓ finite template + complete preflight
location-activation:0001
        ↓ atomic registry append + activation evidence
public opening memory + ordinary use + conversations
```

Activation preflights the template, unused ID and name, review binding, capacity,
closed affinities, and current location authority. Commit exposes one `Location`,
marks exactly one activation record, consumes exactly one template, updates the
ordinary affinity view, and projects provenance-bearing `location_opened`
knowledge. An unexpected commit exception restores the previous registry and
growth authority before retaining a rejected attempt. Allocated review and
activation identities are not reused.

Affinities affect only ordinary need-based public activity selection. They do not
grant employment, seller status, stock, inventories, production, crime permission,
justice roles, commitment types, goal strategies, V4 dependencies, town arcs, or
daily events. Market commerce, Library knowledge strategies, and the fixed
`EVENT_POOL` remain deliberate legacy domain rules. Once two residents arrive at
the new place through normal planning, the existing location-grouped conversation
scheduler can pair them without a special visit script.

Save state persists the bounded review, activation, replay, consumption, and
public-history records. The live dynamic registry is reconstructed from activated
records plus current finite config; an arbitrary serialized location list is never
trusted. Missing templates, changed identities, partial records, duplicate
consumption, unknown schemas, forged provenance, and residents at unknown places
fail closed. Old saves lacking Phase 2 state load the original four-place town.
Because Phase 2 has no removal, historical location references remain resolvable.

Run the Phase 2 acceptance gate with:

```bash
python scripts/evaluate_location_growth.py
```

The evaluator uses real engines and `FakeLLMClient`, repeats a seeded 120-day
save/resume lifecycle, verifies ordinary activity and conversation at the new
place, and attacks identity, metadata, persistence, replay, capacity, readiness,
and provenance boundaries. Review and public histories are bounded. Once the
configured capacity is reached, the system stops allocating proposals or growing
audit state.

## Phase 3: bounded authoritative dynamic event ecology

Phase 3 keeps the existing single `engine.current_daily_event` architecture. The
legacy `EVENT_POOL` remains the finite base-event roster for the four original
places. A second finite roster in `data/town_growth.json` describes compatible
place-local events for configured dynamic places. Generated text cannot add a
template, choose a place, declare eligibility, or create an occurrence.

The old pool entries were reusable template identities even though their Python
type was `DailyEvent`. A selected event is now a concrete occurrence with both a
`template_id` and an `occurrence_id`:

```text
daily-event:<day>:<template-id>:<location-id>
```

The legacy `id` remains the template ID for compatibility. Authoritative
consumers use `occurrence_id`, so two recurrences of the same template cannot be
confused. Old five-field saves still load as legacy events; newly persisted base
and dynamic occurrences carry schema, source kind, day, location, template, and
occurrence identity.

### Eligibility and daily selection

`EventEcologySystem` recomputes eligibility from current authority. A dynamic
candidate requires an activated location with exact Phase 2 provenance, a known
template/location binding, closed tags and affinity requirements, sufficient
location age, multiple distinct residents, activity on multiple recent days, and
an elapsed per-template/location cooldown. Dialogue, memories, descriptions, and
serialized eligibility flags are ignored. Inactive, rejected, forged, future,
or affinity-incompatible places cannot host an event.

Eligible dynamic events augment rather than replace base events. The default
inspectable policy gives dynamic candidates one fixed day in every four while
eligible; all other days use a base event. A SHA-256-derived local choice keyed by
the configured simulation seed and day selects within each finite source class.
This avoids Python's randomized `hash()` and ambient global-random replay
dependence. There is still at most one authoritative event per simulated day.

```text
migration → place activation → repeated ordinary use
          → dynamic eligibility → one concrete occurrence
          → ordinary attend_event → normal co-location/conversation
```

The ordinary planner continues to emit `attend_event`; it records the exact
source occurrence and targets the event's exact active location. The existing
immutable social snapshot and serial/concurrent/batched schedulers need no event
special case. Public daily-event memory means only that the event was known to
exist. Attendance remains an activity record, and conversation or memory text
cannot fabricate it.

### Persistence, V4, and authority boundaries

Dynamic occurrence history and replay guards are exact mirrors capped by the
configured history limit. Save/resume retains the current occurrence, including
across a partial day, without drawing again. Load validates schema, source kind,
template fields, closed tags, exact occurrence identity/day/location, active
location and activation provenance, historical use eligibility, cooldown, and
the matching bounded occurrence record. Contradictory or invented serialized
events fail closed.

V4's `daily_event_at_target_location` contract is unchanged: the current event
must be at the plan's already-bound target. Its authority reference is now the
concrete occurrence ID, and activity proof must come from the same simulated day.
A garden event can therefore satisfy a plan already targeting
`community_garden`, but cannot retarget a library plan, create a strategy, or
advance a goal without the normal strategy activity and provenance checks.

Event tags are descriptive context only. Dynamic templates cannot use authority-
suggesting tags such as `market`, `business`, `seller`, `employment`, `crime`, or
`justice`; event selection itself does not move money or goods, add stock or
production, create jobs or commitments, mutate relationships, produce legal
evidence, advance goals, or alter location activation.

Run the Phase 3 acceptance gate with:

```bash
python scripts/evaluate_event_ecology.py
```

It uses real engines and `FakeLLMClient`, compares two seeded 180-day runs across
a save/resume boundary, exercises organic attendance and conversation, checks an
exact V4 dependency and stale recurrence rejection, attacks malformed persisted
authority, and composes the existing economy, materials, crime, justice,
commitment, plan, migration, location, and outcome-memory validators.

## Phase 4: bounded institutions and endogenous employment

Phase 4 closes one static-economy gap without adding general organization or
commerce simulation. `data/town_growth.json` contains one finite
`Community Garden Stewardship` template, bound to the exact Community Garden
location template and an allowlist of the two exact garden event templates. It
declares one civic role, `community garden steward`, whose sole work route is
`steward_community_garden` at `community_garden` for 18 credits.

```text
migration → activated garden → repeated authoritative use
          → exact dynamic garden occurrences
          → scheduled formation review
          → institution:0001 + zero-baseline employer account
          → conserved startup grant + one authoritative employment
          → next-day ordinary steward activity → ordinary wage transfer
```

`InstitutionGrowthSystem` recomputes readiness from live authority. The default
review requires day 70 and the seven-day schedule, unused capacity and template,
an exactly activated bound location, sustained recent use by multiple distinct
residents, at least two exact allowlisted dynamic occurrences, an evidence-backed
unemployed resident with an existing personal account, and sufficient startup
funds. Tags, dialogue, journals, memory text, and serialized readiness do not
count. Candidate ordering is deterministic: most bound-location activities,
then most exact dynamic-event attendances, then stable agent ID.

Formation is a narrow atomic operation. Complete preflight precedes registration
of an institution-owned account with balance and reconstruction baseline both
zero, one provenance-bearing `Employment`, and an ordinary startup transfer with
event key `institution-startup:<formation-id>`. Only after those succeed is the
template consumed and formation activated. An unexpected failure restores the
economy, institution state, and memories together. The employee keeps their one
resident account and their legacy `Agent.occupation`; the latter remains
biography, not job authority.

The authoritative employment contract specifies the exact activity and exact
location. `steward_community_garden` at `market` is not work and cannot earn a
wage. On following days the ordinary activity planner may consume the active job
opportunity independently of occupation text. `ActivitySystem` records it, and
the existing `EconomySystem.process_activity` path checks employment, start day,
work tag, activity, location, and once-per-job/day wage key before transferring
money. Current authoritative title is exposed to dialogue context, but model text
cannot create, alter, or prove employment.

One public formation fact per resident and one private employment fact for the
employee are projected from the activated formation using stable causal IDs.
They describe authority but cannot create it. Save state persists schema-versioned
bounded reviews, formation records, replay keys, consumed templates, assignment
provenance, and public history; executable templates remain checked-in config.
Load cross-checks location activation, institution account owner and zero
baseline, exact startup ledger entry, employee/account, job/role/wage/activity/
location contract, and absence of orphan institution economic state. Old saves
without Phase 4 state load with no dynamic institution.

No seller, business inventory, good, price, purchase route, stock, production
recipe, profit, or owner equity is created. The existing configured market seller
and production route are untouched. Institution activation likewise grants no
crime, justice, commitment, V4 strategy, place, or event authority. Run the
240-day repeated-seed, save/resume, adversarial gate with:

```bash
python scripts/evaluate_institution_growth.py
```

V5 remains deliberately bounded. It does not provide arbitrary LLM-generated
events, simultaneous event calendars, arbitrary festivals, dynamic sellers,
business inventories, dynamic production recipes, new goods, market pricing,
entrepreneurship, profits, firm ownership, business competition, general hiring
markets, firing, job switching, multi-role institutions, organization politics,
taxation, dynamic construction supply chains, resident departure, demographics,
land ownership, zoning, roads, pathfinding, or unrestricted procedural
civilization generation.
