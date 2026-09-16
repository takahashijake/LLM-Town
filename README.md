# LLM-Town

LLM-Town is a persistent, text-based social simulation in which four residents
plan activities, pursue goals, remember events, and hold bounded multi-turn
conversations. It uses a hybrid architecture: deterministic code owns simulation
state and applies validated effects, while a local language model realizes
grounded dialogue. The model never receives arbitrary authority to mutate state.

## Key capabilities

- Bounded, alternating conversation sessions (four utterances by default)
- Per-speaker context boundaries for memories, journals, goals, intents, and beliefs
- Deterministic semantic-action inference and conservative response outcomes
- Separate semantic action records and effect eligibility/rate limiting
- One bounded anti-echo regeneration attempt on the real-model path
- Persistent memories, daily journals, goals, intents, and adaptive goal strategies
- Directional relationship state plus a compatible shared relationship score
- Direct reputation observations and provenance-preserving hearsay
- Needs, occupations, activity planning, daily events, and town arcs
- Save/resume semantics, isolated deterministic benchmarks, and real-LLM review artifacts
- A deterministic automated test suite that does not load or download a model

The repository implements these systems today. Economy, crime, justice, romance,
factions, networking, a GUI, and semantic vector memory are future possibilities,
not current features.

## Architecture overview

```text
agent state + town state + deterministic policy
                    |
                    v
        bounded, speaker-private context
                    |
                    v
       local LLM -> JSON dialogue proposal
                    |
                    v
 parsing -> semantic validation -> action + response outcome
                    |
                    v
 effect eligibility/deduplication -> deterministic state updates
                    |
                    v
 logs + session memory + journals + save state + evaluation
```

Important directories:

```text
src/actions/       action vocabulary and deterministic inference
src/agents/        agents, goals, intents, memories, relationships
src/behavior/      activity, goal, intent, and social policy
src/llm/           prompt construction, local-model client, parser
src/simulation/    orchestration, sessions, effects, persistence, town arcs
src/systems/       reputation (economy/crime/justice are placeholders only)
src/analysis/      benchmarks, metrics, and real-LLM review artifacts
tests/             deterministic unit and integration tests
```

## How a conversation works

At a shared location, deterministic policy selects a pair and prepares context for
the current speaker only. The first turn can choose a grounded focus. Follow-up
turns are prompted to answer or acknowledge the immediately preceding utterance
before changing topic. Each turn is parsed and checked against conservative action
language rules.

The recorded `final_action` describes what the line means. Effect eligibility is a
separate decision: an `offer_help` can remain an offer even when its relationship,
need, reputation, goal, intent, or town-arc effects are suppressed by a rate cap or
same-session deduplication. This preserves listener response and audit semantics
without allowing repeated actions to amplify state changes.

Offers, requests for help, and cooperation proposals receive deterministic,
conservative outcomes such as `accepted`, `declined`, `answered`, or `unresolved`.
Sessions stop at the configured bound or on closure, storm-off, generation failure,
repetition, or a policy termination. Each participant receives one session memory;
turn and session diagnostics remain reconstructable from JSONL logs.

## Simulation systems

Agents have needs, occupations, personalities, persistent goals, short-lived
intents, memories, daily journals, recent topics, and directional relationship
profiles. Activity and social policies use those structures to select behavior.
Public daily events and persistent town arcs provide shared context.

Reputation is distinct from pair relationships. Direct observations can update a
listener's belief about an actor; supported claims may propagate as hearsay with
provenance. Private beliefs and memories are rebuilt per speaker and are not copied
into the other participant's prompt context.

State can be saved and resumed. Structured goal evidence supports bounded strategy
selection/adaptation, while deterministic effect guards prevent repeated dialogue
actions from double-advancing goals or relationship state.

## Evaluation and reproducibility

Run an isolated deterministic benchmark:

```bash
python scripts/benchmark_simulation.py \
  --fake-llm --days 10 --seeds 1 2 3 \
  --max-conversation-turns 4
```

Each seed receives isolated logs and save state under `outputs/benchmarks/`. The
benchmark records configuration, input hashes, revision metadata, per-run metrics,
and aggregate results without touching ordinary `logs/` or `data/save_state.json`.

Run a controlled real-model evaluation:

```bash
python scripts/evaluate_real_llm.py \
  --days 10 --seed 42 --max-conversation-turns 4
```

The evaluator writes metadata, metrics, a complete session transcript, and review
samples. Diagnostics include semantic versus effect-applied action distributions,
suppression reasons, parser/inference/final disagreements, response outcomes,
adjacent echoes, regeneration, and termination. Potential turn discontinuities
and lexical context matches are review candidates—not objective coherence or
causal-influence scores.

## Quick start

Python 3.11+ is recommended.

For the full local-transformer workflow:

```bash
./setup.sh
source .venv/bin/activate
```

`requirements.txt` contains the local-model runtime stack. Test-only contributors
can avoid installing PyTorch and Transformers:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Run the deterministic fake model (no model download or GPU required):

```bash
python main.py --fake-llm --days 2 --hours 8 12 18 22 --seed 42
```

Run the default local Qwen model after it is installed/cached:

```bash
python main.py \
  --days 2 --hours 8 12 18 22 --seed 42 \
  --model-name Qwen/Qwen2.5-3B-Instruct
```

Use `--load-state --no-clear` to resume rather than clear the ordinary run state.

## Testing

```bash
./test.sh
# or
python -m pytest
```

Tests cover action inference/validation, bounded conversation sessions, echo retry,
effect suppression and deduplication, context privacy, response outcomes, memories,
journals, needs, activities, goals/intents, directional relationships, reputation,
town arcs, persistence/resume, reporting, benchmarks, and evaluation artifacts.
CI installs only `requirements-dev.txt`, uses the fake/model-free paths, and never
downloads Qwen or requires CUDA.

## Current limitations

- Response outcome inference is deliberately conservative and lexical.
- Session effects are generally applied after dialogue generation, so relationship
  state does not change midway through the same conversation.
- The four-turn default bounds cost and failure propagation but limits depth.
- A local 3B model's instruction following and naturalness constrain dialogue quality.
- Same-action deduplication and rate suppression trade some behavioral fidelity for
  stable relationship, reputation, need, goal, intent, and town-arc progression.
- Reputation propagation is implemented, but downstream decision influence still
  benefits from controlled evaluation; lexical overlap alone does not establish it.

## Future directions

The v1 focus is evaluation and refinement of the implemented social simulation.
Possible later work includes stronger controlled outcome validation, longer-context
experiments, and measured reputation-policy studies. Larger subsystems such as an
economy, crime/justice, romance, factions, networking, or a GUI are intentionally
outside the current implementation and v1 freeze.
