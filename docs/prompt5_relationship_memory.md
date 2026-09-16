# Relationship-conditioned social memory

## Integration path

Finalized social actions feed one deterministic relationship update policy. That
policy updates each participant's private view of the other, records a bounded
structured episode, and exposes the resulting delta. Later decisions retrieve
the current counterpart's profile and up to three recent episodes. This context
can affect listener selection, goal strategy and target selection, intent
metadata, social-action weights, and strategy adaptation. The conversation log
records the pre-decision snapshot, retrieved episodes, weight changes, reasons,
and post-interaction deltas.

```text
finalized action/outcome -> directed update -> per-counterpart state + episode
                         -> retrieval -> target/strategy/intent/action policy
                         -> conversation -> structured update
```

## State model

`Agent.relationship_states` is keyed by counterpart name. Each directional
profile stores bounded `[-1, 1]` values for trust, affinity, cooperation,
helpfulness, and hostility, plus interaction and positive/negative counts. An
unseen counterpart is neutral. Alice's view of Bob is independent of Bob's view
of Alice and Carol's view of Bob.

The older `RelationshipManager` score remains a symmetric compatibility layer
for established labels, action availability, and existing reports. It is not a
global reputation. `Agent.reputation_beliefs` continues to represent beliefs
about general conduct and remains separate from direct relationship memory.

## Episodic policy and updates

Each agent keeps at most eight structured social episodes per counterpart. The
most recent episodes survive. Records contain day/hour, counterpart, actor,
finalized action, structured outcome, a template-derived summary, and the exact
dimension deltas. Raw model prose cannot mutate these fields.

The conservative update table lives in `RelationshipUpdater`. Offers of help
raise the recipient's helpfulness and trust; cooperation raises cooperation and
trust for both sides; compliments modestly raise recipient affinity; arguments,
insults, and walking away reduce positive dimensions and raise hostility;
apologies can reduce hostility. A refused help request is supported as an
explicit structured outcome. Values accumulate and clamp at the bounds, so
positive acts can gradually repair rather than erase conflict history.

## Decision conditioning and diagnostics

Direct experience contributes a small interpretable utility to conversation
target weights and goal strategy scores. High trust/helpfulness favors asking
for help, cooperation history favors joint action, and hostility suppresses
reliance while permitting cautious repair. Generated language remains subject
to the existing parser, deterministic inference, and final-action policy.

Goal-created intents preserve the relationship snapshot, retrieved episodes,
and selection reason. A tactic can switch counterparts when direct experience
makes a known helper preferable; goal evidence attributes this to a
`relationship` trigger and preserves goal progress.

Conversation JSONL diagnostics include `relationship_snapshot`,
`retrieved_social_memories`, `relationship_weight_adjustments`,
`relationship_decision_reasons`, `relationship_influenced`, and the directed
`relationship_updates` produced after the interaction.

## Evaluation

Run the deterministic controlled benchmark:

```bash
python scripts/evaluate_relationships.py \
  --output-dir outputs/prompt5_relationship_evaluation/deterministic
```

Run the same paired prompts with the established local model:

```bash
python scripts/evaluate_relationships.py --real-llm \
  --model Qwen/Qwen2.5-3B-Instruct \
  --output-dir outputs/prompt5_relationship_evaluation/qwen-smoke
```

The benchmark holds the immediate goal and action set constant while varying
direct interpersonal history. Real-model conditions within each pair reset to
the same generation seed. It reports preferred-action differences,
trusted-versus-hostile help weights, cooperation preference, target consistency,
relationship update and retrieval correctness, diagnostics coverage, explicit
strategy adaptation, and finalized real-model action differences. Artifacts
include metrics, a readable summary, paired outcomes, transcripts, relationship
state diagnostics, adaptation diagnostics, and failure cases.

## Known limitations

The system uses recent fixed-size episodes rather than semantic retrieval.
Conversation sessions are bounded and alternating, while response outcomes remain
deliberately conservative deterministic interpretations. The legacy pair score
remains symmetric, and private profiles do not propagate through factions,
romance, or city-wide politics. Reputation hearsay is a separate system with
explicit provenance.
