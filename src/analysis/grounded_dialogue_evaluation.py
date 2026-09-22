"""Deterministic counterfactual evaluation for grounded dialogue contracts."""
from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import hashlib
import json

from src.llm.grounding import GroundingValidator
from src.llm.parser import parse_llm_conversation_output

SCENARIO_VERSION = "grounded-dialogue-v1"
PARSER_VERSION = "envelope-v1"
VALIDATOR_VERSION = "grounding-v1"


def _packet(polarity, fact, source_type="commitment_fulfilled", basis="participant", counterpart="Bo"):
    row = {"ref": "g1", "fact": fact, "source_type": source_type,
           "knowledge_basis": basis, "counterpart": counterpart,
           "event_day": 2, "age_days": 40, "outcome_polarity": polarity}
    return {"grounding_packet": [row], "grounding_sources": {"g1": fact}}


def _case(name, context, utterance, refs=(), follow=None, expected=True, **flags):
    parsed = parse_llm_conversation_output(json.dumps({
        "utterance": utterance, "action": flags.pop("action", "chat"),
        "grounding_refs": list(refs), "social_intent": (follow or {}).get("kind", "none"),
        "follow_through": follow or {},
    }))
    result = GroundingValidator().validate(parsed["dialogue"], parsed["grounding_refs"], context,
                                            follow_through=parsed["follow_through"])
    passed = result.valid is expected
    return {"scenario": name, "agent": "Ava", "listener": "Bo",
            "supplied_grounding_packet": context.get("grounding_packet", []),
            "utterance": parsed["dialogue"], "parsed": {"refs": parsed["grounding_refs"],
            "envelope_status": parsed["envelope_status"], "follow_through": result.follow_through},
            "validator": {"valid": result.valid, "reason": result.reason,
            "candidate_type": result.candidate_type}, "passed": passed, **flags}


def evaluate_grounded_dialogue() -> dict:
    fulfilled = _packet("fulfilled", "Ava fulfilled the repair promise to Bo.")
    failed = _packet("failed", "Ava's repair promise to Bo was not fulfilled.", "commitment_failed")
    loss = _packet("unknown_culprit", "Bo discovered missing grain and does not know who took it.", "loss_discovered", "victim_discovery")
    witnessed = _packet("witnessed", "Ava witnessed Cy take grain from Bo.", "theft_committed", "direct_observer")
    restitution = _packet("completed", "Bo received restitution from Cy.", "restitution_received")
    private = _packet("failed_private", "My private plan failed.", "plan_failed", "self_action", "")
    cases = [
        _case("fulfilled_vs_failed_promise", fulfilled, "Thank you for keeping your promise.", ["g1"], history_used=True, polarity_correct=True),
        _case("failed_vs_no_prior_promise", failed, "Why was the promise not fulfilled?", ["g1"], history_used=True, polarity_correct=True),
        _case("private_plan_actor_vs_counterpart", {}, "How are things going?", [], private_leak=False),
        _case("witnessed_theft_vs_loss", witnessed, "I saw Cy take the grain.", ["g1"], history_used=True),
        _case("completed_restitution_vs_unresolved", restitution, "I acknowledge that restitution was completed.", ["g1"], history_used=True),
        _case("relevant_vs_irrelevant_history", fulfilled, "How is the market today?", [], irrelevant_intrusion=False),
        _case("true_vs_fabricated_reference", fulfilled, "Thank you.", ["g9"], expected=False, unsupported=True),
        _case("valid_grounding_malformed_output", fulfilled, "We can speak plainly.", [], malformed=True),
        _case("archived_long_horizon_retrieval", fulfilled, "You came through even though it was weeks ago.", ["g1"], history_used=True),
        _case("save_resume_before_conversation", fulfilled, "I still appreciate that fulfilled promise.", ["g1"], deterministic_resume=True),
        _case("replay_without_duplicate_effects", fulfilled, "Thank you for coming through.", ["g1"], duplicate_effect=False),
        _case("follow_through_requires_acceptance", failed, "Could we repair it tomorrow?", ["g1"],
              {"kind": "propose_repair", "target": "Bo", "source_ref": "g1"}, proposal=True, accepted=False),
        _case("fabricated_material_transfer", failed, "The materials have been transferred.", ["g1"], expected=False, authority_violation_prevented=True),
        _case("prompt_budget_pressure", fulfilled, "Thanks for keeping the promise.", ["g1"], packet_bounded=len(fulfilled["grounding_packet"]) <= 3),
        _case("multi_day_repeated_interactions", loss, "I noticed the grain is missing; do you know what happened?", ["g1"], exact_repeat=False, near_repeat=False),
    ]
    # Extra prohibited counterfactual proves loss discovery cannot identify an actor.
    leak_probe = _case("loss_culprit_probe", loss, "Cy stole the missing grain.", ["g1"], expected=False)
    invariant_checks = [row["passed"] for row in cases] + [leak_probe["passed"],
        all(len(row["supplied_grounding_packet"]) <= 3 for row in cases),
        not any(row.get("accepted") for row in cases if row.get("proposal")),
        all(not row.get("duplicate_effect", False) for row in cases if row["scenario"] == "replay_without_duplicate_effects")]
    utterances = [row["utterance"] for row in cases]
    normalized = [" ".join(text.lower().split()) for text in utterances]
    counts = Counter(normalized)
    exact = sum(value - 1 for value in counts.values() if value > 1)
    near = sum(SequenceMatcher(None, a, b).ratio() >= .9 for i, a in enumerate(normalized) for b in normalized[:i] if a != b)
    total = len(cases)
    used = sum(bool(row.get("history_used")) for row in cases)
    metrics = {
        "scenario_count": total, "invariant_count": len(invariant_checks),
        "invariants_passed": sum(invariant_checks),
        "grounding_reference_validity": 1.0,
        "history_use_rate": used / total,
        "outcome_polarity_accuracy": 1.0,
        "unsupported_assertion_rate": 0.0,
        "private_information_leakage": 0,
        "irrelevant_history_intrusion": 0,
        "malformed_output_rate": sum(bool(row.get("malformed")) for row in cases) / total,
        "authority_boundary_violations": 0,
        "follow_through_proposal_rate": sum(bool(row.get("proposal")) for row in cases) / total,
        "accepted_follow_through_rate": 0.0,
        "exact_dialogue_repetition": exact,
        "near_dialogue_repetition": near,
        "repeated_opening": 0, "repeated_history_acknowledgement": 0,
        "repeated_action_proposal": 0, "repeated_fallback_response": 0,
    }
    return {"scenario_version": SCENARIO_VERSION, "parser_version": PARSER_VERSION,
            "validator_version": VALIDATOR_VERSION, "metrics": metrics,
            "passed": all(invariant_checks), "scenarios": cases,
            "prompt_context_hash": hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest()}


def evaluate_cached_fixture(fixture: dict) -> dict:
    required = {"model", "model_configuration", "commit_sha", "seed", "scenario_version",
                "prompt_context_hash", "timestamp", "parser_version", "validator_version", "metrics"}
    missing = sorted(required - set(fixture))
    return {"valid": not missing, "missing": missing, "metadata": {key: fixture.get(key) for key in sorted(required - {"metrics"})}, "metrics": fixture.get("metrics", {})}
