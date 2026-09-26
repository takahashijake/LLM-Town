#!/usr/bin/env python3
"""Opt-in serial-versus-batched benchmark for an already-cached local model."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.llm.client import TransformersLLMClient
from src.llm.generation import (
    ConversationGenerationRequest,
    generation_request_id,
)
from src.simulation.conversation_scheduler import derive_conversation_seed


def _context(index: int, seed: int) -> dict:
    return {
        "speaker": f"Resident{index * 2}",
        "listener": f"Resident{index * 2 + 1}",
        "speaker_personality": "thoughtful",
        "session_transcript": [],
        "conversation_request_seed": seed,
        "grounded_content_plan": {
            "history_use": "required",
            "permitted_fact": "A previously promised task was fulfilled.",
            "knowledge_basis": "participant",
            "event_type": "commitment_fulfilled",
            "required_polarity": "fulfilled",
            "social_intent": "acknowledge",
            "forbidden_assertions": [],
        },
    }


def _requests(count: int, simulation_seed: int):
    rows = []
    for index in range(count):
        session_id = f"benchmark-session-{index}"
        seed = derive_conversation_seed(
            simulation_seed, 1, 8, session_id, 0, 0,
            schedule_index=index, request_kind="primary",
        )
        rows.append(ConversationGenerationRequest(
            request_id=generation_request_id(
                simulation_seed=simulation_seed,
                day=1,
                hour=8,
                session_id=session_id,
                schedule_index=index,
                turn_index=0,
                generation_attempt=0,
                request_kind="primary",
            ),
            session_id=session_id,
            schedule_index=index,
            turn_index=0,
            generation_attempt=0,
            seed=seed,
            request_kind="primary",
            context=_context(index, seed),
        ))
    return rows


def _serial(client, requests):
    started = time.perf_counter()
    outputs = []
    tokens = 0
    for request in requests:
        outputs.append(client.generate_conversation(dict(request.context)))
        tokens += int(client.last_generated_token_count)
    elapsed = time.perf_counter() - started
    return {
        "wall_clock_seconds": elapsed,
        "model_generate_invocations": len(requests),
        "request_count": len(requests),
        "generated_token_count": tokens,
        "requests_per_second": len(requests) / elapsed,
        "generated_tokens_per_second": tokens / elapsed,
        "output_sha256": hashlib.sha256(
            json.dumps(outputs, sort_keys=True).encode()
        ).hexdigest(),
    }


def _batched(client, requests, batch_size):
    started = time.perf_counter()
    outputs = []
    invocations = 0
    tokens = 0
    for offset in range(0, len(requests), batch_size):
        rows = client.generate_conversation_batch(
            requests[offset:offset + batch_size]
        )
        invocations += 1
        outputs.extend(row.output for row in rows)
        tokens += sum(row.generated_token_count for row in rows)
    elapsed = time.perf_counter() - started
    return {
        "wall_clock_seconds": elapsed,
        "model_generate_invocations": invocations,
        "request_count": len(requests),
        "generated_token_count": tokens,
        "requests_per_second": len(requests) / elapsed,
        "generated_tokens_per_second": tokens / elapsed,
        "output_sha256": hashlib.sha256(
            json.dumps(outputs, sort_keys=True).encode()
        ).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--batch-sizes", type=int, nargs="+", default=[2, 4, 8, 16])
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if any(size < 1 for size in args.batch_sizes):
        parser.error("batch sizes must be positive integers")

    import torch
    import transformers

    artifact = {
        "benchmark": "batched-local-llm-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        ).strip(),
        "model_name": args.model,
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "cuda_available": torch.cuda.is_available(),
        "local_files_only": True,
        "seed": args.seed,
        "max_new_tokens": args.max_new_tokens,
        "results": [],
    }
    if not torch.cuda.is_available():
        artifact.update({"status": "skipped", "reason": "CUDA is unavailable"})
    else:
        artifact["cuda_device"] = torch.cuda.get_device_name(0)
        try:
            client = TransformersLLMClient(
                model_name=args.model,
                max_new_tokens=args.max_new_tokens,
                seed=args.seed,
                local_files_only=True,
            )
        except OSError as error:
            artifact.update({
                "status": "skipped",
                "reason": f"cached model unavailable: {error}",
            })
        else:
            artifact["status"] = "completed"
            torch.cuda.reset_peak_memory_stats()
            for size in args.batch_sizes:
                requests = _requests(size, args.seed)
                artifact["results"].append({
                    "simultaneous_requests": size,
                    "serial": _serial(client, requests),
                    "batched": _batched(client, requests, size),
                })
            artifact.update(client.generation_runtime_metadata())

    rendered = json.dumps(artifact, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
