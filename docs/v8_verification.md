# V8 executed verification record

## Repository and baseline

Connected GitHub inspection and an SSH fetch confirmed `takahashijake/LLM-Town`
main at `cd55b2c40c37d078b2d6ae9df705405f141155cc`. The starting working tree was
clean. Work is isolated on `v8-causal-inspection`; main is not merged or modified.
The final production/test revision is
`d19f73a1a06fa57d092fce50e0e020f8c2bbdf96`; the delivery commit additionally
contains this verification record.

Actions run 37713791903 had 947 passes and one failing stale
`economy.transactions` fixture access; its freeze step was skipped. The failure
was reproduced locally (5 passes, 1 failure), repaired to the real `economy.ledger`
path, and then the complete baseline passed: **948 passed in 1077.69 seconds**.
Actual engine-save path and CLI bootstrap regressions were added afterward.
No existing tests, invariants or acceptance thresholds were removed or weakened.

## Executed acceptance commands

| Command | Actual result | Runtime |
| --- | --- | --- |
| `python -m compileall -q src scripts tests` | passed | not separately timed |
| scoped `python -m ruff check --select E9,F ...` from `v8_testing.md` | all checks passed | not separately timed |
| `python -m pytest tests/analysis/test_simulation_inspector.py tests/analysis/test_causal_inspector.py -q` | 96 passed | 31.44 seconds |
| `python -m pytest -q --junitxml=/tmp/v8-final-pytest.xml` | 1038 passed | 1117.36 seconds |
| `PYTHONHASHSEED=1 python scripts/evaluate_v6_freeze.py --output /tmp/v8-final-freeze.json` | passed: 77 scenarios, 42 invariants, 35 checkpoints, 730 rejected mutations | 260.00 seconds |
| `PYTHONHASHSEED=77 python scripts/evaluate_v6_freeze.py --comprehensive --output /tmp/v8-comprehensive.json` | passed: 77 scenarios, 42 invariants, 69 checkpoints, 730 rejected mutations | 1081.60 seconds |
| `python scripts/showcase_v8.py --output /tmp/v8-showcase-release` | passed; two branches, equal reconstructed traces, honest missing-evidence example | 58.90 seconds |
| `git diff --check` | passed | not separately timed |

Freeze runs exercise the unchanged simulation/assurance implementation; subsequent
changes concern only read-only analysis, its tests and documentation. Both modes
produced the same authoritative digest across hash seeds 1 and 77:

```
9aec1a80d08364b98816a0607c719933ff41420abedf99e49e929c5b6f0760df
```

Intermediate full-suite runs interrupted after review-driven code changes are
not acceptance passes. Only the completed final run above counts.

## Deterministic showcase and evidence limits

The real seed-23 V6 scenario completes 180 days with two generated commerce
branches and separate configured Garden commerce. Institution and lot traces
match exactly after an independent 90+90 save/resume reconstruction. Both branch
audits pass. Hash-seed and dictionary-order subprocess tests additionally verify
stable causal signatures. These claims concern authoritative projections, not
legacy UUID relationship histories or LLM dialogue.

Representative first-branch results: institution formation has eight verified
edges at depth two and explicit missing eligibility/readiness witnesses. Its
production-lot trace has 107 verified edges and 15 current-holder facts at depth
five. A copied save with movement history removed produces zero verified material
edges and `missing_historical_movements`. Reproduce with the commands in
`v8_causal_evidence.md`; generated worlds and reports stay outside version control.

Coverage includes real persisted schema contracts, procurement/production/sale,
consumption, plan acquisition and commitment delivery after save/resume, terminal
repair lineage, multi-branch substitutions, shared ancestors, replay conservation,
coherent wrong prices/owners, malformed records, missing/unsupported authorizations,
cycles, bounds, malicious text, exact IDs, repeated queries and non-mutation.

The inspector cannot prove formation eligibility witnesses that were never
persisted, reconstruct pruned material evidence, or certify all social/help/meeting
outcomes. One contradictory material history conservatively quarantines all
material causal edges. File consistency is not cryptographic authenticity.
These limitations are explicit reports and documented debt, not weakened gates.

## CI and delivery

The workflow independently reports fast inspection, complete pytest,
normal/comprehensive freeze and deterministic showcase jobs. CI status belongs to
the delivered PR and must be read from GitHub; local results are not CI results.
The PR is left unmerged. The recommended next milestone is a narrowly designed
persisted eligibility-witness contract, with migration/replay tests, followed by
localized material evidence quarantine.
