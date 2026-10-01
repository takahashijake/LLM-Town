# V5 dynamic town evolution: bounded resident migration

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

