import json

from src.analysis.grounded_dialogue_benchmark import (
    acceptance, aggregate, classify_response, context_for_case, load_benchmark,
)
from src.llm.client import TransformersLLMClient


def test_balanced_benchmark_is_versioned_and_machine_readable():
    benchmark = load_benchmark()
    assert benchmark["version"] == "grounded-dialogue-balanced-v2"
    assert len(benchmark["cases"]) == 24
    assert {case["class"] for case in benchmark["cases"]} == {
        "must_use", "may_use", "must_not_use",
    }
    assert all("allowed_refs" in case and "forbidden_claims" in case for case in benchmark["cases"])


def test_required_history_needs_reference_content_and_polarity():
    case = load_benchmark()["cases"][0]
    def response(utterance, refs):
        return json.dumps({"utterance": utterance, "grounding_refs": refs,
                           "social_intent": "acknowledge", "follow_through": {
                               "kind": "none", "target": "", "grounding_ref": ""}})
    good = classify_response(case, response("Yes, I kept that promise.", ["g1"]))
    ignored = classify_response(case, response("It is good to see you.", []))
    reversed_polarity = classify_response(case, response("I failed that promise.", ["g1"]))
    assert good["history_used"] and good["polarity_correct"]
    assert not ignored["history_used"]
    assert not reversed_polarity["history_used"]
    assert not reversed_polarity["polarity_correct"]


def test_metrics_keep_failure_categories_separate():
    malformed = classify_response(load_benchmark()["cases"][0], "not json")
    assert not malformed["schema_parse_success"]
    assert malformed["legacy_fallback_used"]
    assert not malformed["generation_failure"]
    metrics = aggregate([malformed])
    assert metrics["model_ignored_history"] == 0
    assert metrics["generation_failures"] == 0


def test_two_stage_plan_only_selects_visible_allowed_fact():
    case = load_benchmark()["cases"][0]
    plan = context_for_case(case, two_stage=True)["grounded_content_plan"]
    assert plan["grounding_ref"] in case["allowed_refs"]
    assert plan["counterpart"] == case["listener"]
    assert plan["event_type"] == case["fact"]["source_type"]
    irrelevant = next(
        row for row in load_benchmark()["cases"]
        if row["id"] == "must_not_irrelevant_archive"
    )
    assert context_for_case(irrelevant, two_stage=True)["grounded_content_plan"] is None


def test_acceptance_thresholds_are_not_relaxed():
    metrics = {"schema_parse_success": 1.0, "valid_grounding_reference_rate": 1.0,
               "engine_owned_grounding_reference_validity": 1.0,
               "private_leakage": 0, "authority_contradictions": 0,
               "required_history_use": .90, "irrelevant_history_intrusion": .10,
               "polarity_accuracy": .95, "counterpart_accuracy": 1.0,
               "generation_failures": 0, "repair_rate": .15, "fallback_rate": .10}
    assert acceptance(metrics)["passed"]
    metrics["required_history_use"] = .899
    assert not acceptance(metrics)["passed"]


def test_engine_metadata_cannot_make_wrong_surface_meaning_correct():
    case = load_benchmark()["cases"][0]
    raw = json.dumps({
        "utterance": "No, I failed that promise.",
        "grounding_refs": ["invented-id"],
        "social_intent": "acknowledge",
        "follow_through": {"kind": "none", "target": "", "grounding_ref": ""},
    })
    result = classify_response(case, raw, engine_owned_metadata=True)
    assert result["engine_owned_grounding_reference_valid"]
    assert result["metadata_disagreement"]
    assert not result["history_used"]
    assert not result["polarity_correct"]


def test_production_record_exposes_plan_repair_and_final_outcomes():
    case = load_benchmark()["cases"][0]
    result = classify_response(
        case, '{"utterance":"Yes, I kept that promise."}',
        engine_owned_metadata=True, repair_used=True, repair_succeeded=True,
        initial_validation_result="history_omitted", latency_seconds=.25,
    )
    assert result["plan_created"] and result["engine_grounding_attached"]
    assert result["history_use_category"] == "required"
    assert result["surface_history_realized"]
    assert result["initial_validation_result"] == "history_omitted"
    assert result["repair_attempted"] and result["repair_succeeded"]
    assert result["final_safety_result"] and result["final_polarity_result"]
    assert result["latency_seconds"] == .25


def test_production_realization_prompts_stay_within_character_budget():
    client = object.__new__(TransformersLLMClient)
    prompts = [
        TransformersLLMClient._build_prompt(client, context)
        for case in load_benchmark()["cases"]
        if (context := context_for_case(case, two_stage=True))["grounded_content_plan"]
    ]
    assert prompts and max(map(len, prompts)) <= 2_400
