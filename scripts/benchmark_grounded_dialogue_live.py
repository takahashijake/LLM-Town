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
    PARSER_VERSION, VALIDATOR_VERSION, acceptance, aggregate, classify_response,
    context_for_case, git_sha, load_benchmark, prompt_hash,
)
from src.llm.client import TransformersLLMClient
from src.llm.response_contract import TRANSFORMERS_CAPABILITIES

MODELS = {
    "3b": "Qwen/Qwen2.5-3B-Instruct",
    "7b": "Qwen/Qwen2.5-7B-Instruct",
}
ABLATIONS = {
    "A_baseline": {},
    "B_constrained_decoding": {"output_constraint": "prompted_json"},
    "C_simplified_schema": {"simplified_contract": True},
    "D_prompt_refinement": {"prompt_refinement": True},
    "E_few_shot": {"few_shot": True},
    "F_parser_normalization": {},
    "G_combination": {"simplified_contract": True, "prompt_refinement": True, "few_shot": True},
    "H_two_stage": {"simplified_contract": True, "prompt_refinement": True,
                    "two_stage": True},
}


def model_digest(client) -> str:
    config = client.model.config.to_json_string(use_diff=False)
    return hashlib.sha256(config.encode()).hexdigest()


def run_one(model_key: str, ablation: str, seeds: list[int], retry_format: bool) -> dict:
    import transformers
    benchmark = load_benchmark()
    options = dict(ABLATIONS[ablation])
    two_stage = options.pop("two_stage", False)
    client = TransformersLLMClient(
        model_name=MODELS[model_key], max_new_tokens=120, temperature=.4, top_p=.9,
        **options,
    )
    records, prompts = [], []
    for seed in seeds:
        for case in benchmark["cases"]:
            client.seed = seed
            context = context_for_case(case, two_stage=two_stage)
            error, raw, retries = "", "", 0
            try:
                raw = client.generate_conversation(context)
                prompts.append(client.last_rendered_prompt)
                first = classify_response(case, raw)
                if retry_format and not first["schema_parse_success"]:
                    raw = client.repair_format(raw, first["parsed_response"]["envelope_status"])
                    retries = 1
                record = classify_response(
                    case, raw, retry_count=retries,
                    truncated=client.last_generated_token_count >= client.generation_config["max_new_tokens"],
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                record = classify_response(case, raw, retry_count=retries,
                                           generation_error=error)
            record.update({"seed": seed, "prompt_index": len(prompts) - 1})
            records.append(record)
    metrics = aggregate(records)
    return {
        "artifact_version": "grounded-dialogue-live-v2", "benchmark_version": benchmark["version"],
        "schema_version": benchmark["schema_version"], "parser_version": PARSER_VERSION,
        "validator_version": VALIDATOR_VERSION, "ablation": ablation,
        "model": MODELS[model_key], "model_digest": model_digest(client),
        "backend": {"provider": TRANSFORMERS_CAPABILITIES.provider,
                    "version": transformers.__version__, "capabilities": [m.value for m in TRANSFORMERS_CAPABILITIES.supported_modes],
                    "detail": TRANSFORMERS_CAPABILITIES.detail},
        "model_configuration": {"max_new_tokens": 120, "temperature": .4, "top_p": .9,
                                "top_k": getattr(client.model.generation_config, "top_k", None),
                                "do_sample": True,
                                "seeds": seeds, "chat_template": client.tokenizer.chat_template,
                                "format_retry": retry_format, **options, "two_stage": two_stage},
        "commit_sha": git_sha(ROOT), "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(), "prompt_hash": prompt_hash(prompts),
        "benchmark_hash": hashlib.sha256(json.dumps(benchmark, sort_keys=True).encode()).hexdigest(),
        "metrics": metrics, "acceptance": acceptance(metrics), "prompts": prompts, "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    parser.add_argument("--ablations", nargs="+", choices=ABLATIONS, default=list(ABLATIONS))
    parser.add_argument("--seeds", nargs="+", type=int, default=[42, 73, 101])
    parser.add_argument("--format-retry", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/grounded_dialogue/v2")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for model in args.models:
        for ablation in args.ablations:
            artifact = run_one(model, ablation, args.seeds, args.format_retry)
            path = args.output_dir / f"{model}-{ablation}.json"
            path.write_text(json.dumps(artifact, indent=2) + "\n")
            summaries.append({"model": model, "ablation": ablation,
                              "metrics": artifact["metrics"], "passed": artifact["acceptance"]["passed"]})
            print(json.dumps(summaries[-1]))
    (args.output_dir / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
