# V8 testing and review guidance

## Fast development tier

```bash
python -m compileall -q src scripts tests
python -m ruff check --select E9,F src/analysis/inspection_*.py src/analysis/simulation_inspector.py src/analysis/causal*.py scripts/inspect_town.py scripts/showcase_v8.py tests/analysis/test_causal_inspector.py tests/analysis/test_simulation_inspector.py
python -m pytest tests/analysis/test_simulation_inspector.py tests/analysis/test_causal_inspector.py -m "not integration" -q
```

Scoped Ruff checks syntax, undefined/unused names and imports in the selected
inspection/causal analysis modules, inspector scripts and tests. It adds no repository-wide formatting rewrite.
Install test dependencies with `python -m pip install -r requirements.txt -r
requirements-dev.txt`. The existing full suite remains mandatory.

## Integration and regression tiers

```bash
python -m pytest tests/analysis/test_simulation_inspector.py tests/analysis/test_causal_inspector.py -q
python -m pytest -q
```

The focused module builds actual saved engine states, same-tick commerce, a
save/resume transfer plan and a seeded 180-day two-branch V6 world. Regression
coverage includes schema paths, reciprocal references, wrong-type IDs, valid
other-branch substitutions, coherent location forgery, shared upstream lots,
missing movements, wrong ancestry, chronology, identity collisions, cycles,
bounds, malicious fields, JSON errors, stable hash-seed/insertion-order reports,
unchanged input/save bytes, and blocked constructors/transitions/model imports.
The field mutation matrix removes, nulls and changes the shapes of fields in real
persisted records; controlled rejection/uncertainty is required without crashes
or leaked text. Narrative-only changes need not invalidate unrelated authority.

## Release assurance tier

```bash
PYTHONHASHSEED=1 python scripts/evaluate_v6_freeze.py --output /tmp/v8-freeze.json
PYTHONHASHSEED=77 python scripts/evaluate_v6_freeze.py --comprehensive --output /tmp/v8-comprehensive.json
python scripts/showcase_v8.py --output /tmp/v8-showcase
git diff --check
```

The original V6 thresholds, scenarios and invariants are unchanged. Normal and
comprehensive modes must agree on their authoritative signature. Comprehensive
mode independently continues checkpoints. Real-model smoke remains optional,
separate from causal correctness. Generated output is not committed.

CI has independent `inspector-fast`, complete `pytest`, normal/comprehensive
`release-assurance` matrix jobs and `showcase` jobs. No failing job prevents the
freeze jobs from executing; all required coverage remains present. Each job has
an isolated runner and output path. CI artifacts report full-suite JUnit results,
freeze diagnostics and privacy-controlled showcase reports.

## Final adversarial review

Correctness: verified dependencies require explicit reciprocal contracts;
formation/commerce eligibility and help/meeting outcome gaps remain unresolved.
Security: fixed labels, identifier/structure/output budgets, nested-text exclusion
and safe error paths keep injected narrative out of explanations.
Simulation architecture: no transitions, constructors, save migrations or state
schemas were modified; tests block transition calls during inspection.
QA: actual saved worlds supplement tiny unit fixtures and field mutations. Valid
other-branch references and coherent forgeries catch more than nonexistent IDs.
Maintenance: reading, projections, evidence/index/traversal, system contracts and
presentation are separate modules; scoped lint avoids unrelated changes.
Performance: indexed recipe/source matching and bounded repair/traversal avoid
repeated whole-history joins. Occurrence associations are independently capped.

Review findings fixed: pre-filter truncation; missing real schema fields/date
projection; CLI import bootstrap; malformed exchange chronology escaping controlled
diagnostics; cross-branch location substitution lacking work-location binding;
material identity namespace impersonation; same-day repair order; explicit reconciled current-holder facts; avoidable
commerce/plan joins; missing input/output budgets. Corresponding focused tests
cover these paths. See `v8_verification.md` for executed acceptance results.
