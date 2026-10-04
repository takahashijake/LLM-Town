#!/usr/bin/env python3
"""Optionally exercise one commerce proposal through a local model."""

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

from src.analysis.procedural_commerce_evaluation import (
    _write_config, StaticProceduralCommerceProvider, HORIZON_DAYS,
)
from src.analysis.v6_freeze_evaluation import (
    MultiBranchProvider, write_config as _multi_config, HORIZON_DAYS as MULTI_HORIZON,
)
from src.llm.client import FakeLLMClient, TransformersLLMClient
from src.simulation.engine import SimulationEngine


class BootstrapThenModelProvider(StaticProceduralCommerceProvider):
    provider_kind = "existing_llm_client_commerce"

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.commerce_context = None
        self.raw_commerce_result = None

    def propose_commerce(self, context: dict) -> object:
        self.commerce_context = context
        self.raw_commerce_result = self.client.generate_growth_proposal("commerce", context)
        return self.raw_commerce_result


class MultiBranchModelProvider(MultiBranchProvider):
    """Bootstrap both real branches; use the model only for closed offers."""
    provider_kind = "existing_llm_client_multi_commerce"

    def __init__(self, client: TransformersLLMClient) -> None:
        super().__init__()
        self.client = client
        self.contexts = []
        self.raw_results = []

    def propose_commerce(self, context: dict) -> object:
        self.calls["commerce"] += 1
        raw = self.client.generate_growth_proposal("commerce", context)
        self.contexts.append(context)
        self.raw_results.append(raw)
        return raw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--seed", type=int, default=23)
    parser.add_argument("--multi-branch", action="store_true",
                        help="exercise two independently selected commerce targets")
    args = parser.parse_args()
    client = TransformersLLMClient(
        model_name=args.model, seed=args.seed,
        local_files_only=args.local_files_only,
        max_new_tokens=160, temperature=0.2,
    )
    provider = (MultiBranchModelProvider(client) if args.multi_branch
                else BootstrapThenModelProvider(client))
    with TemporaryDirectory() as directory:
        root = Path(directory)
        config = _multi_config(root) if args.multi_branch else _write_config(root)
        engine = SimulationEngine(
            "data/agents.json", "data/locations.json",
            llm_client=FakeLLMClient(), growth_proposal_provider=provider,
            town_growth_path=config, state_path=root / "state.json",
            logs_dir=root / "logs", simulation_seed=args.seed,
        )
        with redirect_stdout(StringIO()):
            engine.run(MULTI_HORIZON if args.multi_branch else HORIZON_DAYS, [8])
        if args.multi_branch:
            records = [row for row in engine.growth_proposals.records if row.kind == "commerce"]
            reports = [{
                "target_context": provider.contexts[index],
                "raw_model_result": provider.raw_results[index],
                "parser_result": row.status, "admission_reason": row.reason,
                "canonical_payload": row.canonical_payload,
                "generated_template_id": row.generated_template_id,
                "target_generated_location": row.target_location_template_id,
                "target_generated_institution": row.target_institution_template_id,
            } for index, row in enumerate(records)]
            print(json.dumps({"multi_branch": True, "proposals": reports}, indent=2, sort_keys=True))
            return 0 if len(records) == 2 and all(row.status == "admitted" for row in records) else 1
        record = next(
            (item for item in engine.growth_proposals.records
             if item.kind == "commerce"), None
        )
        template = (
            engine.growth_proposals.commerce_templates.get(
                record.generated_template_id
            ) if record and record.generated_template_id else None
        )
        report = {
            "target_context": provider.commerce_context,
            "raw_model_result": provider.raw_commerce_result,
            "parser_result": record.status if record else "not_attempted",
            "admission_reason": record.reason if record else "no_eligible_target",
            "canonical_payload": record.canonical_payload if record else None,
            "generated_template_id": template.id if template else None,
            "target_generated_location": (
                template.location_template_id if template else None
            ),
            "target_generated_institution": (
                template.institution_template_id if template else None
            ),
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if record is not None and record.status == "admitted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
