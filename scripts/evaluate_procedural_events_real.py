#!/usr/bin/env python3
"""Optionally exercise one event proposal through the local Transformers client."""

import argparse
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.procedural_event_evaluation import _write_config
from src.llm.client import FakeLLMClient, TransformersLLMClient
from src.simulation.engine import SimulationEngine


class BootstrapThenModelProvider:
    provider_kind = "existing_llm_client_event"

    def __init__(self, client):
        self.client = client
        self.event_context = None
        self.raw_event_result = None

    def propose_resident(self, context):
        return {
            "name": "Mira", "personality": "curious and community-minded",
            "goals": ["learn local customs", "build close friendships"],
        }

    def propose_location(self, context):
        return {
            "name": "Story Grove",
            "description": "A small public grove for conversation and reading.",
            "affinities": ["social", "knowledge", "community"],
        }

    def propose_event(self, context):
        self.event_context = context
        self.raw_event_result = self.client.generate_growth_proposal("event", context)
        return self.raw_event_result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--seed", type=int, default=23)
    args = parser.parse_args()
    client = TransformersLLMClient(
        model_name=args.model, seed=args.seed,
        local_files_only=args.local_files_only,
        max_new_tokens=180, temperature=0.2,
    )
    provider = BootstrapThenModelProvider(client)
    with TemporaryDirectory() as directory:
        root = Path(directory)
        config = _write_config(root)
        engine = SimulationEngine(
            "data/agents.json", "data/locations.json",
            llm_client=FakeLLMClient(), growth_proposal_provider=provider,
            town_growth_path=config, state_path=root / "state.json",
            logs_dir=root / "logs", simulation_seed=args.seed,
        )
        with redirect_stdout(StringIO()):
            engine.run(40, [8])
        record = next(
            (item for item in engine.growth_proposals.records
             if item.kind == "event"), None
        )
        report = {
            "target_context": provider.event_context,
            "raw_model_result": provider.raw_event_result,
            "parser_result": record.status if record else "not_attempted",
            "admission_reason": record.reason if record else "no_eligible_target",
            "generated_template_id": record.generated_template_id if record else None,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if record is not None and record.status == "admitted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
