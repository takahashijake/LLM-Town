#!/usr/bin/env python3
"""Controlled real-model A/B for archived fulfilled-vs-failed grounding."""

import argparse
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.llm.client import TransformersLLMClient
from src.llm.parser import parse_llm_conversation_output
from src.simulation.engine import SimulationEngine


def make_context(engine, outcome, enabled):
    listener, speaker = engine.agents[0], engine.agents[3]
    item = engine.commitment_system.create(
        proposer_id=listener.id, counterpart_id=speaker.id,
        commitment_type="transfer", day=3, due_day=5,
        metadata={"good_id": "trade_materials", "quantity": 1},
    )
    engine.commitment_system.transition(item.id, "accepted", day=3, reason="accepted")
    if outcome == "fulfilled":
        engine.commitment_system.fulfill_transfer(item.id, day=4)
    else:
        engine.commitment_system.transition(item.id, "expired", day=6,
                                            reason="due_window_passed")
    for agent in (speaker, listener):
        engine.journal_system.compress_old_memories(agent, current_day=40)
    context = engine.prepare_conversation_context(
        "market", speaker, listener, 40
    )["context"]
    context["suggested_action"] = "chat"
    context["allowed_actions"] = ["chat", "compliment", "apologize",
                                  "offer_help", "ask_for_help", "cooperate"]
    # At day 40 pair commitment context has expired; archived causal memory is
    # the only arm difference.
    context["active_commitments"] = []
    context["commitment_records"] = []
    if not enabled:
        context["relevant_memories"] = []
        context["grounding_packet"] = []
        context["grounding_sources"] = {
            key: value for key, value in context.get("grounding_sources", {}).items()
            if not key.startswith("g")
        }
        context["focus_options"] = [x for x in context.get("focus_options", [])
                                    if "history" not in x]
    return context


def run(model, seeds):
    client = TransformersLLMClient(model_name=model, max_new_tokens=120,
                                   temperature=0.4, top_p=0.9)
    records = []
    for seed in seeds:
        for outcome in ("fulfilled", "failed"):
            for enabled in (False, True):
                random.seed(seed)
                client.torch.manual_seed(seed)
                client.torch.cuda.manual_seed_all(seed)
                with tempfile.TemporaryDirectory(prefix="causal-real-") as work:
                    engine = SimulationEngine(
                        str(ROOT / "data/agents.json"), str(ROOT / "data/locations.json"),
                        llm_client=client, state_path=Path(work) / "state.json",
                        logs_dir=Path(work) / "logs",
                    )
                    context = make_context(engine, outcome, enabled)
                    error = ""
                    try:
                        raw = client.generate_conversation(context)
                        parsed = parse_llm_conversation_output(
                            raw, allowed_actions=context["allowed_actions"]
                        )
                        text = parsed.get("dialogue", "")
                        malformed = parsed.get("action_source") != "llm" or not text
                    except Exception as exc:
                        raw, text, malformed, error = "", "", True, repr(exc)
                    lower = text.lower()
                    fulfillment = any(x in lower for x in (
                        "delivered", "fulfilled", "kept my promise", "kept the promise",
                        "brought you the trade material", "gave you the trade material",
                    ))
                    failure = any(x in lower for x in ("failed", "didn't", "did not", "unfulfilled", "missed"))
                    records.append({
                        "model": model, "seed": seed, "outcome": outcome,
                        "historical_recall": enabled, "context_memories": context["relevant_memories"],
                        "raw": raw, "dialogue": text, "malformed": malformed,
                        "runtime_error": error, "mentions_fulfillment": fulfillment,
                        "mentions_failure": failure,
                        "correct_distinction": (fulfillment and not failure) if outcome == "fulfilled"
                                               else (failure and not fulfillment),
                        "contradiction": failure if outcome == "fulfilled" else fulfillment,
                    })
    def metrics(rows):
        count = len(rows)
        return {
            "samples": count,
            "historical_grounding_rate": sum(r["correct_distinction"] for r in rows) / count,
            "authoritative_contradiction_rate": sum(r["contradiction"] for r in rows) / count,
            "malformed_output_rate": sum(r["malformed"] for r in rows) / count,
            "runtime_failure_rate": sum(bool(r["runtime_error"]) for r in rows) / count,
        }
    return {
        "model": model,
        "arms": {
            "recent_only": metrics([r for r in records if not r["historical_recall"]]),
            "causal_historical": metrics([r for r in records if r["historical_recall"]]),
        },
        "records": records,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 73])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.model_name, args.seeds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({"model": result["model"], "arms": result["arms"]}, indent=2))
