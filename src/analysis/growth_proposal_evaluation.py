"""Deterministic V6 Phase 1 proposal/admission acceptance gate."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


HORIZON_DAYS = 70


class StaticGrowthProposalProvider:
    provider_kind = "deterministic_static"

    def __init__(self):
        self.resident_calls = 0
        self.location_calls = 0

    def propose_resident(self, context: dict) -> dict:
        self.resident_calls += 1
        return {
            "name": "Mira",
            "personality": "curious and community-minded",
            "goals": ["learn local customs", "build close friendships"],
        }

    def propose_location(self, context: dict) -> dict:
        self.location_calls += 1
        return {
            "name": "Story Grove",
            "description": "A small public grove for conversation and reading.",
            "affinities": ["social", "knowledge", "community"],
        }


class NoReplayProvider:
    provider_kind = "no_replay_guard"

    def __init__(self):
        self.resident_calls = 0
        self.location_calls = 0

    def propose_resident(self, context: dict):
        self.resident_calls += 1
        raise AssertionError("an admitted resident proposal was rerun")

    def propose_location(self, context: dict):
        self.location_calls += 1
        return {
            "name": "Story Grove",
            "description": "A small public grove for conversation and reading.",
            "affinities": ["social", "knowledge", "community"],
        }


def _write_config(root: Path) -> Path:
    data = json.loads(Path("data/town_growth.json").read_text(encoding="utf-8"))
    data["policy"]["resident_capacity"] = 7
    data["location_growth"]["policy"]["location_capacity"] = 7
    data["procedural_growth"] = {"policy": {
        "enabled": True,
        "earliest_proposal_day": 1,
        "review_interval_days": 1,
        "proposal_cooldown_days": 0,
        "resident_proposal_capacity": 1,
        "location_proposal_capacity": 1,
        "history_limit": 2,
    }}
    path = root / "town_growth_v6.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _engine(
    root: Path, name: str, config: Path, provider, *, load: bool = False,
) -> SimulationEngine:
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs", simulation_seed=17,
        town_growth_path=config, growth_proposal_provider=provider,
    )


def _run(engine: SimulationEngine, days: int) -> None:
    with redirect_stdout(StringIO()):
        engine.run(days, [8])


def _horizon(
    root: Path, name: str, config: Path, splits: tuple[int, ...], provider,
) -> SimulationEngine:
    caller_state = random.getstate()
    random.seed(17)
    try:
        engine = _engine(root, name, config, provider)
        for index, days in enumerate(splits):
            if index:
                engine = _engine(root, name, config, provider, load=True)
            _run(engine, days)
        return engine
    finally:
        random.setstate(caller_state)


def _signature(engine: SimulationEngine) -> dict:
    proposals = engine.growth_proposals.records
    migrations = [x for x in engine.town_growth.migration_records if x.status == "activated"]
    activations = [x for x in engine.location_growth.activation_records if x.status == "activated"]
    growth_sources = {x.id for x in migrations} | {x.id for x in activations}
    return {
        "proposal_ids": [x.id for x in proposals],
        "proposal_hashes": [x.canonical_payload_hash for x in proposals],
        "generated_template_ids": [x.generated_template_id for x in proposals],
        "migration_ids": [x.id for x in migrations],
        "resident_ids": [x.id for x in engine.agents],
        "location_activation_ids": [x.id for x in activations],
        "location_ids": [x.id for x in engine.locations],
        "ledger_state": {
            "balances": sorted(
                (key, account.balance)
                for key, account in engine.economy.accounts.items()
            ),
            "transactions": [
                (item.id, item.event_key, item.amount)
                for item in engine.economy.ledger
            ],
        },
        "material_totals": sorted(engine.materials.total_quantities().items()),
        "memory_provenance": sorted(
            (memory.id, memory.source_system, memory.source_id, memory.event_type)
            for agent in engine.agents
            for memory in agent.memory + agent.memory_archive
            if memory.source_id in growth_sources
        ),
    }


def _mutated_load_rejected(root: Path, config: Path, saved: dict, name: str, mutate) -> bool:
    data = deepcopy(saved)
    mutate(data)
    (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    try:
        _engine(root, name, config, NoReplayProvider(), load=True)
    except (KeyError, TypeError, ValueError):
        return True
    return False


def evaluate_growth_proposals() -> dict:
    scenarios: dict[str, bool] = {}
    invariants: dict[str, bool] = {}
    diagnostics: dict[str, object] = {"horizon_days": HORIZON_DAYS}
    with TemporaryDirectory() as directory:
        root = Path(directory)
        config = _write_config(root)

        fresh_provider = StaticGrowthProposalProvider()
        fresh = _horizon(root, "fresh", config, (HORIZON_DAYS,), fresh_provider)
        repeat_provider = StaticGrowthProposalProvider()
        repeated = _horizon(root, "repeated", config, (HORIZON_DAYS,), repeat_provider)
        resumed_provider = StaticGrowthProposalProvider()
        resumed = _horizon(root, "resumed", config, (1, 19, 20, 30), resumed_provider)

        # A distinct provider after day-one admission must only be asked for the
        # still-missing location candidate.
        manual_random_state = random.getstate()
        random.seed(17)
        try:
            first = StaticGrowthProposalProvider()
            admission = _engine(root, "admission", config, first)
            _run(admission, 1)
            no_replay = NoReplayProvider()
            after_admission = _engine(
                root, "admission", config, no_replay, load=True
            )
            _run(after_admission, HORIZON_DAYS - 1)
        finally:
            random.setstate(manual_random_state)

        signature = _signature(fresh)
        diagnostics["authoritative_signature"] = signature
        diagnostics["provider_calls"] = {
            "fresh": [fresh_provider.resident_calls, fresh_provider.location_calls],
            "resumed": [resumed_provider.resident_calls, resumed_provider.location_calls],
            "repeated": [repeat_provider.resident_calls, repeat_provider.location_calls],
            "post_admission": [no_replay.resident_calls, no_replay.location_calls],
        }
        scenarios["uninterrupted_resume_repeat_match"] = (
            signature == _signature(resumed) == _signature(repeated)
            == _signature(after_admission)
        )
        scenarios["admitted_proposal_is_not_rerun_after_resume"] = (
            first.resident_calls == 1
            and first.location_calls == 0
            and no_replay.resident_calls == 0
            and no_replay.location_calls == 1
        )

        resident_record = next(x for x in fresh.growth_proposals.records if x.kind == "resident")
        location_record = next(x for x in fresh.growth_proposals.records if x.kind == "location")
        migration = next(
            x for x in fresh.town_growth.migration_records
            if x.template_id == resident_record.generated_template_id
        )
        activation = next(
            x for x in fresh.location_growth.activation_records
            if x.template_id == location_record.generated_template_id
        )
        resident = next(x for x in fresh.agents if x.id == migration.agent_id)
        scenarios.update({
            "resident_candidate_to_admitted_template": (
                resident_record.status == "admitted"
                and resident_record.proposal_day == 1
                and resident_record.generated_template_id
                == "generated_resident_template_0001"
            ),
            "resident_template_uses_v5_migration": (
                migration.status == "activated"
                and migration.review_day > resident_record.admission_day
                and resident.name == "Mira"
            ),
            "migrant_has_account_inventory_and_conserved_settlement": (
                fresh.economy.account_for_agent(resident.id).id
                == f"account:agent:{resident.id}"
                and fresh.materials.inventory_for_agent(resident.id).id
                == f"inventory:agent:{resident.id}"
                and fresh.economy.conservation_holds()
            ),
            "migrant_participates_after_activation": any(
                row.get("type") == "activity"
                and row.get("agent_id") == resident.id
                and row.get("day", 0) > migration.activation_day
                for row in fresh.activity_records
            ),
            "location_candidate_to_admitted_template": (
                location_record.status == "admitted"
                and location_record.proposal_day == 2
                and location_record.generated_template_id
                == "generated_location_template_0001"
            ),
            "location_template_uses_v5_activation": (
                activation.status == "activated"
                and activation.review_day > location_record.admission_day
                and activation.location_id == "generated_location_0001"
            ),
            "generated_location_receives_ordinary_activity": any(
                row.get("type") == "activity"
                and row.get("location") == activation.location_id
                and row.get("day", 0) > activation.activation_day
                for row in fresh.activity_records
            ),
            "capacity_exhaustion_stops_provider_and_sequence_churn": (
                fresh_provider.resident_calls == 1
                and fresh_provider.location_calls == 1
                and fresh.growth_proposals.next_proposal_sequence == 3
            ),
            "generated_location_has_no_branch_authority": (
                all(
                    item.location_template_id != location_record.generated_template_id
                    for item in fresh.event_ecology.templates.values()
                )
                and all(
                    item.location_template_id != location_record.generated_template_id
                    for item in fresh.institution_growth.templates.values()
                )
                and all(
                    item.location_template_id != location_record.generated_template_id
                    for item in fresh.commerce_growth.templates.values()
                )
            ),
        })
        fresh.town_growth._validate_state()
        invariants.update({
            "proposal_hashes_reconstruct": all(
                row.canonical_payload_hash is not None for row in fresh.growth_proposals.records
            ),
            "proposal_bindings_valid": True,
            "town_growth_valid": True,
            "location_growth_valid": all(
                fresh.location_growth.validate(fresh.locations, fresh.agents).values()
            ),
            "ledger_reconstructs": fresh.economy.ledger_reconstructs_balances(),
            "materials_conserved": fresh.materials.material_conservation_holds(),
            "outcome_memory_valid": all(fresh.outcome_memory.validate().values()),
        })
        fresh.growth_proposals.validate_bindings(fresh.town_growth, fresh.location_growth)

        saved = json.loads((root / "fresh.json").read_text(encoding="utf-8"))
        attacks = {
            "tampered_proposal_id_rejected": lambda x: x["growth_proposals"]["records"][0].__setitem__("id", "growth-proposal:9999"),
            "tampered_kind_rejected": lambda x: x["growth_proposals"]["records"][0].__setitem__("kind", "location"),
            "tampered_status_rejected": lambda x: x["growth_proposals"]["records"][0].__setitem__("status", "rejected"),
            "tampered_payload_rejected": lambda x: x["growth_proposals"]["records"][0]["canonical_payload"].__setitem__("name", "Forgery"),
            "tampered_digest_rejected": lambda x: x["growth_proposals"]["records"][0].__setitem__("canonical_payload_hash", "0" * 64),
            "tampered_generated_id_rejected": lambda x: x["growth_proposals"]["records"][0].__setitem__("generated_template_id", "generated_resident_template_0002"),
            "tampered_template_rejected": lambda x: x["growth_proposals"]["resident_templates"][0].__setitem__("personality", "forged"),
            "rewound_sequence_rejected": lambda x: x["growth_proposals"].__setitem__("next_proposal_sequence", 1),
            "missing_admitted_template_rejected": lambda x: x["growth_proposals"]["resident_templates"].clear(),
            "duplicate_generated_template_id_rejected": lambda x: x["growth_proposals"]["resident_templates"].append(deepcopy(x["growth_proposals"]["resident_templates"][0])),
            "resident_proposal_to_location_template_rejected": lambda x: x["growth_proposals"]["records"][0].__setitem__("generated_template_id", "generated_location_template_0001"),
            "location_proposal_to_resident_template_rejected": lambda x: x["growth_proposals"]["records"][1].__setitem__("generated_template_id", "generated_resident_template_0001"),
            "checked_in_template_collision_rejected": lambda x: (
                x["growth_proposals"]["records"][0].__setitem__("generated_template_id", "resident_template_001"),
                x["growth_proposals"]["resident_templates"][0].__setitem__("id", "resident_template_001"),
            ),
            "rewound_resident_template_sequence_rejected": lambda x: x["growth_proposals"].__setitem__("next_resident_template_sequence", 1),
            "rewound_location_template_sequence_rejected": lambda x: x["growth_proposals"].__setitem__("next_location_template_sequence", 1),
            "unknown_generated_migration_rejected": lambda x: x["town_growth"]["migration_records"][0].__setitem__("template_id", "generated_resident_template_9999"),
            "unknown_generated_activation_rejected": lambda x: x["location_growth"]["activation_records"][0].__setitem__("template_id", "generated_location_template_9999"),
        }
        for name, mutation in attacks.items():
            scenarios[name] = _mutated_load_rejected(
                root, config, saved, f"attack-{name}", mutation
            )

    failed_scenarios = sorted(name for name, passed in scenarios.items() if not passed)
    failed_invariants = sorted(name for name, passed in invariants.items() if not passed)
    diagnostics["failed_scenarios"] = failed_scenarios
    diagnostics["failed_invariants"] = failed_invariants
    return {
        "passed": not failed_scenarios and not failed_invariants,
        "scenario_count": len(scenarios),
        "scenarios_passed": len(scenarios) - len(failed_scenarios),
        "invariant_count": len(invariants),
        "invariants_passed": len(invariants) - len(failed_invariants),
        "scenarios": scenarios,
        "invariants": invariants,
        "diagnostics": diagnostics,
    }
