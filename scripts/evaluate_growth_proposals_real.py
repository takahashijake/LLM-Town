#!/usr/bin/env python3
"""Optionally ask the existing local-model client for two V6 proposals."""

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

from src.analysis.growth_proposal_evaluation import _write_config
from src.llm.client import FakeLLMClient, TransformersLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.growth_proposals import LLMGrowthProposalProvider


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    client = TransformersLLMClient(
        model_name=args.model, seed=args.seed,
        local_files_only=args.local_files_only,
        max_new_tokens=180, temperature=0.2,
    )
    provider = LLMGrowthProposalProvider(client)
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
            engine.run(2, [8])
        print(json.dumps(engine.growth_proposals.to_dict(), indent=2, sort_keys=True))
        return 0 if all(
            row.status == "admitted" for row in engine.growth_proposals.records
        ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
