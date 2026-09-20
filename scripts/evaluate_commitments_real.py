#!/usr/bin/env python3
"""Controlled real-Qwen A/B evaluation of commitment grounding."""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.llm.client import TransformersLLMClient
from src.llm.parser import parse_llm_conversation_output
from src.simulation.conversation_session import ResponseOutcomeResolver
from src.simulation.engine import SimulationEngine


SCENARIOS = (
    ("help", "Could you help me repair the fence tomorrow?", "ask_for_help"),
    ("meet", "Could we meet at the cafe tomorrow?", "cooperate"),
    ("transfer", "Could you bring me one trade material tomorrow?", "ask_for_help"),
    ("failure", "Could you bring me one reference book tomorrow?", "ask_for_help"),
)


def generate(client, context):
    raw = client.generate_conversation(context)
    parsed = parse_llm_conversation_output(raw, allowed_actions=context["allowed_actions"])
    return raw, parsed


def run_arm(
    client, model_name: str, seed: int, enabled: bool,
    response_overrides: dict[str, str] | None = None,
) -> dict:
    random.seed(seed)
    client.torch.manual_seed(seed)
    if client.torch.cuda.is_available():
        client.torch.cuda.manual_seed_all(seed)
    with tempfile.TemporaryDirectory(prefix="llm-town-social-ab-") as work:
        engine = SimulationEngine(
            str(ROOT / "data/agents.json"), str(ROOT / "data/locations.json"),
            llm_client=client, state_path=Path(work) / "state.json",
            logs_dir=Path(work) / "logs",
        )
        # Both arms retain prompt grounding; only authoritative execution
        # pressure differs in this Phase-2 comparison.
        engine.commitment_grounding_enabled = True
        alice, bob = engine.agents[0], engine.agents[3]
        alice.location_id = bob.location_id = "cafe"
        resolver = ResponseOutcomeResolver()
        events = []
        counters = {key: 0 for key in (
            "proposals", "accepted", "declined", "unresolved", "follow_through",
            "contradictions", "forgotten", "false_fulfillment", "parsing_success",
            "intent_action_compatible", "repetitions", "runtime_failures", "malformed_output",
            "candidates", "feasible", "selected", "executed", "fulfilled", "deadline_miss",
            "cancelled", "provenance_valid",
        )}
        failure_reasons = {}
        prior_lines = set()
        response_cache = {}
        for index, (name, proposal, semantic_action) in enumerate(SCENARIOS):
            # Each scenario is isolated so the A/B arms have identical initial
            # state and only the future grounding toggle differs.
            engine.commitment_system.commitments.clear()
            engine.commitment_system.processed_evidence_keys.clear()
            engine.commitment_system.next_number = index + 1
            counters["proposals"] += 1
            response_context = engine.prepare_conversation_context(
                "cafe", bob, alice, 1,
                session_transcript=[{"speaker": alice.name, "listener": bob.name,
                                     "dialogue": proposal}],
            )["context"]
            response_context["suggested_action"] = "chat"
            try:
                client.torch.manual_seed(seed * 100 + index * 2)
                if response_overrides and name in response_overrides:
                    raw = response_overrides[name]
                    parsed = parse_llm_conversation_output(
                        raw, allowed_actions=response_context["allowed_actions"],
                    )
                else:
                    raw, parsed = generate(client, response_context)
                response_cache[name] = raw
                parsed_ok = parsed.get("action_source") == "llm" and bool(parsed.get("dialogue"))
                counters["parsing_success"] += int(parsed_ok)
                counters["malformed_output"] += int(not parsed_ok)
            except Exception as error:
                counters["runtime_failures"] += 1
                events.append({"scenario": name, "stage": "response", "error": repr(error)})
                continue
            response = parsed["dialogue"]
            outcome = resolver.resolve(semantic_action, response)
            counters[outcome if outcome in {"accepted", "declined"} else "unresolved"] += 1
            item = engine.commitment_system.process_response(
                proposer_id=alice.id, counterpart_id=bob.id, proposal_text=proposal,
                response_text=response, outcome=outcome, day=1, tick=8,
                session_id=f"{name}-{seed}-{enabled}", proposal_turn=0,
                response_turn=1,
                known_goods={good_id: good.name for good_id, good in engine.materials.goods.items()},
            )
            opportunity = None
            if item and item.status == "accepted":
                options = engine.commitment_system.opportunities_for_agent(
                    bob.id, day=2, tick=8,
                )
                opportunity = options[0] if options else None
                counters["candidates"] += int(opportunity is not None)
                counters["feasible"] += int(
                    opportunity is not None and opportunity.feasibility == "feasible"
                )
                if enabled and opportunity and opportunity.feasibility == "feasible":
                    random.seed(seed * 1000 + index)
                    before = len(engine.commitment_system.execution_records)
                    engine.activity_system.run_agent_activities(
                        agents=[bob], location_ids=[place.id for place in engine.locations],
                        day=2, hour=8, current_daily_event=None, agent_intents={},
                    )
                    activity_record = engine.activity_records[-1]
                    selected = activity_record.get("source_commitment_id") == item.id
                    counters["selected"] += int(selected)
                    executed = len(engine.commitment_system.execution_records) > before
                    counters["executed"] += int(executed)
                    counters["provenance_valid"] += int(
                        executed and engine.commitment_system.execution_records[-1].get(
                            "source_commitment_id"
                        ) == item.id
                    )
                if item.status == "accepted":
                    engine.commitment_system.expire_due(day=3, tick=8)
                counters["fulfilled"] += int(item.status == "fulfilled")
                counters["deadline_miss"] += int(item.status == "expired")
                if item.status != "fulfilled":
                    if opportunity is None:
                        reason = "no_candidate_generated"
                    elif opportunity.feasibility != "feasible":
                        reason = opportunity.infeasibility_reason
                    elif not enabled:
                        reason = "candidate_never_selected"
                    elif not any(record.get("commitment_id") == item.id
                                 for record in engine.commitment_system.execution_records):
                        selected_record = next((record for record in engine.activity_records
                                                if record.get("source_commitment_id") == item.id), None)
                        reason = "selected_but_execution_failed" if selected_record else "candidate_never_selected"
                    else:
                        reason = "unknown"
                    failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
            future_context = engine.prepare_conversation_context("cafe", bob, alice, 3)["context"]
            future_context["suggested_action"] = "chat"
            try:
                client.torch.manual_seed(seed * 100 + index * 2 + 1)
                future_raw, future_parsed = generate(client, future_context)
                parsed_ok = (
                    future_parsed.get("action_source") == "llm"
                    and bool(future_parsed.get("dialogue"))
                )
                counters["parsing_success"] += int(parsed_ok)
                counters["malformed_output"] += int(not parsed_ok)
            except Exception as error:
                counters["runtime_failures"] += 1
                events.append({"scenario": name, "stage": "future", "error": repr(error)})
                continue
            future = future_parsed["dialogue"]
            lower = future.lower()
            remembers = any(word in lower for word in (
                "fence", "cafe", "trade material", "supplies", "promise", "agreed", "couldn't", "cannot",
            ))
            if item and outcome == "accepted":
                counters["follow_through"] += int(remembers)
                counters["forgotten"] += int(not remembers)
                contradiction = (
                    (item.status == "expired" and any(x in lower for x in ("will help", "still will", "i'll help")))
                    or (item.status == "fulfilled" and any(x in lower for x in ("will bring", "haven't brought")))
                )
                counters["contradictions"] += int(contradiction)
            claimed_transfer = any(x in lower for x in ("i gave", "i brought", "i transferred", "already gave"))
            counters["false_fulfillment"] += int(
                name == "transfer" and claimed_transfer and (not item or item.status != "fulfilled")
            )
            counters["intent_action_compatible"] += int(
                future_parsed["action"] == "chat" or future_parsed["action"] in lower
            )
            normalized = " ".join(future.lower().split())
            counters["repetitions"] += int(normalized in prior_lines)
            prior_lines.add(normalized)
            events.append({
                "scenario": name, "proposal": proposal, "raw_response": raw,
                "response": response, "outcome": outcome,
                "commitment": item.to_dict() if item else None,
                "future_context_commitments": future_context.get("active_commitments", []),
                "raw_future": future_raw, "future": future,
            })
        accepted = counters["accepted"]
        conversations = len(events) * 2
        metrics = {
            "conversations": conversations,
            "proposal_count": counters["proposals"],
            "acceptance_rate": accepted / counters["proposals"],
            "proposal_resolution_rate": (counters["accepted"] + counters["declined"]) / counters["proposals"],
            "follow_through_rate": counters["follow_through"] / accepted if accepted else 0.0,
            "contradiction_rate": counters["contradictions"] / accepted if accepted else 0.0,
            "forgotten_commitment_rate": counters["forgotten"] / accepted if accepted else 0.0,
            "false_fulfillment_rate": counters["false_fulfillment"] / max(1, counters["proposals"]),
            "valid_action_parsing": counters["parsing_success"] / max(1, conversations),
            "intent_action_compatibility": counters["intent_action_compatible"] / max(1, len(events)),
            "repetition_rate": counters["repetitions"] / max(1, len(events)),
            "runtime_failures": counters["runtime_failures"],
            "malformed_output_rate": counters["malformed_output"] / max(1, conversations),
            "actionable_commitment_opportunity_rate": counters["candidates"] / accepted if accepted else 0.0,
            "feasible_opportunity_rate": counters["feasible"] / counters["candidates"] if counters["candidates"] else 0.0,
            "commitment_action_selection_rate": counters["selected"] / counters["feasible"] if counters["feasible"] else 0.0,
            "authoritative_execution_rate": counters["executed"] / counters["selected"] if counters["selected"] else 0.0,
            "accepted_commitment_fulfillment_rate": counters["fulfilled"] / accepted if accepted else 0.0,
            "deadline_miss_rate": counters["deadline_miss"] / accepted if accepted else 0.0,
            "explicit_cancellation_rate": counters["cancelled"] / accepted if accepted else 0.0,
            "action_commitment_provenance_validity": counters["provenance_valid"] / counters["executed"] if counters["executed"] else 1.0,
        }
        result = {"model": model_name, "seed": seed, "grounding_enabled": True,
                  "execution_pressure_enabled": enabled, "metrics": metrics,
                  "funnel": {key: counters[key] for key in
                             ("accepted", "candidates", "feasible", "selected", "executed", "fulfilled")},
                  "failure_classification": failure_reasons, "events": events}
        result["response_cache"] = response_cache
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / "outputs" / "commitment_real" / (
        args.model_name.replace("/", "--") + ".json"
    )
    client = TransformersLLMClient(args.model_name)
    runs = []
    for seed in args.seeds:
        baseline = run_arm(client, args.model_name, seed, False)
        enabled = run_arm(
            client, args.model_name, seed, True,
            response_overrides=baseline["response_cache"],
        )
        runs.extend((baseline, enabled))
    document = {"model": args.model_name, "seeds": args.seeds,
                "predefined_metrics": list(runs[0]["metrics"]), "runs": runs}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2))
    print(f"Wrote controlled commitment A/B evaluation to {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
