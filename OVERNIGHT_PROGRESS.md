# Overnight engineering progress

## Causal memory run (2026-09-22)

- Starting SHA: `54c102b43e0ba65c39c30101213877e77fc86225` (clean worktree).
- Baseline: compileall and `git diff --check` PASS; 542 tests PASS.
- Baseline evaluators: commitments 20/20; execution 20/20; semantics 45;
  accountability 10 scenarios/20 invariants; social decisions 14/14; Whole V2
  22/22; long-horizon planning 8 scenarios/14 invariants — all PASS.
- Completed: architecture audit; structured provenance; shared owner-scoped
  projection; commitment/private-plan integration; salience-aware bounded archive;
  bounded historical prompt retrieval.
- Checkpoint: `ce8f532` — provenance-preserving causal memory projection.
- Current phase: final regression/evaluator audit.
- Decisions: source systems remain authoritative; explicit recipients and knowledge
  bases are mandatory; causal IDs include owner/source/event; private plan failure
  is self-only; existing relationship/reputation remains the social-pressure path.
- Deterministic acceptance: 11/11 causal-memory scenarios and 13/13 invariants
  PASS; full suite 543 passed; planning evaluator remains PASS.
- Long horizon: full 250/500-day fake-model benchmarks completed for seeds 42/73;
  memory stress checks PASS for all four states (archive 500 each, active 24–33,
  causal 2–3, owner duplicates 0, provenance reconstructable). Natural commitment
  count was zero; conversation repetition rose from about 75% to 86%.
- Real model: cached Qwen2.5-3B and 7B, seeds 42/73, 8 matched samples/model.
  Neither model explicitly used the historical fact in this tiny sample; no
  authoritative contradictions/runtime failures. 7B malformed-output rates were
  2/4 recent-only and 3/4 historical; 3B malformed rate was 0/4 in both arms.
- Known weaknesses: natural commitments remain sparse; real-model sample is small;
  long-run dialogue repetition is high. Public adjudication projection is broad
  only when justice configuration explicitly marks adjudications public.
- Final validation: compileall PASS; `git diff --check` PASS; 544 tests PASS.
  Commitments 20/20, execution 20/20, semantics 45, accountability 20/20,
  social decisions 14/14, Whole V2 22/22, planning 14/14, causal memory
  12/12 scenarios and 14/14 invariants, crime, and justice all PASS.
- Next unfinished action: none in the mandatory implementation; report results.

- Original requested starting SHA: `849f24159b60c4959ca33e0d2c418c02d245adad`
- Actual campaign starting SHA: `4777181` (`main`, clean; the expected Phase 3 diff was already committed)
- Current checkpoint SHA: `HEAD` (`Harden long-horizon memory stability and document plans`; parent plan checkpoint `562188f`)
- Completed: baseline/Phase 3 audit; Phase 1 characterization; Phases 2–5 core vertical slice; Phase 7 deterministic evaluator
- Current phase: final freeze/readiness audit
- Architecture finding: goals and intents persist, while executable activities are reconstructed per tick. Commitment acquisition and fulfillment are authoritative but lack a persistent multi-step record.
- Decision: add a deterministic plan authority whose bounded steps reference existing commitment activity types; economy, materials, and commitments remain the only mutation authorities.
- Baseline validation: `pytest -q` → 532 passed; focused commitment tests → 34 passed; `python -m compileall -q src tests scripts` PASS.
- Evaluators: commitments 20/20 PASS; execution 20/20 PASS; semantics 45 examples PASS; accountability 10 scenarios/20 invariants PASS; social decisions 14/14 PASS; Whole V2 22/22 PASS (30 days).
- Implemented: stable bounded plan/step IDs; active/completed/abandoned/failed lifecycle; source ownership; known-action validation; exact persistence; two-tick acquisition/delivery; bounded interruption and three-observation failure; terminal-source invalidation; idempotent authoritative execution records; pair-private accepted/fulfilled/failure memories with provenance tags.
- New evaluator: `python scripts/evaluate_long_horizon_planning.py` → 8/8 scenarios and 14/14 invariants PASS; funnel: 1 created, 1 completed, 1 failed, 1 abandoned, 1 interrupted, 2 steps executed.
- Final validation: `pytest -q` → 542 passed; `python -m compileall -q src tests scripts` PASS; `git diff --check` PASS. All required deterministic evaluators PASS: commitments 20/20, execution 20/20, semantics 45 examples, accountability 10 scenarios/20 invariants, social decisions 14/14, Whole V2 22/22, planning 8 scenarios/14 invariants.
- Known limitations: only transfer-commitment plans exist; blocking currently means deterministic route absence and has no alternate-seller replanning beyond authoritative route rediscovery; causal memories use typed records/provenance tags but no generalized event bus; occupation and need continuity still use existing intents/activities.
- Stability: seed 42 at 30/100/250 days; one seeded plan completed with exactly two execution records and no active leak. At 250 days: 22 activity types, 0 idle records, active memories 27/37/31/33, archives 500 each, 0 duplicate active-memory IDs; currency, material conservation/history/provenance, commitment invariants, and plan invariants PASS.
- Stability fix: end-of-day compression now reapplies the 500-entry archive bound before saving; regression added.
- Real-model note: no new planning-specific real-model run was performed. Planning correctness is model-independent, and the current real-model harness does not expose a plan-aware comparison metric; prior cached Qwen 2.5 3B/7B commitment runs remain the behavioral evidence. Extending that harness is unfinished.
- Next unfinished step: broaden grounded causal outcome memory beyond transfer plans and add plan-aware real-model dialogue metrics before adding plan templates.
