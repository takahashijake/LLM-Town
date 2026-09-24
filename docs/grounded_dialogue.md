# Grounded dialogue and social follow-through

## V3 production architecture

Grounded dialogue now uses an engine-planned, two-stage path. Deterministic code
selects whether history applies and owns the visible `gN` fact, event type,
outcome polarity, counterpart, social intent, follow-through eligibility, and
forbidden assertions. The model receives that bounded plan and realizes it as a
natural utterance. It does not decide provenance, ownership, culprit identity,
counterpart identity, outcome, or whether follow-through is legitimate.

Any model-emitted metadata is advisory and retained as disagreement diagnostics.
The parsed production record always uses the engine-selected reference; invented
or misspelled IDs cannot displace it or reject an otherwise safe utterance.
Surface language is scored separately, so correct metadata cannot make an
incorrect or polarity-reversed utterance count as grounded.

The immutable `GroundedDialoguePlan` names the speaker and listener, classifies
history use as required/optional/prohibited, and carries only the selected
prompt-local reference, event type, polarity, counterpart, knowledge basis,
concise permitted fact, social intent, follow-through category, and prohibited
assertions. It is ephemeral guidance, never saved world state. The live planner
constructs it only from the current speaker's already-filtered grounding packet;
it does not search global systems or another resident's memory.

The validator has narrow event-specific contracts for fulfilled, failed, expired,
cancelled, private-plan completion/failure, witnessed crime, unknown culprit,
adjudication, and completed restitution/material outcomes. A contradiction gets
at most one plan-scoped repair. Failure then produces a personality-neutral,
event-specific utterance without mutating state. Repair, fallback, and metadata
disagreement are recorded on the turn.

### Final capability tiers (24 cases × 3 seeds)

Production candidate D passed every safety requirement for both cached local
Qwen models: private leakage 0, authority contradictions 0, counterpart accuracy
100%, engine-owned reference validity 100%, and runtime failures 0. Both also
reached 100% parse success, required-history realization, and polarity accuracy,
with 0% irrelevant-history intrusion.

- Qwen2.5-3B is **safe degraded support**: repair 13.89%, deterministic fallback
  13.89%. It passes the repair ceiling but exceeds the 10% fallback ceiling.
- Qwen2.5-7B is **safe degraded support**: repair 18.06%, deterministic fallback
  8.33%. It passes the fallback ceiling but exceeds the 15% repair ceiling.

The targeted prior-failure cluster (five cases, seed 42) was safe and 100%
correct after recovery: 3B repaired 4/5 and fell back 3/5; 7B repaired 2/5 and
fell back 1/5. These deliberately concentrated rates are not capability rates.
The one-seed A–D ablation confirmed that A (prompted JSON), B (plan plus
model-owned metadata), and C (engine metadata without recovery) all fail quality
gates. D is selected because it alone closes surface failures while preserving
the authority boundary. Since neither supported model meets the full-quality
repair/fallback envelope, V3 should not yet advance to broader social
follow-through.

The runtime exposes this classification through `--grounded-dialogue-tier` and
prints the selected tier at startup. The setting is capability-based rather than
derived from a model-name allowlist. Use `unverified` for a model/configuration
that has not passed this benchmark.

### Experimental two-stage characterization

The archived H arm deterministically selected a visible benchmark fact and its
required polarity, but still asked the model to emit the grounding reference,
intent, and follow-through metadata. History counted only when a supplied allowed
reference, required surface terms, and non-forbidden meaning all agreed. The 7B
95% reference result came from `must_not_unwitnessed_accusation` emitting fact
text as an ID in seeds 42 and 101. Its polarity misses clustered in fulfillment,
unknown-culprit uncertainty, cancellation, and restitution. The 3B misses
clustered in cancellation, witnessed theft, archived fulfillment, adjudication,
unknown-culprit uncertainty, and unwitnessed accusation. These records
characterize the old behavior; benchmark scaffolding was not copied into the
runtime planner.

Generation caching keys include model digest, exact prompt hash, content-plan
hash, seed, generation configuration, and parser version. Development used stored
baselines and targeted failures; only D received the final three-seed run.
The final post-hardening artifacts are in `outputs/grounded_dialogue/v3-production-final/`.
Their planned-realization chat prompts are 1,035–1,092 characters, below the
2,400-character limit; the engine plan itself renders to at most 713 characters.

## Contract and knowledge boundary

Conversation retrieval remains the only entrance to historical context. After
the existing bounded selector chooses at most three memories, provenance-backed
causal memories owned by the current speaker are projected into a grounding
packet of at most three facts. Each prompt-local `gN` reference carries a
concise fact, event type, knowledge basis, relevant counterpart, day/age, and
explicit outcome polarity. Authoritative IDs, private provenance internals,
hidden plan reasons, and other agents' memories are not rendered.

The packet distinguishes accepted, fulfilled, failed/expired, privately failed
plans, witnessed theft, unknown-culprit loss discovery, and completed
restitution. Empty packets and ordinary recent dialogue context are valid.

## Optional response envelope

Models may return `utterance` (or legacy `dialogue`), `grounding_refs`,
`social_intent`, and `{kind,target,source_ref}` follow-through metadata alongside
the existing action, response, and commitment fields. Plain text, missing
fields, and malformed JSON continue through the established fallback path.
The envelope records a model claim; it is not proof.

Validation resolves references only in the current prompt, checks polarity,
unknown culprits, private-plan knowledge, counterpart scope, and an allowlist of
follow-through kinds. Invalid metadata is removed and recorded. The runner may
retry live generation, then uses safe ordinary dialogue without authoritative
mutation.

## Authority and follow-through

Dialogue cannot move money or goods, change ownership or plans, create evidence,
convict anyone, complete restitution, or fulfill a commitment. A repair remains
a spoken proposal. The existing proposal recognizer, counterpart acceptance,
commitment lifecycle, material system, and idempotency keys remain authoritative.
Follow-through metadata adds no relationship or reputation score, avoiding
double counting; it makes appreciation, explanation requests, apologies,
bounded repair proposals, similar-proposal reluctance, and cooperation
inspectable.

## Evaluation

```bash
python scripts/evaluate_grounded_dialogue.py
python scripts/evaluate_grounded_dialogue.py --cached data/grounded_dialogue_cached_3b.json
python scripts/evaluate_grounded_dialogue.py --cached data/grounded_dialogue_cached_7b.json
python scripts/evaluate_grounded_dialogue.py --live-model 3b --output outputs/grounded_dialogue/live-3b.json
python scripts/evaluate_grounded_dialogue.py --live-model 7b --output outputs/grounded_dialogue/live-7b.json
python scripts/benchmark_grounded_dialogue_live.py --models 3b 7b --seeds 42 73 101
```

### V3 balanced live contract

`data/grounded_dialogue_benchmark_v2.json` is the versioned acceptance corpus:
24 cases, evenly divided among history-must-be-used, history-may-be-used, and
history-must-not-be-used. It includes counterfactual fulfilled/failed and
counterpart pairs plus cancelled commitments, self-private plan outcomes,
witnessed crime, unknown culprit, adjudication, restitution, acquisition, and
recent/archived memory. Every case declares allowed and forbidden references,
required polarity/terms, forbidden claims, social intents, and follow-through.

The live runner stores the commit and model/config digests, Transformers version,
full chat template, seeds and sampling controls, token limit, benchmark and prompt
hashes, exact rendered prompts, raw responses, parsed responses, validator result,
retry count, and separate failure classifications. Generated artifacts live under
`outputs/grounded_dialogue/v2/` and are not test dependencies.

The local provider is `AutoModelForCausalLM.generate` through Hugging Face
Transformers. It supports `prompted_json` and backward-compatible `legacy_text`
in this application. No JSON-schema, grammar, JSON-mode, or tool-output processor
is configured; requesting a native mode fails explicitly. Both Qwen sizes use the
same provider path and tokenizer-specific chat template. Generation uses 120 new
tokens, temperature 0.4, top-p 0.9, the recorded seed, EOS padding, and no custom
stop strings. Consequently the “constrained decoding” ablation is an honestly
recorded prompted-JSON control, not native constrained decoding.

The compact canonical response contract is defined in
`src/llm/response_contract.py`. The parser accepts legacy `dialogue`, compact
`utterance`, known `response`/`text` aliases, code fences, whitespace, and harmless
surrounding text. It never repairs reference IDs, polarity, counterpart, private
facts, or follow-through semantics. An optional format repair receives only the
invalid output, concise parse error, and compact shape, runs at most once, and is
separately counted.

Metrics intentionally separate schema parsing, legacy fallback, valid references,
required and optional use, irrelevant intrusion, polarity and counterpart accuracy,
unsupported claims, private leakage, authority contradictions, runtime failure,
truncation, retries, valid-but-wrong structure, parser rejection, and ignored
history. A reference alone does not count: required use also needs matching content
and preserved polarity with no forbidden claim.

V3 records additionally expose plan creation, required/optional/prohibited history,
surface realization, engine metadata attachment, advisory disagreement, initial
and final validation outcomes, repair attempted/succeeded, fallback use, final
safety and polarity, and elapsed latency. New artifacts include breakdowns by
event type, history-use category, initial validation result, and repair result.

### 2026-09-23 reliability envelope

All A–H arms ran 24 cases × seeds 42/73/101 for each model. The frozen baseline
used the exact inherited envelope and was 3B: parse 94.4%, refs 100%, required use
0%, intrusion 0%, polarity 58.3%, seven truncations; and 7B: parse 80.6%, refs
87.3%, required use 41.7%, intrusion 20.8%, polarity 71.9%, 21 truncations.
There was no private leakage, authority contradiction, or runtime failure.

No isolated change passed. For 3B, compact schema/prompt/few-shot/parser/combined
required-use rates were 0/0/0/0/16.7%; the combination regressed refs to 70.7%
and intrusion to 20.8%. For 7B the same arms were 25/33.3/37.5/41.7/29.2%, with
reference validity 76.9–87.3% and intrusion 16.7–20.8%. The provider-constrained
control matched baseline because native decoding constraints are unavailable.

The corrected two-stage experiment withheld irrelevant facts and deterministically
selected only visible allowed facts for required cases. It reached 62.5% required
use / 62.5% polarity for 3B and 79.2% / 85% for 7B. Reference validity was
100%/95%, intrusion 0%, counterpart accuracy 100%, and all hard leakage/authority/
runtime counts remained zero. This is material improvement but still fails the
frozen gates, so it remains an experiment rather than production behavior.

The viable safety mode is therefore prompted JSON plus deterministic validation
and safe fallback, not a freeze-quality grounded-response mode. 3B is structurally
reliable but usually ignores historical facts; 7B uses them more often but can
emit invalid reference content and miss polarity. Broader social follow-through
must wait for a backend with real constrained decoding or a better realization
model followed by the same benchmark.

Ordinary tests never load a model. Artifacts require model/configuration, commit
SHA, seed, scenario version, context hash, timestamp, parser version, validator
version, and metrics. The preserved legacy cached baseline shows zero historical
use in both models and 37.5% parse success for the old 7B run. The deterministic
suite reports validity, history, polarity, leakage, irrelevant intrusion,
malformed output, authority, follow-through, and repetition across 15 scenarios.

Known limitation: validation intentionally handles structured references and
high-risk claim shapes, not unrestricted semantic truth. Fresh live balanced
artifacts are needed for post-change real-model quality; cached legacy artifacts
measure the pre-change causal-memory prompt.

The grounding packet is counted inside the existing 2,400-character dynamic
context ceiling. Targeted follow-through (`propose_repair`, `decline_similar`,
and `cooperate`) is accepted only when its target is the counterpart exposed by
the cited prompt-local fact. Cancellation, adjudication, and private completion
retain distinct polarity labels rather than falling back to neutral.

## Recorded baseline and ablation

The preserved pre-change cached causal-history runs produced 0% correct history
use for both 3B and 7B. A first live pass also exposed and corrected an ablation
bug: disabling rendered memory had left the new packet enabled. With a true
packet-removal arm, the final listener-relevance instruction raised the 3B
history-use rate from 0% to 25% (4 enabled-arm samples), with 0% contradiction,
malformation, and runtime failure. The 7B result remained 0% history use with
0% contradiction and malformation. Both miss the 90% polarity-use quality goal;
the results are retained honestly, and broader live balanced coverage remains a
known limitation rather than being inferred from the deterministic suite.

On 2026-09-23, fresh local runs at `9cf1ca7` completed with cached model weights.
The 3B historical arm had 0/4 historical use, 0 contradictions, and 0 malformed
outputs (recent-only malformed: 1/4). The 7B historical arm had 0/4 historical
use, 0 contradictions, and 2/4 malformed outputs (recent-only malformed: 4/4).
These runs therefore do not meet the real-model quality targets, despite the
deterministic safety suite passing.
