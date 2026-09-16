# LLM-Town v1 freeze report

## Candidate identity

- Base commit: `70e88b1c3ec87af82411d31491f3467374eb04e2`
- Branch: `main`, verified equal to freshly fetched `origin/main` before changes
- Candidate state: uncommitted working-tree diff on the base commit; there is no
  separate final commit SHA yet
- Final benchmark source SHA-256: `bd037924977d9a7f57d7f1923daf9871ff2faee1b43d5cc99bf723a6ad0b0b0a`

## Scope

V1 is a persistent, text-based social simulation of four residents. Deterministic
code owns state, policy, validation, effect eligibility, mutation, persistence,
and measurement. A local language model proposes dialogue but cannot directly
mutate simulation state.

Economy, crime/justice, factions, romance, networking, a GUI, large populations,
and vector memory are outside v1. Empty files that implied those systems existed
were removed rather than implemented.

## Architecture

```text
deterministic state and policy
        -> speaker-private bounded context
        -> LLM dialogue proposal
        -> parse and semantic validation
        -> semantic action and response outcome
        -> effect eligibility and deduplication
        -> deterministic state mutation
        -> logs, memories, journals, persistence, and evaluation
```

Semantic action identity remains separate from effect eligibility. A repeated or
rate-capped action keeps its meaning for response and audit purposes while its
state effects are suppressed.

## Implemented systems

- Bounded alternating multi-turn sessions and conservative response outcomes
- Private per-speaker memories, journals, goals, intents, and reputation beliefs
- Session-level memories, bounded active memory, and archival summaries
- Persistent goals/intents with strategy selection and adaptation evidence
- Directional relationship profiles plus a symmetric compatibility score
- Direct reputation evidence and provenance-preserving hearsay
- Daily events and persistent town arcs
- Deterministic mutation, action caps, same-session deduplication, save/resume,
  isolated benchmarks, and real-model review artifacts

No further architectural extraction was made. Large orchestration and analysis
modules have related responsibilities and covered interfaces; a line-count-only
refactor would add freeze risk without improving the behavioral contract.

## Baseline and tests

Starting baseline on the base commit:

```text
python -m pytest
359 passed in 11.46s

python -m compileall -q src scripts main.py
success
```

Final candidate:

```text
python -m pytest
361 passed in 11.77s

python -m compileall -q src scripts main.py
success
```

The suite includes deterministic coverage for context privacy, bounded sessions,
memory limits, persistence/resume, semantic-action preservation, effect suppression,
same-session deduplication, relationships, reputation, goals/intents, town arcs,
benchmarks, and evaluation artifacts.

## Deterministic benchmark

Command:

```bash
python scripts/benchmark_simulation.py \
  --fake-llm \
  --days 10 \
  --seeds 1 2 3 \
  --max-conversation-turns 4
```

Final result:

| Seed | Utterances | Repetition | Intent/action | Active memory avg/max | Goals achieved | Intents succeeded | Relationship events | Arcs resolved |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 49 | 4.1% | 75.0% | 28.25 / 30 | 8 | 17 | 15 | 2 |
| 2 | 47 | 2.1% | 76.9% | 28.25 / 32 | 9 | 19 | 18 | 3 |
| 3 | 46 | 2.2% | 83.3% | 25.00 / 27 | 11 | 23 | 15 | 1 |

All seeds produced 40 journals with 100% day coverage. Goal opportunity progress
rates were 69.6%, 74.5%, and 79.6%. Conversation, daily-event, and town-arc memory
records were present. Duplicate and rate-cap suppression were exercised. Two
back-to-back benchmark suites produced identical configuration, aggregate metrics,
and every per-seed metrics object.

The benchmark's `6/10` soft-check totals are diagnostic warnings: chat and
compliment distributions fall outside historical target bands, daily-event use is
18.4-19.6% against a 20% lower target, and no `town_arc_participation` subtype was
created. These are not hidden by threshold changes. Town-arc memories were present
(19-41 per seed) and 1-3 arcs resolved per seed, but action-caused arc changes were
zero in this short fake-model run.

The controlled deterministic relationship evaluation reported 100% for retrieval,
directed update correctness, relationship-conditioned decisions, target consistency,
strategy adaptation attribution, trusted/hostile help behavior, repair preference,
and diagnostics validity. Its failure-case list was empty.

## Real-LLM acceptance

Final full command:

```bash
python scripts/evaluate_real_llm.py \
  --days 5 \
  --seed 42 \
  --max-conversation-turns 4 \
  --model-name Qwen/Qwen2.5-3B-Instruct \
  --output-dir outputs/freeze_candidate_qwen_final
```

Settings were temperature `0.4`, top-p `0.9`, maximum 150 new tokens, four daily
time slots, and sampled generation on CUDA. Required metadata, metrics, transcript,
review, human-review sample, and strategy-adaptation diagnostics were all produced.

Key empirical results:

- 66 utterances in 20 sessions; average 3.3 turns; maximum turn index 3
- 100% JSON/action parse success; zero malformed outputs or generation exceptions
- 100% measured intent/action compatibility after the request-language fix
- 0% exact repetition, 1.5% near repetition, and zero adjacent exact/near echoes
- 14 sessions reached four turns; 6 ended conservatively after repetition fallback
- 11 guarded fallback lines: 3 narration replacements, 6 repetition replacements,
  1 unsupported-hearsay replacement, and 1 evidence-backed rumor reconstruction
- 34 effects suppressed (33 same-session duplicates, 1 rate cap); zero suppressed
  effects were applied and every suppression had a reason
- 5 goals achieved, 11 intents succeeded, 1 relationship-triggered strategy
  adaptation, 6 reputation beliefs, and 1 provenance-preserving hearsay update
- Town-arc context matched 9 of 25 lexical opportunities; this is an indicator,
  not proof of causal context use

Manual transcript review found no leaked narration, literal placeholder text,
malformed response, generation exception, unsupported rumor mutation, adjacent
echo, effect-after-suppression error, duplicate state mutation, or broken bound.
One-day post-fix smoke coverage also directly verified that a previously
misclassified request was finalized as `ask_for_help`.

## Remaining limitations

- Qwen sometimes invents incidental local specifics such as shortages, stall names,
  a social-media page, or menu details. These lines do not bypass deterministic
  state validation, but dialogue grounding is not perfect.
- Safe fallbacks occurred for 16.7% of final-run utterances. They prevented leaked
  narration, unsupported hearsay, and repeated model lines, but some are generic and
  six sessions ended early after repetition fallback.
- Conservative response resolution left 12 of 14 social actions unresolved.
- The real-model generator samples, so identical seed/settings are not promised to
  be bit-for-bit reproducible across hardware/runtime executions. The fake-model
  benchmark is reproducible.
- Short fake runs showed arc resolution and arc memories but no dialogue-caused arc
  mutation, and the dedicated participation-memory subtype remained absent.
- The candidate is an uncommitted working tree, so a final commit SHA does not exist.

None of these limitations prevents a v1 portfolio freeze. They should remain
documented rather than turned into new subsystems or metric-driven tuning work.

## Repository cleanup inventory

Modified:

- `.gitignore`: ignore generated output families while retaining curated structured
  relationship evidence
- `README.md`: remove placeholder-system claims, describe output policy, and link
  this report
- `docs/prompt5_relationship_memory.md`: remove milestone wording and update the
  obsolete one-line-conversation limitation
- `src/actions/action_system.py`: recognize conservative free-form assistance
  requests exposed by the acceptance transcript
- `src/simulation/conversation_policy.py`: render fallback activities as grammatical
  phrases
- `tests/actions/test_action_inference.py`: cover direct assistance variants
- `tests/simulation/test_conversation_policy.py`: cover grammatical fallback phrases

Added:

- `docs/v1_freeze_report.md`: this verification record

Deleted empty, unreferenced placeholders/tests:

```text
data/laws.json
src/agents/goals.py
src/llm/prompts.py
src/simulation/conversations.py
src/simulation/events.py
src/systems/crime.py
src/systems/economy.py
src/systems/justice.py
src/town/scheduler.py
src/town/town.py
src/utils/ids.py
src/utils/logging.py
tests/simulation/test_engine_orchestration.py
tests/test_agents.py
tests/test_simulation.py
```

Deleted historical unstructured output:

```text
outputs/long_runs/run_20_day_agent_arc_memories.txt
outputs/long_runs/run_20_day_arc_action_boost.txt
outputs/long_runs/run_20_day_arc_change_logging.txt
outputs/long_runs/run_20_day_arc_change_logging_clean.txt
outputs/long_runs/run_20_day_clean_logs_memory_report.txt
outputs/long_runs/run_20_day_dialogue_cleanup.txt
outputs/long_runs/run_20_day_grammar_polish.txt
outputs/long_runs/run_20_day_memory_quality_report.txt
outputs/long_runs/run_20_day_seed_42.txt
outputs/long_runs/run_20_day_seed_42_arc035.txt
outputs/long_runs/run_20_day_seed_42_fixed_arcs.txt
outputs/long_runs/run_20_day_seed_42_relevant_arc_memory.txt
outputs/long_runs/run_50_day_seed_42.txt
outputs/long_runs/run_50_day_seed_42_arc_causal.txt
outputs/long_runs/run_50_day_seed_42_compliment_cap.txt
outputs/long_runs/run_50_day_seed_42_diagnostics.txt
outputs/long_runs/run_50_day_seed_42_grounded_fallbacks.txt
outputs/long_runs/run_50_day_seed_42_quality_fix.txt
outputs/long_runs/run_50_day_story_benchmark.txt
outputs/seed_sweep/analysis_seed_{1,2,3,4,5}.txt
outputs/seed_sweep/run_seed_{1,2,3,4,5}.txt
outputs/town_arc_seed_sweep/run_seed_{1,2,3,4,5}.txt
```

The structured files under `outputs/prompt5_relationship_evaluation/` remain as
curated evidence. Generated freeze and benchmark runs are ignored local artifacts.

## Verdict

`FREEZE READY WITH MINOR POLISH`

There is no blocking functional defect and no major subsystem or architectural
refactor is required for v1.
