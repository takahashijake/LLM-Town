# Grounded dialogue and social follow-through

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
```

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
