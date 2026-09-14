"""Controlled Prompt 5 benchmark for relationship-conditioned behavior."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from src.agents.goal import Goal
from src.agents.intent import AgentIntent
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def _engine(project_root: Path, run_dir: Path) -> SimulationEngine:
    return SimulationEngine(
        agents_path=str(project_root / "data" / "agents.json"),
        locations_path=str(project_root / "data" / "locations.json"),
        llm_client=FakeLLMClient(),
        state_path=run_dir / "state.json",
        logs_dir=run_dir / "logs",
    )


def _intent(speaker: str, listener: str, kind: str, strategy: str) -> AgentIntent:
    return AgentIntent(
        id=f"paired-{speaker}-{listener}-{kind}",
        agent_name=speaker,
        intent_type=kind,
        description=f"{speaker} has the same controlled {kind} goal.",
        created_day=4,
        expires_day=6,
        priority=5,
        target_agent=listener,
        strategy=strategy,
    )


def _preferred_action(weights: dict[str, int]) -> str:
    return max(sorted(weights), key=lambda action: weights[action])


def _apply_history(engine, speaker, listener, actions: list[str]) -> None:
    for day, action in enumerate(actions, 1):
        actor, recipient = (
            (listener, speaker)
            if action in {"offer_help", "compliment"}
            else (speaker, listener)
        )
        engine.relationship_updater.apply_structured_relationship_update(
            day=day,
            hour=8,
            speaker=actor,
            listener=recipient,
            action=action,
            outcome="completed",
        )


def _decision(
    project_root: Path,
    scratch: Path,
    name: str,
    history: list[str],
    *,
    intent_type: str,
    strategy: str,
) -> tuple[dict[str, Any], SimulationEngine, Any, Any, dict]:
    engine = _engine(project_root, scratch / name)
    speaker, listener = engine.agents[:2]
    activity_by_intent = {
        "investigate": (
            "Review public records for useful information",
            "The speaker needs a concrete fact to continue the review.",
        ),
        "build_friendship": (
            "Organize supplies for a community project",
            "The supplies need sorting at the town square.",
        ),
        "repair_relationship": (
            "Take a break at the town square",
            "The speaker has an opportunity for a calm conversation.",
        ),
    }
    speaker.current_activity, speaker.current_activity_reason = activity_by_intent[
        intent_type
    ]
    _apply_history(engine, speaker, listener, history)
    intent = _intent(speaker.name, listener.name, intent_type, strategy)
    engine.agent_intents[speaker.name] = intent
    setup = engine.prepare_conversation_context(
        location_id=speaker.location_id,
        speaker=speaker,
        listener=listener,
        current_day=4,
    )
    preferred = _preferred_action(setup["arc_adjusted_weights"])
    setup["suggested_action"] = preferred
    setup["context"]["suggested_action"] = preferred
    result = {
        "name": name,
        "history": history,
        "counterpart": listener.name,
        "preferred_action": preferred,
        "action_weights": setup["arc_adjusted_weights"],
        "relationship_snapshot": setup["relationship_snapshot"],
        "retrieved_social_memories": setup["social_memories"],
        "relationship_weight_adjustments": setup[
            "relationship_weight_adjustments"
        ],
        "relationship_decision_reasons": setup[
            "relationship_decision_reasons"
        ],
    }
    return result, engine, speaker, listener, setup


def _generate_real_result(
    llm,
    engine,
    speaker,
    listener,
    setup: dict,
    generation_seed: int,
) -> dict:
    import torch

    torch.manual_seed(generation_seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(generation_seed)
    context = setup["context"]
    raw = llm.generate_conversation(context)
    processed = engine.process_conversation_output(
        raw_output=raw,
        allowed_actions=setup["allowed_actions"],
        speaker=speaker,
        listener=listener,
        old_relationship_label=setup["old_relationship_label"],
        location_id=speaker.location_id,
        suggested_action=setup["suggested_action"],
        current_day=4,
        conversation_context=context,
        enforce_information_boundaries=True,
    )
    conversation = processed["conversation"]
    parsed_action = processed["parsed_action"]
    inferred_action, inference_reason = engine.actions.infer_action_with_reason(
        conversation, processed["parsed_output"].get("tags", [])
    )
    action, final_reason = engine.choose_final_action_with_reason(
        conversation=conversation,
        parsed_action=parsed_action,
        conversation_tags=processed["parsed_output"].get("tags", []),
        allowed_actions=setup["allowed_actions"],
        inferred_action=inferred_action,
    )
    return {
        "raw_response": raw,
        "dialogue": conversation,
        "parsed_action": parsed_action,
        "action_source": processed["parsed_output"].get("action_source", ""),
        "inferred_action": inferred_action,
        "inference_reason": inference_reason,
        "final_action": action,
        "final_action_reason": final_reason,
        "dialogue_source": processed["dialogue_source"],
        "suggested_action": setup["suggested_action"],
        "generation_seed": generation_seed,
    }


def run_relationship_evaluation(
    output_dir: str | Path,
    *,
    project_root: str | Path = ".",
    llm=None,
    model_identifier: str = "deterministic-policy",
    seed: int = 42,
) -> dict[str, Any]:
    """Run controlled pairs and write a self-contained Prompt 5 artifact set."""
    project_root = Path(project_root).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    random.seed(seed)
    scratch = output_dir / "scenario_state"

    scenario_specs = [
        (
            "help_seek_trusted", ["offer_help"] * 3,
            "investigate", "observe_relevant_activity",
        ),
        (
            "help_seek_neutral", [],
            "investigate", "observe_relevant_activity",
        ),
        (
            "help_seek_hostile", ["argue"] * 3,
            "investigate", "observe_relevant_activity",
        ),
        (
            "cooperate_proven", ["cooperate"] * 3,
            "build_friendship", "direct_cooperation",
        ),
        (
            "cooperate_neutral", [],
            "build_friendship", "direct_cooperation",
        ),
        (
            "conflict_unresolved", ["insult", "argue", "argue"],
            "repair_relationship", "apologize_directly",
        ),
        (
            "conflict_repaired",
            ["insult", "argue", "argue", "apologize", "offer_help", "cooperate"],
            "repair_relationship", "apologize_directly",
        ),
    ]
    scenarios = []
    runtime = {}
    for name, history, intent_type, strategy in scenario_specs:
        result, engine, speaker, listener, setup = _decision(
            project_root, scratch, name, history,
            intent_type=intent_type, strategy=strategy,
        )
        scenarios.append(result)
        runtime[name] = (engine, speaker, listener, setup)

    by_name = {scenario["name"]: scenario for scenario in scenarios}
    pairs = [
        {
            "name": "trusted_helper_vs_neutral",
            "left": "help_seek_trusted", "right": "help_seek_neutral",
            "expected": "trusted history increases help seeking",
        },
        {
            "name": "trusted_helper_vs_hostile",
            "left": "help_seek_trusted", "right": "help_seek_hostile",
            "expected": "hostile history suppresses help seeking",
        },
        {
            "name": "proven_cooperator_vs_neutral",
            "left": "cooperate_proven", "right": "cooperate_neutral",
            "expected": "successful cooperation increases cooperation preference",
        },
        {
            "name": "repair_progress",
            "left": "conflict_unresolved", "right": "conflict_repaired",
            "expected": "positive follow-up improves the private relationship state",
        },
    ]
    for pair in pairs:
        left, right = by_name[pair["left"]], by_name[pair["right"]]
        pair["preferred_actions_differ"] = (
            left["preferred_action"] != right["preferred_action"]
        )
        pair["help_weight_delta"] = (
            left["action_weights"].get("ask_for_help", 0)
            - right["action_weights"].get("ask_for_help", 0)
        )
        pair["cooperation_weight_delta"] = (
            left["action_weights"].get("cooperate", 0)
            - right["action_weights"].get("cooperate", 0)
        )
        pair["relationship_value_delta"] = round(
            _decision_value(left["relationship_snapshot"])
            - _decision_value(right["relationship_snapshot"]), 3
        )

    # Independent target-choice control: only Maya's direct histories differ.
    target_engine = _engine(project_root, scratch / "target_choice")
    seeker, reliable, hostile = target_engine.agents[:3]
    _apply_history(target_engine, seeker, reliable, ["offer_help"] * 3)
    _apply_history(target_engine, seeker, hostile, ["argue"] * 3)
    target_goal = Goal(
        id="paired-target-goal", agent_name=seeker.name,
        description="Obtain useful information", category="increase_knowledge",
        priority=5, created_day=4, review_day=7, progress_target=3,
        target_locations=["library"],
    )
    selected = target_engine.goal_planner.select_strategy(
        target_goal, seeker, target_engine
    )
    target_diagnostic = {
        "selected_strategy": selected.name,
        "selected_target": selected.target_agent,
        "expected_target": reliable.name,
        "relationship_influenced": selected.relationship_influenced,
        "reason": selected.relationship_reason,
        "relationship_snapshot": selected.relationship_snapshot,
        "retrieved_social_memories": list(selected.relevant_social_memories),
    }

    adaptation_engine = _engine(project_root, scratch / "strategy_adaptation")
    seeker, refused_target, known_helper = adaptation_engine.agents[:3]
    _apply_history(adaptation_engine, seeker, refused_target, ["offer_help"] * 2)
    adaptation_goal = Goal(
        id="paired-adaptation-goal", agent_name=seeker.name,
        description="Obtain useful information", category="increase_knowledge",
        priority=5, created_day=1, review_day=7, progress=1, progress_target=3,
        target_locations=["library"],
    )
    original = adaptation_engine.goal_planner.select_strategy(
        adaptation_goal, seeker, adaptation_engine
    )
    original_intent = adaptation_engine.intent_planner.create_intent_from_goal(
        adaptation_goal, original, 1
    )
    adaptation_goal.current_strategy = original.name
    adaptation_goal.current_strategy_target = original.target_agent
    adaptation_goal.strategy_started_day = 1
    for day in (2, 3, 4):
        adaptation_engine.relationship_updater.apply_structured_relationship_update(
            day=day, hour=12, speaker=seeker, listener=refused_target,
            action="ask_for_help", outcome="refused",
        )
    _apply_history(adaptation_engine, seeker, known_helper, ["offer_help"] * 2)
    replacement, adaptation_trigger = adaptation_engine.goal_planner.should_adapt(
        adaptation_goal, original_intent, seeker, adaptation_engine, current_day=4
    )
    adaptation_diagnostic = {
        "trigger": adaptation_trigger,
        "old_strategy": original.name,
        "new_strategy": replacement.name if replacement else None,
        "old_target_agent": original.target_agent,
        "new_target_agent": replacement.target_agent if replacement else None,
        "expected_target": known_helper.name,
        "preserved_progress": adaptation_goal.progress,
        "relationship_reason": replacement.relationship_reason if replacement else "",
        "relationship_snapshot": (
            replacement.relationship_snapshot if replacement else {}
        ),
        "retrieved_social_memories": (
            list(replacement.relevant_social_memories) if replacement else []
        ),
        "prior_counterpart_memories": [
            memory.summary for memory in seeker.get_social_memories(
                original.target_agent, limit=3
            )
        ],
    }

    real_results = []
    if llm is not None:
        paired_generation_seeds = {
            "help_seek_trusted": seed + 100,
            "help_seek_neutral": seed + 100,
            "help_seek_hostile": seed + 100,
            "cooperate_proven": seed + 200,
            "cooperate_neutral": seed + 200,
            "conflict_unresolved": seed + 300,
            "conflict_repaired": seed + 300,
        }
        for scenario in scenarios:
            engine, speaker, listener, setup = runtime[scenario["name"]]
            generated = _generate_real_result(
                llm,
                engine,
                speaker,
                listener,
                setup,
                paired_generation_seeds[scenario["name"]],
            )
            scenario["real_llm"] = generated
            real_results.append({"scenario": scenario["name"], **generated})
        for pair in pairs:
            left = by_name[pair["left"]].get("real_llm", {})
            right = by_name[pair["right"]].get("real_llm", {})
            pair["real_actions_differ"] = (
                bool(left) and bool(right)
                and left.get("final_action") != right.get("final_action")
            )

    decision_pairs = pairs
    influenced = sum(pair["preferred_actions_differ"] for pair in decision_pairs)
    valid_diagnostics = sum(
        bool(scenario["relationship_snapshot"].get("interaction_count"))
        and bool(scenario["retrieved_social_memories"])
        and bool(scenario["relationship_decision_reasons"])
        for scenario in scenarios if scenario["history"]
    )
    history_scenarios = sum(bool(scenario["history"]) for scenario in scenarios)
    real_pair_differences = sum(pair.get("real_actions_differ", False) for pair in decision_pairs)
    real_count = len(real_results)
    direct_real_results = [
        row for row in real_results if row["dialogue_source"] == "llm"
    ]
    update_checks = [
        by_name["help_seek_trusted"]["relationship_snapshot"]["trust"] > 0,
        by_name["help_seek_trusted"]["relationship_snapshot"]["helpfulness"] > 0,
        by_name["help_seek_hostile"]["relationship_snapshot"]["hostility"] > 0,
        by_name["help_seek_hostile"]["relationship_snapshot"]["affinity"] < 0,
        by_name["cooperate_proven"]["relationship_snapshot"]["cooperation"] > 0,
        _decision_value(by_name["conflict_repaired"]["relationship_snapshot"])
        > _decision_value(by_name["conflict_unresolved"]["relationship_snapshot"]),
    ]
    metrics = {
        "relationship_conditioned_decision_rate": round(
            influenced / len(decision_pairs), 3
        ),
        "preferred_target_consistency": float(
            target_diagnostic["selected_target"] == target_diagnostic["expected_target"]
        ),
        "trusted_help_seeking_preferred": float(
            by_name["help_seek_trusted"]["preferred_action"] == "ask_for_help"
        ),
        "hostile_help_seeking_suppressed": float(
            by_name["help_seek_hostile"]["action_weights"].get("ask_for_help", 0)
            < by_name["help_seek_trusted"]["action_weights"].get("ask_for_help", 0)
        ),
        "proven_cooperation_preferred": float(
            by_name["cooperate_proven"]["preferred_action"] == "cooperate"
        ),
        "repair_deescalation_preferred": float(
            by_name["conflict_unresolved"]["preferred_action"] == "apologize"
            and by_name["conflict_repaired"]["preferred_action"] == "chat"
        ),
        "relationship_update_correctness": round(
            sum(update_checks) / len(update_checks), 3
        ),
        "repair_relationship_value_gain": round(
            _decision_value(by_name["conflict_repaired"]["relationship_snapshot"])
            - _decision_value(by_name["conflict_unresolved"]["relationship_snapshot"]),
            3,
        ),
        "memory_retrieval_correctness": round(
            sum(bool(s["retrieved_social_memories"]) for s in scenarios if s["history"])
            / history_scenarios, 3
        ),
        "valid_relationship_diagnostics_rate": round(
            valid_diagnostics / history_scenarios, 3
        ),
        "relationship_attributed_strategy_adaptation": float(
            adaptation_trigger == "relationship"
            and replacement is not None
            and replacement.target_agent == known_helper.name
            and adaptation_goal.progress == 1
        ),
        "context_present_without_preferred_action_change_count": sum(
            not pair["preferred_actions_differ"] for pair in decision_pairs
        ),
        "real_llm_pair_action_difference_rate": (
            round(real_pair_differences / len(decision_pairs), 3)
            if llm is not None else None
        ),
        "real_llm_json_parsing_rate": (
            round(sum(row["action_source"] == "llm" for row in real_results) / real_count, 3)
            if real_count else None
        ),
        "real_llm_suggested_action_followthrough_rate": (
            round(sum(
                row["final_action"] == row["suggested_action"] for row in real_results
            ) / real_count, 3) if real_count else None
        ),
        "real_llm_parser_inference_agreement_rate": (
            round(sum(
                row["parsed_action"] == row["inferred_action"] for row in real_results
            ) / real_count, 3) if real_count else None
        ),
        "real_llm_direct_dialogue_parser_inference_agreement_rate": (
            round(sum(
                row["parsed_action"] == row["inferred_action"]
                for row in direct_real_results
            ) / len(direct_real_results), 3) if direct_real_results else None
        ),
        "real_context_pair_without_action_change_count": (
            sum(not pair.get("real_actions_differ", False) for pair in decision_pairs)
            if llm is not None else None
        ),
    }
    failures = [
        {"type": "policy_pair_without_change", **pair} for pair in pairs
        if pair in decision_pairs and not pair["preferred_actions_differ"]
    ]
    failures.extend(
        {"type": "parser_inference_disagreement", **row}
        for row in real_results
        if row["parsed_action"] != row["inferred_action"]
    )
    if llm is not None:
        failures.extend(
            {"type": "real_pair_without_action_difference", **pair}
            for pair in decision_pairs
            if not pair.get("real_actions_differ", False)
        )
    document = {
        "schema_version": 1,
        "kind": "llm-town-prompt5-relationship-evaluation",
        "model_identifier": model_identifier,
        "seed": seed,
        "metrics": metrics,
        "paired_scenarios": pairs,
        "target_choice": target_diagnostic,
        "strategy_adaptation": adaptation_diagnostic,
        "scenarios": scenarios,
    }
    _write_artifacts(output_dir, document, failures, real_results)
    return document


def _decision_value(snapshot: dict) -> float:
    return round(
        snapshot.get("trust", 0) * 0.3
        + snapshot.get("affinity", 0) * 0.15
        + snapshot.get("cooperation", 0) * 0.2
        + snapshot.get("helpfulness", 0) * 0.25
        - snapshot.get("hostility", 0) * 0.35,
        3,
    )


def _write_artifacts(
    output_dir: Path,
    document: dict,
    failures: list[dict],
    transcripts: list[dict],
) -> None:
    def write_json(name: str, value: Any) -> None:
        (output_dir / name).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    write_json("evaluation.json", document)
    write_json("metrics.json", document["metrics"])
    write_json("paired_scenario_outcomes.json", document["paired_scenarios"])
    write_json("relationship_state_diagnostics.json", document["scenarios"])
    write_json("strategy_adaptation_diagnostics.json", {
        "target_choice": document["target_choice"],
        "adaptation": document["strategy_adaptation"],
    })
    write_json("failure_cases.json", failures)
    write_json("transcripts.json", transcripts)
    metrics = document["metrics"]
    summary = (
        "# Prompt 5 relationship evaluation\n\n"
        f"Model: `{document['model_identifier']}`\n\n"
        f"- Relationship-conditioned decision rate: "
        f"{metrics['relationship_conditioned_decision_rate']:.1%}\n"
        f"- Preferred-target consistency: "
        f"{metrics['preferred_target_consistency']:.1%}\n"
        f"- Memory retrieval correctness: "
        f"{metrics['memory_retrieval_correctness']:.1%}\n"
        f"- Valid relationship diagnostics: "
        f"{metrics['valid_relationship_diagnostics_rate']:.1%}\n"
        f"- Real-LLM paired action difference rate: "
        f"{metrics['real_llm_pair_action_difference_rate']}\n"
        f"- Real-LLM JSON parsing rate: "
        f"{metrics['real_llm_json_parsing_rate']}\n"
        f"- Real-LLM suggested-action followthrough rate: "
        f"{metrics['real_llm_suggested_action_followthrough_rate']}\n"
        f"- Real-LLM parser/inference agreement rate: "
        f"{metrics['real_llm_parser_inference_agreement_rate']}\n"
        f"- Real-LLM direct-dialogue parser/inference agreement rate: "
        f"{metrics['real_llm_direct_dialogue_parser_inference_agreement_rate']}\n"
    )
    (output_dir / "summary.md").write_text(summary, encoding="utf-8")
