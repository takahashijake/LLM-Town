# Overnight engineering progress

## V3 production hardening continuation (2026-09-24)

- Actual start was clean `6473793` on `main`, aligned with `origin/main`; the
  requested `1abaa3d` checkpoint had already advanced through the initial
  engine-planned implementation.
- Expanded the immutable content plan to explicitly carry speaker/listener,
  required/optional/prohibited history use, permitted fact, and knowledge basis,
  while preserving engine ownership of reference, polarity, counterpart, intent,
  follow-through, and prohibitions.
- Added explicit surface-validation outcomes for omitted history, reversed
  polarity, private leakage, unsupported inference, wrong counterpart, authority
  claims, and unparseable output. Added characterization tests for plan immutability
  and evaluator telemetry.
- A planned turn now handles an ordinary model exception with an immediately
  validated event-specific fallback and no retry loop; the exception remains
  advisory diagnostic telemetry.
- Extended future live artifacts with plan/engine/surface fields, initial versus
  repaired result, repair success, final safety/polarity, latency, and grouped
  event/history/repair breakdowns. Preserved the completed 144-generation run;
  no unchanged arm or model was regenerated.
- Audited archived H failures: 7B invalid references were fact text emitted as an
  ID in two unwitnessed-accusation samples; 3B realization misses concentrated in
  cancellation, witnessed theft, archived fulfillment, adjudication, and boundary
  uncertainty/accusation cases. Details are in `docs/grounded_dialogue.md`.
- Final production-only live run completed: 144 generations, with 100% parse,
  required surface history, polarity, counterpart, and engine-reference validity;
  zero intrusion, leakage, authority contradiction, runtime failure, or truncation.
  3B repair/fallback improved to 13.89%/13.89% and remains safe degraded on the
  fallback ceiling. 7B measured 18.06%/8.33% and remains safe degraded on the
  repair ceiling. Planned rendered prompts were 1,035–1,092 characters.

## Engine-planned grounded realization V3 gate (2026-09-23)

- Starting SHA `1abaa3d331205d5d9fd75cae181482c3b7808afe`; clean `main`, aligned
  with `origin/main`.
- Implemented an engine-owned content plan for history use, selected visible
  reference, authoritative event/polarity, counterpart, social intent,
  follow-through eligibility, and forbidden assertions. Planned model output is
  utterance-only; any emitted metadata is advisory and disagreements are logged.
- Added narrow polarity contracts for fulfilled, failed, expired, cancelled,
  private completion/failure, witnessed crime, unknown culprit, adjudication,
  restitution, and material completion. One bounded repair precedes an
  event-specific, state-neutral fallback.
- Added regressions proving invented metadata cannot replace the engine reference
  and correct engine metadata cannot make reversed surface meaning pass.
- Targeted five-case seed-42 failure cluster: both models had 100% history and
  polarity after recovery with zero hard-safety failures; 3B repair/fallback was
  4/5 and 3/5, 7B was 2/5 and 1/5.
- Final D run, 72 samples/model: both had 100% parse/history/polarity/counterpart/
  engine-reference validity and zero leakage, authority contradiction, intrusion,
  or runtime failure. 3B repair/fallback was 19.44%/19.44%; 7B was 15.28%/6.94%.
  Both are honestly classified safe degraded; thresholds were not weakened.
- A–D only: prompted JSON, planned meaning with model metadata, engine metadata,
  and engine metadata plus repair/fallback. D was selected as the only safe path
  that closes all surface failures. Neither model currently supports advancing
  V3 to broader social follow-through.
- Verification so far: compileall PASS; 573 tests PASS; grounded evaluator PASS;
  all prior deterministic commitment, planning, social, relationship, economy,
  material, production, crime, justice, causal-memory, and Whole V2 evaluators
  PASS.

## Reliable live grounded dialogue V3 gate (2026-09-23)

- Starting SHA: `c60aa0076ded1268336cbeb9ef3c8850491ee5a5`; clean `main`
  aligned with `origin/main` (not one commit ahead as the prompt expected).
- Initial verification: `git diff --check` and compileall PASS; 554 tests PASS.
- Provider audit: both Qwen paths use local cached weights through Transformers
  5.17.0 `AutoModelForCausalLM.generate` on CUDA. There is no configured native
  JSON schema/grammar/JSON mode/tool output. Supported application modes are
  explicit `prompted_json` and `legacy_text`; native requests fail clearly.
- Added `grounded-dialogue-balanced-v2`: 24 cases in balanced 8/8/8 must/may/must-
  not-use classes, three fixed seeds, precise per-failure metrics, exact prompt/raw/
  parsed evidence, capability metadata, and the isolated A–H experiment runner.
- Frozen baseline (72 samples/model, exact inherited contract): 3B parse 94.4%,
  valid refs 100%, required use 0%, irrelevant intrusion 0%, polarity 58.3%,
  seven truncations and one unsupported claim; 7B parse 80.6%, valid refs 87.3%,
  required use 41.7%, intrusion 20.8%, polarity 71.9%, and 21 truncations.
  Both had zero private leakage, authority contradictions, and runtime failures.
- 3B isolated results: prompted constraint control and parser-only matched baseline;
  simplified schema 0% required use / 50% polarity / 100% parse; prompt-only
  0% / 25% / 69.4% parse with 31 truncations; few-shot 0% / 30.8% / 100% parse;
  combined 16.7% / 53.1% but regressed valid refs to 70.7% and intrusion to 20.8%.
  The first two-stage run was contaminated by that unsafe combination and is being
  replaced with a plan layered only over the safe compact/refined contract.
- Completed 7B isolated results: prompted constraint control and parser-only
  matched baseline; simplified schema required use 25.0%, refs 80.5%, intrusion
  20.8%, polarity 62.7%; prompt-only 33.3%/83.7%/20.8%/60.4%; few-shot
  37.5%/87.2%/20.8%/65.3%; combined 29.2%/76.9%/16.7%/58.7%. None is
  adoptable, and all remained free of private leakage, authority contradiction,
  and runtime failure.
- Corrected two-stage result (irrelevant facts withheld before realization): 3B
  parse 100%, refs 100%, required use 62.5%, intrusion 0%, polarity 62.5%; 7B
  parse 100%, refs 95%, required use 79.2%, intrusion 0%, polarity 85%. Both had
  100% counterpart accuracy and zero leakage/authority/runtime failures. This is
  a material semantic improvement but misses hard gates, so it is experimental
  only and is not wired into ordinary conversation.
- Selected production mode: capability-aware `prompted_json` with existing
  deterministic validation and safe fallback. Bounded parser normalization is
  retained; optional repair is one format-only retry and never invents a ref.
  Neither model currently has a freeze-quality reliability envelope: 3B is safe
  but ignores history; 7B is more responsive but not reference/polarity reliable.
  V3 must not advance to broader social follow-through on this evidence.

## Grounded dialogue continuation (2026-09-23)

- Starting SHA: `9cf1ca742f10d8ebfaf6d86690fe783e7cc8df54` (`main`, clean,
  aligned with `origin/main`); requested checkpoint `99ae9d9` had already advanced
  through `b067256` (grounded dialogue) and `9cf1ca7` (repository instructions).
- Initial validation: `compileall` PASS; `git diff --check` PASS; 553 tests PASS.
- Current milestone: final validation and handoff.
- Completed: live-state verification; conversation/grounding/authority path audit;
  baseline deterministic suite.
- Architecture decisions: retain source systems as sole authorities; prompt-local
  `gN` facts remain advisory; follow-through continues through existing proposal
  recognition and counterpart acceptance; no new trust score.
- Baseline grounded metrics at inherited checkpoint: 15 scenarios, 19/19 stated
  invariants, 100% validator reference/polarity figures, zero reported leakage or
  authority violations. Cached legacy 3B/7B history use is 0%; parse success is
  100%/37.5%. These cached artifacts predate the new balanced schema.
- Known weaknesses: inherited evaluator derives several metrics from scenario
  flags rather than validator observations; packet text was added after the
  prompt budget calculation; final prompt JSON example omitted follow-through.
- Completed milestone: grounding packet now participates in the 2,400-character
  prompt budget; the final prompt schema advertises optional metadata; targeted
  follow-through requires the cited visible counterpart; cancellation,
  adjudication, and private completion have distinct polarity labels.
- Validation: `compileall` PASS; `git diff --check` PASS; 554 tests PASS. Required
  deterministic evaluators for commitments, execution, semantics, accountability,
  planning, social decisions, relationships, economy, materials, production,
  crime, justice, causal memory, grounded dialogue, and Whole V2 PASS.
- Cached evaluation: legacy 3B valid (100% parse, 0% history use); legacy 7B valid
  (37.5% parse, 0% history use). Fresh local live runs at starting SHA: 3B
  historical arm 0/4 use, 0 contradictions, 0 malformed (recent-only 1/4
  malformed); 7B historical arm 0/4 use, 0 contradictions, 2/4 malformed
  (recent-only 4/4 malformed). Real-model targets are not met.
- Artifact limitation: causal-memory stress analysis requires explicit generated
  long-horizon save states; the previously reported seed-42/73 paths are not in
  this checkout. No replacement 250/500-day campaign was fabricated.
- Checkpoint commits: inherited `b067256`; no new checkpoint commit yet.
- Next action: final diff review and local checkpoint commit after green verification.

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
