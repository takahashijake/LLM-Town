"""Deterministic V6 Phase 2 generated-event acceptance gate."""

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


HORIZON_DAYS = 84


class StaticProceduralEventProvider:
    provider_kind = "deterministic_procedural_event"

    def __init__(self, event: object | None = None) -> None:
        self.calls = {"resident": 0, "location": 0, "event": 0}
        self.event = event or {
            "name": "Story Exchange",
            "description": "Residents share short stories and local knowledge.",
            "tags": ["community", "knowledge", "social"],
            "required_affinities": ["community", "knowledge"],
        }
        self.event_contexts: list[dict] = []

    def propose_resident(self, context: dict) -> dict:
        self.calls["resident"] += 1
        return {
            "name": "Mira", "personality": "curious and community-minded",
            "goals": ["learn local customs", "build close friendships"],
        }

    def propose_location(self, context: dict) -> dict:
        self.calls["location"] += 1
        return {
            "name": "Story Grove",
            "description": "A small public grove for conversation and reading.",
            "affinities": ["social", "knowledge", "community"],
        }

    def propose_event(self, context: dict) -> object:
        self.calls["event"] += 1
        self.event_contexts.append(deepcopy(context))
        if isinstance(self.event, Exception):
            raise self.event
        return self.event


class NoCallsProvider:
    provider_kind = "no_replay"

    def __getattr__(self, name):
        if name.startswith("propose_"):
            def fail(_context):
                raise AssertionError("provider was called after capacity exhaustion")
            return fail
        raise AttributeError(name)


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
        "event_proposal_capacity": 1,
        "event_templates_per_location": 1,
        "history_limit": 3,
    }}
    path = root / "town_growth_v6_phase2.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _engine(root: Path, name: str, config: Path, provider, *, load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs", simulation_seed=23,
        town_growth_path=config, growth_proposal_provider=provider,
    )


def _run(engine, days: int) -> None:
    with redirect_stdout(StringIO()):
        engine.run(days, [8])


def _horizon(root: Path, name: str, config: Path, splits, provider):
    caller_state = random.getstate()
    random.seed(23)
    try:
        engine = _engine(root, name, config, provider)
        for index, days in enumerate(splits):
            if index:
                engine = _engine(root, name, config, provider, load=True)
            _run(engine, days)
        return engine
    finally:
        random.setstate(caller_state)


def _signature(engine) -> dict:
    return {
        "proposals": [
            (item.id, item.kind, item.status, item.canonical_payload_hash,
             item.generated_template_id, item.target_location_template_id)
            for item in engine.growth_proposals.records
        ],
        "event_templates": [
            item.to_dict() if hasattr(item, "to_dict") else {
                "id": item.id, "name": item.name,
                "location_template_id": item.location_template_id,
                "tags": list(item.tags),
            }
            for item in sorted(engine.growth_proposals.event_templates.values(),
                               key=lambda value: value.id)
        ],
        "occurrences": [
            (item.occurrence_id, item.template_id, item.location_id, item.day)
            for item in engine.event_ecology.occurrence_history
        ],
        "daily_events": [
            (item["day"], item["template_id"], item["location_id"],
             item["source_kind"])
            for item in engine.daily_event_history
        ],
    }


def _mutated_load_rejected(root, config, saved, name, mutate) -> bool:
    data = deepcopy(saved)
    mutate(data)
    (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    try:
        _engine(root, name, config, NoCallsProvider(), load=True)
    except (KeyError, TypeError, ValueError):
        return True
    return False


def evaluate_procedural_events() -> dict:
    scenarios: dict[str, bool] = {}
    invariants: dict[str, bool] = {}
    diagnostics: dict[str, object] = {"horizon_days": HORIZON_DAYS}
    with TemporaryDirectory() as directory:
        root = Path(directory)
        config = _write_config(root)
        fresh_provider = StaticProceduralEventProvider()
        fresh = _horizon(root, "fresh", config, (HORIZON_DAYS,), fresh_provider)
        repeat = _horizon(
            root, "repeat", config, (HORIZON_DAYS,),
            StaticProceduralEventProvider(),
        )
        resumed_provider = StaticProceduralEventProvider()
        resumed = _horizon(
            root, "resumed", config, (2, 38, 44), resumed_provider,
        )
        event_record = next(
            item for item in fresh.growth_proposals.records if item.kind == "event"
        )
        event_template = fresh.growth_proposals.event_templates[
            event_record.generated_template_id
        ]
        activation = next(
            item for item in fresh.location_growth.activation_records
            if item.template_id == event_record.target_location_template_id
        )
        occurrence = next(
            (item for item in fresh.event_ecology.occurrence_history
             if item.template_id == event_template.id), None
        )
        diagnostics["signature"] = _signature(fresh)
        diagnostics["provider_calls"] = fresh_provider.calls
        diagnostics["event_context"] = fresh_provider.event_contexts[-1]
        scenarios.update({
            "generated_location_activated_before_event_admission": (
                activation.status == "activated"
                and activation.activation_day < event_record.admission_day
            ),
            "event_candidate_admitted_and_bound": (
                event_record.status == "admitted"
                and event_template.id == "generated_event_template_0001"
                and event_template.location_template_id
                == event_record.target_location_template_id
            ),
            "admission_does_not_create_occurrence": (
                occurrence is not None and occurrence.day > event_record.admission_day
            ),
            "ordinary_event_ecology_creates_occurrence": (
                occurrence is not None
                and occurrence.location_id == activation.location_id
            ),
            "ordinary_daily_event_memory_records_generated_occurrence": any(
                memory.type == "daily_event"
                and event_template.id in memory.tags
                and memory.location == activation.location_id
                for agent in fresh.agents
                for memory in agent.memory + agent.memory_archive
            ),
            "uninterrupted_resume_repeat_match": (
                _signature(fresh) == _signature(repeat) == _signature(resumed)
            ),
            "capacity_stops_provider": fresh_provider.calls == {
                "resident": 1, "location": 1, "event": 1,
            },
            "bounded_context_has_no_private_state": all(
                key not in json.dumps(fresh_provider.event_contexts[-1])
                for key in ("balance", "inventory", "memory", "relationship", "legal")
            ),
            "configured_institution_allowlists_exclude_generated_event": all(
                event_template.id not in item.relevant_dynamic_event_template_ids
                for item in fresh.institution_growth.templates.values()
            ),
        })
        fresh.growth_proposals.validate_bindings(
            fresh.town_growth, fresh.location_growth, fresh.event_ecology,
            locations=fresh.locations, activity_records=fresh.activity_records,
        )
        invariants.update({
            "proposal_bindings_valid": True,
            "event_ecology_valid": all(fresh.event_ecology.validate(
                locations=fresh.locations, location_growth=fresh.location_growth,
                activity_records=fresh.activity_records,
            ).values()),
            "institution_authority_valid": all(fresh.institution_growth.validate(
                agents=fresh.agents, locations=fresh.locations,
                location_growth=fresh.location_growth,
                event_ecology=fresh.event_ecology, economy=fresh.economy,
            ).values()),
        })
        saved = json.loads((root / "fresh.json").read_text(encoding="utf-8"))
        event_index = next(
            index for index, item in enumerate(saved["growth_proposals"]["records"])
            if item["kind"] == "event"
        )
        attacks = {
            "tampered_event_payload_rejected": lambda x: x["growth_proposals"]["records"][event_index]["canonical_payload"].__setitem__("name", "Forgery"),
            "tampered_event_hash_rejected": lambda x: x["growth_proposals"]["records"][event_index].__setitem__("canonical_payload_hash", "0" * 64),
            "tampered_event_template_rejected": lambda x: x["growth_proposals"]["event_templates"][0].__setitem__("description", "Forgery"),
            "tampered_target_binding_rejected": lambda x: x["growth_proposals"]["event_templates"][0].__setitem__("location_template_id", "location_template_001"),
            "rewound_event_sequence_rejected": lambda x: x["growth_proposals"].__setitem__("next_event_template_sequence", 1),
            "deleted_event_authority_rejected": lambda x: x["growth_proposals"]["event_templates"].clear(),
            "unknown_occurrence_authority_rejected": lambda x: x["event_ecology"]["occurrence_history"][0].__setitem__("template_id", "generated_event_template_9999"),
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
        "scenarios": scenarios, "invariants": invariants,
        "diagnostics": diagnostics,
    }
