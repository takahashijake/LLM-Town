"""Balanced live benchmark and precise grounded-response classification."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from src.llm.grounding import GroundingValidator
from src.llm.parser import extract_json_object, parse_llm_conversation_output

BENCHMARK_PATH = Path(__file__).resolve().parents[2] / "data/grounded_dialogue_benchmark_v2.json"
PARSER_VERSION = "bounded-envelope-v2"
VALIDATOR_VERSION = "grounding-v1"


def load_benchmark(path: Path = BENCHMARK_PATH) -> dict:
    benchmark = json.loads(path.read_text())
    classes = Counter(case["class"] for case in benchmark["cases"])
    if len(benchmark["cases"]) < 24 or classes != {"must_use": 8, "may_use": 8, "must_not_use": 8}:
        raise ValueError("balanced benchmark requires exactly 8 cases in each history-use class")
    return benchmark


def context_for_case(case: dict, *, two_stage: bool = False) -> dict:
    fact = dict(case["fact"])
    fact.setdefault("event_day", 10)
    expose_history = not two_stage or case["class"] != "must_not_use"
    sources = {fact["ref"]: fact["fact"]} if expose_history else {}
    plan = None
    if two_stage and case["class"] == "must_use" and case["allowed_refs"]:
        plan = {
            "history_relevant": True, "grounding_ref": case["allowed_refs"][0],
            "required_polarity": case["required_polarity"], "counterpart": case["listener"],
            "dialogue_act": case["allowed_social_intents"][0],
        }
    return {
        "speaker": case["speaker"], "listener": case["listener"], "location": "market",
        "relationship_label": "acquaintance", "relationship_score": 0,
        "allowed_actions": ["chat", "apologize", "compliment", "cooperate"],
        "suggested_action": "chat", "grounding_packet": [fact] if expose_history else [],
        "grounding_sources": sources, "session_transcript": [
            {"speaker": case["listener"], "dialogue": case["question"]}
        ],
        "focus_options": ["Answer the listener's immediately preceding question."],
        "grounded_content_plan": plan,
    }


def _contains_any(text: str, values: list[str]) -> bool:
    lower = text.lower()
    return any(value.lower() in lower for value in values)


def classify_response(case: dict, raw: str, *, retry_count: int = 0,
                      generation_error: str = "", truncated: bool = False) -> dict:
    json_text = extract_json_object(raw)
    syntactic_json = False
    if json_text:
        try:
            syntactic_json = isinstance(json.loads(json_text), dict)
        except json.JSONDecodeError:
            pass
    parsed = parse_llm_conversation_output(raw, allowed_actions=[
        "chat", "apologize", "compliment", "cooperate",
    ])
    utterance = parsed["dialogue"]
    refs = parsed["grounding_refs"]
    allowed = set(case["allowed_refs"])
    supplied = {case["fact"]["ref"]}
    invalid_refs = sorted(set(refs) - supplied)
    forbidden_refs = sorted(set(refs) & set(case["forbidden_refs"]))
    valid_refs = sorted(set(refs) & supplied)
    context = context_for_case(case)
    validation = GroundingValidator().validate(
        utterance, refs, context, follow_through=parsed["follow_through"]
    )
    required_terms = case["required_terms"]
    content_matches = not required_terms or _contains_any(utterance, required_terms)
    forbidden_claims = [claim for claim in case["forbidden_claims"] if claim.lower() in utterance.lower()]
    history_used = bool(set(valid_refs) & allowed) and content_matches and not forbidden_claims
    if case["class"] == "must_not_use" and case["required_polarity"]:
        # Safe uncertainty/cancellation uses the supplied boundary without exposing a culprit.
        history_used = bool(set(valid_refs) & allowed) and content_matches and not forbidden_claims
    polarity_correct = (not case["required_polarity"] or content_matches) and not forbidden_claims
    counterpart_ok = all(
        not case["fact"].get("counterpart")
        or case["fact"]["counterpart"] == case["listener"]
        for ref in valid_refs if ref in allowed
    )
    follow = validation.follow_through or {}
    if follow.get("target") and follow["target"] != case["listener"]:
        counterpart_ok = False
    parse_success = parsed["envelope_status"] == "parsed" and bool(utterance)
    return {
        "case_id": case["id"], "expected_history_use": case["class"],
        "raw_response": raw, "parsed_response": parsed,
        "schema_parse_success": parse_success,
        "legacy_fallback_used": parsed["envelope_status"] == "legacy_plain_text",
        "syntactically_valid_json": syntactic_json,
        "parser_rejected_valid_structure": syntactic_json and not parse_success,
        "valid_grounding_references": not invalid_refs and not forbidden_refs,
        "valid_refs": valid_refs, "invalid_refs": invalid_refs,
        "forbidden_refs": forbidden_refs, "history_used": history_used,
        "polarity_correct": polarity_correct, "counterpart_correct": counterpart_ok,
        "unsupported_claims": forbidden_claims,
        "private_leakage": bool(forbidden_claims) and case["fact"]["knowledge_basis"] == "private_other",
        "authority_contradiction": validation.candidate_type == "authority_boundary",
        "validator": {"valid": validation.valid, "reason": validation.reason,
                      "candidate_type": validation.candidate_type},
        "generation_failure": bool(generation_error), "generation_error": generation_error,
        "truncated": truncated, "retry_count": retry_count,
    }


def aggregate(records: list[dict]) -> dict:
    count = len(records)
    rate = lambda key, rows=records: sum(bool(row[key]) for row in rows) / len(rows) if rows else 0.0
    required = [row for row in records if row["expected_history_use"] == "must_use"]
    optional = [row for row in records if row["expected_history_use"] == "may_use"]
    irrelevant = [row for row in records if row["expected_history_use"] == "must_not_use"]
    referenced = [row for row in records if row["parsed_response"]["grounding_refs"]]
    polarity = [row for row in records if row["expected_history_use"] == "must_use" or
                row["parsed_response"]["grounding_refs"]]
    return {
        "samples": count,
        "schema_parse_success": rate("schema_parse_success"),
        "legacy_fallback_use": rate("legacy_fallback_used"),
        "valid_grounding_reference_rate": rate("valid_grounding_references", referenced) if referenced else 1.0,
        "required_history_use": rate("history_used", required),
        "optional_history_use": rate("history_used", optional),
        "irrelevant_history_intrusion": rate("history_used", irrelevant),
        "polarity_accuracy": rate("polarity_correct", polarity),
        "counterpart_accuracy": rate("counterpart_correct", referenced) if referenced else 1.0,
        "unsupported_claims": sum(bool(row["unsupported_claims"]) for row in records),
        "private_leakage": sum(row["private_leakage"] for row in records),
        "authority_contradictions": sum(row["authority_contradiction"] for row in records),
        "generation_failures": rate("generation_failure"),
        "truncation": sum(row["truncated"] for row in records),
        "retry_count": sum(row["retry_count"] for row in records),
        "parser_rejected_valid_structure": sum(row["parser_rejected_valid_structure"] for row in records),
        "valid_but_incorrect_structure": sum(
            row["schema_parse_success"] and (
                not row["valid_grounding_references"] or bool(row["unsupported_claims"])
            ) for row in records
        ),
        "model_ignored_history": sum(row["schema_parse_success"] and not row["history_used"] for row in required),
    }


def prompt_hash(prompts: list[str]) -> str:
    return hashlib.sha256(json.dumps(prompts, sort_keys=True).encode()).hexdigest()


def git_sha(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def acceptance(metrics: dict) -> dict:
    checks = {
        "parse_success": metrics["schema_parse_success"] >= .95,
        "valid_refs": metrics["valid_grounding_reference_rate"] == 1.0,
        "private_leakage": metrics["private_leakage"] == 0,
        "authority": metrics["authority_contradictions"] == 0,
        "required_history": metrics["required_history_use"] >= .75,
        "irrelevant_intrusion": metrics["irrelevant_history_intrusion"] <= .10,
        "polarity": metrics["polarity_accuracy"] >= .90,
        "counterpart": metrics["counterpart_accuracy"] == 1.0,
        "generation": metrics["generation_failures"] <= .05,
    }
    return {"passed": all(checks.values()), "checks": checks}
