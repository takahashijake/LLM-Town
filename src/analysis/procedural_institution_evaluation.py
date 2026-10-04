"""Deterministic V6 Phase 3 procedural-institution acceptance gate."""

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


HORIZON_DAYS = 100


class StaticProceduralInstitutionProvider:
    provider_kind = "deterministic_procedural_institution"

    def __init__(self, institution: object | None = None) -> None:
        self.calls = {
            "resident": 0, "location": 0, "event": 0, "institution": 0,
        }
        self.institution = institution or {
            "name": "Story Grove Commons",
            "role_title": "story grove coordinator",
            "work_activity_name": "Coordinate Story Grove programs",
        }
        self.institution_contexts: list[dict] = []

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

    def propose_event(self, context: dict) -> dict:
        self.calls["event"] += 1
        return {
            "name": "Story Exchange",
            "description": "Residents share short stories and local knowledge.",
            "tags": ["community", "knowledge", "social"],
            "required_affinities": ["community", "knowledge"],
        }

    def propose_institution(self, context: dict) -> object:
        self.calls["institution"] += 1
        self.institution_contexts.append(deepcopy(context))
        if isinstance(self.institution, Exception):
            raise self.institution
        return self.institution


class NoCallsProvider:
    provider_kind = "no_replay"

    def __getattr__(self, name):
        if name.startswith("propose_"):
            def fail(_context):
                raise AssertionError("provider called after bounded exhaustion")
            return fail
        raise AttributeError(name)


def _write_config(root: Path) -> Path:
    data = json.loads(Path("data/town_growth.json").read_text(encoding="utf-8"))
    data["policy"]["resident_capacity"] = 7
    data["location_growth"]["policy"]["location_capacity"] = 7
    institution_policy = data["institution_growth"]["policy"]
    institution_policy.update({
        "institution_capacity": 3,
        "earliest_formation_day": 1,
        "review_interval_days": 1,
        "formation_cooldown_days": 0,
    })
    data["procedural_growth"] = {"policy": {
        "enabled": True,
        "earliest_proposal_day": 1,
        "review_interval_days": 1,
        "proposal_cooldown_days": 0,
        "resident_proposal_capacity": 1,
        "location_proposal_capacity": 1,
        "event_proposal_capacity": 1,
        "event_templates_per_location": 1,
        "institution_proposal_capacity": 1,
        "institution_templates_per_location": 1,
        "generated_institution_wage": 18,
        "generated_institution_startup_grant": 240,
        "generated_institution_funding_source_account_id": (
            "account:employer:town_services"
        ),
        "history_limit": 4,
    }}
    path = root / "town_growth_v6_phase3.json"
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
    generated = sorted(engine.growth_proposals.institution_templates.values(),
                       key=lambda item: item.id)
    generated_ids = {item.id for item in generated}
    formations = [
        item for item in engine.institution_growth.formation_records
        if item.template_id in generated_ids
    ]
    employments = [
        item for item in engine.economy.employments.values()
        if item.formation_id in {formation.id for formation in formations}
    ]
    return {
        "proposals": [
            (item.id, item.kind, item.status, item.canonical_payload_hash,
             item.generated_template_id, item.target_location_template_id)
            for item in engine.growth_proposals.records
        ],
        "templates": [
            (item.id, item.institution_key, item.name,
             item.location_template_id,
             item.relevant_dynamic_event_template_ids,
             item.role.role_template_id, item.role.work_activity_id,
             item.role.wage, item.startup_grant,
             item.startup_funding_source_account_id)
            for item in generated
        ],
        "formations": [
            (item.id, item.template_id, item.employee_agent_id, item.status,
             item.activation_day, item.startup_transaction_id)
            for item in formations
        ],
        "employments": [
            (item.id, item.agent_id, item.title, item.wage,
             item.qualifying_activity_ids, item.activity_locations,
             item.start_day, item.formation_id)
            for item in employments
        ],
        "balances": sorted(
            (key, value.balance) for key, value in engine.economy.accounts.items()
        ),
        "ledger": [
            (item.id, item.event_key, item.amount)
            for item in engine.economy.ledger
        ],
        "generated_work": [
            (item.get("event_key"), item.get("agent_id"),
             item.get("activity_id"), item.get("location"))
            for item in engine.activity_records
            if item.get("activity_id", "").startswith(
                "generated_work_activity_"
            )
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


def evaluate_procedural_institutions() -> dict:
    scenarios: dict[str, bool] = {}
    invariants: dict[str, bool] = {}
    diagnostics: dict[str, object] = {"horizon_days": HORIZON_DAYS}
    with TemporaryDirectory() as directory:
        root = Path(directory)
        config = _write_config(root)
        provider = StaticProceduralInstitutionProvider()
        fresh = _horizon(root, "fresh", config, (HORIZON_DAYS,), provider)
        repeat = _horizon(
            root, "repeat", config, (HORIZON_DAYS,),
            StaticProceduralInstitutionProvider(),
        )
        resumed_provider = StaticProceduralInstitutionProvider()
        resumed = _horizon(
            root, "resumed", config, (52, 48), resumed_provider,
        )
        resumed_after_formation = _horizon(
            root, "resumed-after-formation", config, (60, 40),
            StaticProceduralInstitutionProvider(),
        )
        institution_record = next(
            item for item in fresh.growth_proposals.records
            if item.kind == "institution"
        )
        template = fresh.growth_proposals.institution_templates[
            institution_record.generated_template_id
        ]
        formation = next(
            item for item in fresh.institution_growth.formation_records
            if item.template_id == template.id
        )
        employment = fresh.economy.employments[formation.employment_id]
        startup = next(
            item for item in fresh.economy.ledger
            if item.id == formation.startup_transaction_id
        )
        work = [
            item for item in fresh.activity_records
            if item.get("agent_id") == formation.employee_agent_id
            and item.get("activity_id") == template.role.work_activity_id
        ]
        occurrences = [
            item for item in fresh.event_ecology.occurrence_history
            if item.template_id
            in template.relevant_dynamic_event_template_ids
            and item.location_id == formation.location_id
            and item.day <= institution_record.proposal_day
        ]
        diagnostics.update({
            "provider_calls": provider.calls,
            "institution_context": provider.institution_contexts[-1],
            "signature": _signature(fresh),
        })
        scenarios.update({
            "institution_candidate_admitted": (
                institution_record.status == "admitted"
                and template.id == "generated_institution_template_0001"
            ),
            "location_activated_before_admission": any(
                item.status == "activated"
                and item.template_id == template.location_template_id
                and item.activation_day < institution_record.admission_day
                for item in fresh.location_growth.activation_records
            ),
            "exact_generated_event_provenance": (
                bool(occurrences)
                and {item.template_id for item in occurrences}
                == set(template.relevant_dynamic_event_template_ids)
                and all(item.day <= institution_record.proposal_day
                        for item in occurrences)
            ),
            "admission_does_not_form_same_day": (
                formation.review_day > institution_record.admission_day
            ),
            "admission_transfers_no_money": (
                startup.day > institution_record.admission_day
            ),
            "ordinary_review_selects_employee": (
                formation.status == "activated"
                and formation.employee_agent_id == employment.agent_id
            ),
            "account_and_employment_match": (
                employment.employer_account_id == formation.employer_account_id
                and employment.qualifying_activity_ids
                == (template.role.work_activity_id,)
                and employment.activity_locations
                == ((template.role.work_activity_id, formation.location_id),)
            ),
            "startup_is_conserved_transfer": (
                startup.source_account_id
                == template.startup_funding_source_account_id
                and startup.destination_account_id
                == formation.employer_account_id
                and startup.amount == template.startup_grant
            ),
            "ordinary_work_starts_after_employment": (
                bool(work)
                and min(item["day"] for item in work) >= employment.start_day
                and all(item["location"] == formation.location_id for item in work)
            ),
            "ordinary_wage_paid": any(
                item.event_key.startswith(f"wage:{employment.id}:")
                and item.amount == template.role.wage
                for item in fresh.economy.ledger
            ),
            "no_generated_commerce": all(
                item.template_id == "commerce_template_001"
                for item in fresh.commerce_growth.activation_records
            ),
            "resume_and_repeat_match": (
                _signature(fresh) == _signature(repeat) == _signature(resumed)
                == _signature(resumed_after_formation)
            ),
            "resume_does_not_reconstruct_proposal": (
                resumed_provider.calls == {
                    "resident": 1, "location": 1, "event": 1,
                    "institution": 1,
                }
            ),
            "capacity_stops_provider": provider.calls == {
                "resident": 1, "location": 1, "event": 1,
                "institution": 1,
            },
            "provider_context_withholds_authority_ids": all(
                forbidden not in json.dumps(provider.institution_contexts[-1])
                for forbidden in (
                    "location_template_id", "event_template_id", "employee",
                    "wage", "funding_source_account_id",
                )
            ),
        })
        invariants.update({
            "proposal_bindings_valid": True,
            "institution_authority_valid": True,
            "currency_conserved": fresh.economy.conservation_holds(),
            "ledger_reconstructs": fresh.economy.ledger_reconstructs_balances(),
        })
        try:
            fresh.growth_proposals.validate_bindings(
                fresh.town_growth, fresh.location_growth, fresh.event_ecology,
                fresh.institution_growth, locations=fresh.locations,
                activity_records=fresh.activity_records,
            )
            fresh.validate_institution_authorities()
        except (KeyError, TypeError, ValueError):
            invariants["proposal_bindings_valid"] = False
            invariants["institution_authority_valid"] = False

        saved = json.loads((root / "fresh.json").read_text(encoding="utf-8"))
        template_index = next(
            index for index, item in enumerate(
                saved["growth_proposals"]["institution_templates"]
            ) if item["id"] == template.id
        )
        attacks = {
            "tampered_institution_name_rejected": lambda data: data[
                "growth_proposals"
            ]["institution_templates"][template_index].__setitem__("name", "Fake"),
            "tampered_event_allowlist_rejected": lambda data: data[
                "growth_proposals"
            ]["institution_templates"][template_index].__setitem__(
                "relevant_dynamic_event_template_ids",
                ["garden_learning_circle"],
            ),
            "tampered_wage_rejected": lambda data: data["growth_proposals"][
                "institution_templates"
            ][template_index]["role"].__setitem__("wage", 999),
            "removed_startup_rejected": lambda data: data["economy"][
                "ledger"
            ].__setitem__(slice(None), [
                item for item in data["economy"]["ledger"]
                if item["id"] != formation.startup_transaction_id
            ]),
            "swapped_employee_rejected": lambda data: next(
                item for item in data["institution_growth"]["formation_records"]
                if item["id"] == formation.id
            ).__setitem__("employee_agent_id", "agent_001"),
        }
        for name, mutate in attacks.items():
            scenarios[name] = _mutated_load_rejected(
                root, config, saved, name, mutate
            )

    failed_scenarios = sorted(name for name, value in scenarios.items() if not value)
    failed_invariants = sorted(name for name, value in invariants.items() if not value)
    diagnostics["failed_scenarios"] = failed_scenarios
    diagnostics["failed_invariants"] = failed_invariants
    return {
        "passed": not failed_scenarios and not failed_invariants,
        "scenario_count": len(scenarios),
        "scenarios_passed": len(scenarios) - len(failed_scenarios),
        "scenarios": scenarios,
        "invariant_count": len(invariants),
        "invariants_passed": len(invariants) - len(failed_invariants),
        "invariants": invariants,
        "diagnostics": diagnostics,
    }
