# V8 reconnaissance and baseline

Connected GitHub and `git fetch origin main` both confirmed starting main
`cd55b2c40c37d078b2d6ae9df705405f141155cc`. Starting working tree was clean.
Work branch: `v8-causal-inspection`. No open PRs at reconnaissance; merged PR #4
introduced V7. Open roadmap issue #3 requests growth observability and release
assurance. Actions run 37713791903 failed with 947 passes and one failure in
2979.04 seconds; its integrated freeze step was skipped.

Local reproduction: inspector tests 5 passed / 1 failed in 0.15 seconds. The
fixture already persisted `economy.ledger`, but the comparison test still mutated
and asserted `economy.transactions`. Both stale paths are repaired. A regression
uses `SimulationEngine.state.save` and verifies every inspector collection path
exists with the correct list shape, and a real ledger modification changes its
projection signature. Focused baseline: 7 passed in 0.04 seconds; compileall passed.
Full baseline and release results are recorded below when execution completes.

## Authority boundaries and audit findings

`SimulationState.save` persists plain JSON, without a global save schema version.
Economy schema 1 owns conserved balances and ledger. Materials schema 2 owns
transfers, exchanges, consumption, recipes, lots and movement commit order.
Growth systems own review/activation records; generated templates are persisted
in growth proposals, while configured templates and policy remain external
configuration. Commitment dictionaries have no version; plans are schema 7 with
legacy migrations. The inspector must not hydrate an engine, migrate authority,
invoke a transition or use a provider to compensate for missing evidence.

V7 report schema 1 supports timeline, exact-ID association views and source
projection comparisons. Its allowlist omits real `source_account_id`,
`destination_account_id`, `monetary_transaction_id`, `inventory_transfer_id`,
formation employment/account references and lifecycle dates. Chronology uses
only `day/hour`, missing review/activation/created/start dates. Inspection
truncates to 1000 before identity filtering, silently excluding late matches.
Source-local ordinals avoid inter-source collisions but do not resolve typed
references. File size, collection types and resource budgets are unchecked.
Narrative/nested fields are excluded, but scalar values still need bounded safe
presentation. Empty and absent collections are indistinguishable.

Highest risks: falsely promoting shared IDs into causation; substituting valid
other-branch identities; production ancestry without input ownership at commit;
legacy/pruned history appearing complete; sensitive nested proof text; and large
histories exhausting memory. Existing tests do not cover these inspector cases.

## Design decisions

Use a bounded JSON reader, independent safe projection registry, immutable typed
record identities, pure reference-contract checks and a bounded graph traversal.
Keep the V7 facade and its report version; introduce a separately versioned causal
report. Facts report persisted observations, verified dependencies name explicit
contract checks, associations are never traversed as causes, and unresolved
proof carries controlled diagnostics. No simulation save extension is needed.

Prefer explicit narrow contracts over generic ID joins or rehydrating the world:
ID joins cannot establish causal direction, and rehydration requires external
policy/configuration and can migrate old saves. Material replay needs its common
movement sequence, not arbitrary timestamp tie ordering. Separate namespaces
and reciprocal bindings preserve legitimate shared upstream lots without joining
separate branch registries. A partial trace is useful only when incompleteness
is visible; it must not claim to prove full formation eligibility from retained
records alone. Release coverage remains intact; independent CI jobs allow fast
inspector diagnosis and freeze results even when another gate fails.
