#!/usr/bin/env python3
"""Run reproducible balanced grounded-dialogue live experiments."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis.grounded_dialogue_benchmark import (
    PARSER_VERSION, VALIDATOR_VERSION, acceptance, aggregate, capability_tier, classify_response,
    context_for_case, git_sha, load_benchmark, prompt_hash,
)
from src.llm.client import TransformersLLMClient
from src.llm.grounding import grounded_fallback
from src.llm.response_contract import TRANSFORMERS_CAPABILITIES

MODELS = {
    "3b": "Qwen/Qwen2.5-3B-Instruct",
    "7b": "Qwen/Qwen2.5-7B-Instruct",
}
ABLATIONS = {
    "A_baseline": {},
    "B_plan_model_metadata": {"two_stage": True},
    "C_engine_metadata": {"two_stage": True, "engine_owned_metadata": True},
    "D_engine_repair_fallback": {"two_stage": True, "engine_owned_metadata": True,
                                 "semantic_repair": True},
}


def model_digest(client) -> str:
    config = client.model.config.to_json_string(use_diff=False)
    return hashlib.sha256(config.encode()).hexdigest()


def run_one(model_key: str, ablation: str, seeds: list[int], retry_format: bool,
            case_ids: set[str] | None = None) -> dict:
    import transformers
    benchmark = load_benchmark()
    options = dict(ABLATIONS[ablation])
    two_stage = options.pop("two_stage", False)
    engine_owned = options.pop("engine_owned_metadata", False)
    semantic_repair = options.pop("semantic_repair", False)
    client = TransformersLLMClient(
        model_name=MODELS[model_key], max_new_tokens=120, temperature=.4, top_p=.9,
        **options,
    )
    records, prompts = [], []
    cache_path = ROOT / "outputs/grounded_dialogue/v3-generation-cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    digest = model_digest(client)
    for seed in seeds:
        for case in benchmark["cases"]:
            if case_ids and case["id"] not in case_ids:
                continue
            client.seed = seed
            context = context_for_case(case, two_stage=two_stage)
            if two_stage and not engine_owned:
                context["model_generated_grounding_metadata"] = True
            error, raw, retries = "", "", 0
            repair_used = fallback_used = False
            try:
                rendered = client.render_conversation_prompt(context)
                prompts.append(rendered)
                content_plan_hash = hashlib.sha256(json.dumps(
                    context.get("grounded_content_plan"), sort_keys=True
                ).encode()).hexdigest()
                cache_key = hashlib.sha256(json.dumps({
                    "model_digest": digest,
                    "prompt_hash": hashlib.sha256(rendered.encode()).hexdigest(),
                    "content_plan_hash": content_plan_hash, "seed": seed,
                    "generation_configuration": client.generation_config,
                    "parser_version": PARSER_VERSION,
                }, sort_keys=True).encode()).hexdigest()
                if cache_key in cache:
                    raw = cache[cache_key]
                else:
                    raw = client.generate_conversation(context)
                    cache[cache_key] = raw
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(json.dumps(cache, indent=2) + "\n")
                first = classify_response(case, raw, engine_owned_metadata=engine_owned)
                if retry_format and not first["schema_parse_success"]:
                    raw = client.repair_format(raw, first["parsed_response"]["envelope_status"])
                    retries = 1
                    first = classify_response(case, raw, engine_owned_metadata=engine_owned)
                if (semantic_repair and not context.get("grounded_content_plan")
                        and not first["schema_parse_success"]):
                    raw = client.repair_format(
                        raw, first["parsed_response"]["envelope_status"]
                    )
                    retries += 1
                    first = classify_response(case, raw, engine_owned_metadata=engine_owned)
                    if not first["schema_parse_success"]:
                        fallback_used = True
                        raw = json.dumps({"utterance": "I understand."})
                if semantic_repair and context.get("grounded_content_plan") and (
                    not first["schema_parse_success"] or not first["history_used"]
                    or not first["polarity_correct"] or first["private_leakage"]
                    or first["authority_contradiction"]
                ):
                    repair_used = True
                    raw = client.repair_grounded_realization(
                        context, raw, first["validator"]["reason"] or "planned meaning not realized"
                    )
                    retries += 1
                    repaired = classify_response(
                        case, raw, retry_count=retries,
                        engine_owned_metadata=engine_owned, repair_used=True,
                    )
                    if (not repaired["schema_parse_success"] or not repaired["history_used"]
                            or not repaired["polarity_correct"] or repaired["private_leakage"]
                            or repaired["authority_contradiction"]):
                        fallback_used = True
                        raw = json.dumps({"utterance": grounded_fallback(
                            context["grounded_content_plan"]
                        )})
                record = classify_response(
                    case, raw, retry_count=retries,
                    engine_owned_metadata=engine_owned, repair_used=repair_used,
                    fallback_used=fallback_used,
                    truncated=getattr(client, "last_generated_token_count", 0) >= client.generation_config["max_new_tokens"],
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                record = classify_response(
                    case, raw, retry_count=retries, generation_error=error,
                    engine_owned_metadata=engine_owned, repair_used=repair_used,
                    fallback_used=fallback_used,
                )
            record.update({"seed": seed, "prompt_index": len(prompts) - 1})
            records.append(record)
    metrics = aggregate(records)
    return {
        "artifact_version": "grounded-dialogue-live-v3", "benchmark_version": benchmark["version"],
        "schema_version": benchmark["schema_version"], "parser_version": PARSER_VERSION,
        "validator_version": VALIDATOR_VERSION, "ablation": ablation,
        "model": MODELS[model_key], "model_digest": digest,
        "backend": {"provider": TRANSFORMERS_CAPABILITIES.provider,
                    "version": transformers.__version__, "capabilities": [m.value for m in TRANSFORMERS_CAPABILITIES.supported_modes],
                    "detail": TRANSFORMERS_CAPABILITIES.detail},
        "model_configuration": {"max_new_tokens": 120, "temperature": .4, "top_p": .9,
                                "top_k": getattr(client.model.generation_config, "top_k", None),
                                "do_sample": True,
                                "seeds": seeds, "chat_template": client.tokenizer.chat_template,
                                "format_retry": retry_format, **options, "two_stage": two_stage,
                                "engine_owned_metadata": engine_owned,
                                "semantic_repair": semantic_repair},
        "commit_sha": git_sha(ROOT), "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(), "prompt_hash": prompt_hash(prompts),
        "benchmark_hash": hashlib.sha256(json.dumps(benchmark, sort_keys=True).encode()).hexdigest(),
        "metrics": metrics, "acceptance": acceptance(metrics),
        "capability_tier": capability_tier(metrics), "prompts": prompts, "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    parser.add_argument("--ablations", nargs="+", choices=ABLATIONS, default=list(ABLATIONS))
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 73, 101])
    parser.add_argument("--format-retry", action="store_true")
    parser.add_argument("--case-ids", nargs="+", help="Run only named targeted cases")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/grounded_dialogue/v2")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for model in args.models:
        for ablation in args.ablations:
            artifact = run_one(
                model, ablation, args.seeds, args.format_retry,
                set(args.case_ids or []),
            )
            path = args.output_dir / f"{model}-{ablation}.json"
            path.write_text(json.dumps(artifact, indent=2) + "\n")
            summaries.append({"model": model, "ablation": ablation,
                              "metrics": artifact["metrics"], "passed": artifact["acceptance"]["passed"]})
            print(json.dumps(summaries[-1]))
    (args.output_dir / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
