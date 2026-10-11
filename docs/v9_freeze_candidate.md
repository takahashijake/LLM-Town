# V9 freeze candidate

**Local release gates: PASS**, verified 2026-10-11 with Python 3.13.11.
This is a review candidate, not a merged release or GitHub tag.

Runtime implementation revision: `282ec1572f6e9d0fec0f8ff9e4aaf55ac7df2204`.
Exact stacked base: `83a99244b6df19f876a43b5953681c7045c2d936`, open V8 PR #5.
Main at reconnaissance: `cd55b2c40c37d078b2d6ae9df705405f141155cc`.
[V9 PR #6](https://github.com/takahashijake/LLM-Town/pull/6) targets
`v8-causal-inspection` and remains unmerged. Final delivery also includes the
verification/documentation commit; its runtime source is unchanged.

| Gate | Executed result |
| --- | --- |
| Clean V8 baseline | 1,038 passed, zero failures |
| Complete V9 regression | 1,139 passed, zero failures/errors/skips; 101 new tests |
| Feature + V7/V8 inspection acceptance | 197 passed |
| Compileall, scoped Ruff E9/F, diff checks | PASS |
| Normal V6 freeze, hash seed 1 | 77 scenarios, 42 invariants, 35 checkpoints, 730 mutations |
| Comprehensive V6 freeze, hash seed 77 | 77 scenarios, 42 invariants, 69 checkpoints, 730 mutations |
| V9 model-free evaluator/showcase | 29/29 PASS; four independently reconstructed boundaries |
| Institution / event ecology / commitment execution evaluators | 30/30 + 22/22; 28/28 + 21/21; 20/20 |

The unchanged V6 release digest in both modes is:

```
9aec1a80d08364b98816a0607c719933ff41420abedf99e49e929c5b6f0760df
```

The enabled V9 seed-11, 100-day authoritative signature is identical for the
uninterrupted world and reconstruction from formation, one contribution,
pre-completion review and completed effect:

```
cc7883f38f910375e390c773e217eb796d13c109e7f58cd9c09e37462b2664a5
```

This compares deterministic systems including economy, materials, crime, justice,
commitments, plans, all growth systems and project authority; it also compares
selected activity references, resident needs/locations, relationship scores,
public goal/intent/arc state and daily events. Private UUID-bearing memories are
outside this signature. Fresh-process continuation and deterministic read-only
inspection are separately checked. Entire-save byte equivalence is not claimed.

The implemented vertical slice activates the project on day 70; four independent
residents execute garden preparation on days 72, 75, 82 and 84. The incomplete
checkpoint has no benefit. Verified completion makes the garden workshop
available on day 85, with six subsequent real learning sessions. Rejected actor
forgery withholds progress/effect edges. Expiration and cancellation grant no
completed-project benefit; mid-day cancellation resumes with the terminal state.

```bash
python scripts/evaluate_v9_collective_projects.py --output /tmp/llm-town-v9
python scripts/inspect_town.py trace /tmp/llm-town-v9/uninterrupted.json \
  --type project --id civic-project:garden_learning --format text
```

The normal/comprehensive V6 thresholds, existing tests and baseline signatures
were not modified. V9 is disabled by default and adds no save fields or arbitration
randomness in that configuration. Generated worlds, dialogue and logs are not
committed. CI uploads controlled reports only.

Remaining limits are explicit: one finite garden project, activity work only,
activation-time participant roster, no resource donations or terminal retries,
shared Python RNG for simultaneous engines in one process, upstream whole-save
history growth, and internal consistency rather than cryptographic authenticity.
Independent resident arbitration may produce expiration in other trajectories.
The full architecture, adversarial findings, exact commands and performance
measurements are in [contracts](v9_collective_projects.md) and
[verification](v9_verification.md). GitHub head CI status must be checked separately;
this candidate's PASS refers to completed local gates.
