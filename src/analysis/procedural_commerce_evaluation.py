"""Real-engine acceptance of bounded procedural institution commerce."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import json
import random
from pathlib import Path
from tempfile import TemporaryDirectory

from src.analysis.commerce_growth_evaluation import _revenue_funds_later_wage
from src.analysis.growth_audits import conservation_checks
from src.systems.growth_proposals import payload_digest
from src.analysis.procedural_institution_evaluation import (
    StaticProceduralInstitutionProvider, NoCallsProvider, _write_config as _phase3_config,
    _horizon, _engine, _run, _signature as _institution_signature,
    _mutated_load_rejected,
)

HORIZON_DAYS = 140


class StaticProceduralCommerceProvider(StaticProceduralInstitutionProvider):
    provider_kind = "deterministic_procedural_commerce"

    def __init__(self, candidate: object = None) -> None:
        super().__init__()
        self.calls["commerce"] = 0
        self.candidate = {"offer": "community_meals"} if candidate is None else candidate
        self.commerce_contexts: list[dict] = []

    def propose_commerce(self, context: dict) -> object:
        self.calls["commerce"] += 1
        self.commerce_contexts.append(deepcopy(context))
        if isinstance(self.candidate, Exception):
            raise self.candidate
        return self.candidate


def _write_config(root: Path) -> Path:
    path = _phase3_config(root)
    data = json.loads(path.read_text())
    data["procedural_growth"]["policy"].update(
        commerce_proposal_capacity=1, history_limit=5,
        generated_institution_startup_grant=600,
    )
    data["commerce_growth"]["policy"].update(
        commerce_capacity=2, activation_cooldown_days=7,
    )
    path.write_text(json.dumps(data))
    return path


def _signature(engine) -> dict:
    return {
        "institutions": _institution_signature(engine),
        "commerce": engine.commerce_growth.to_dict(),
        "templates": [asdict(item) for item in engine.commerce_growth.templates.values()],
        "materials": engine.materials.to_dict(),
        "economy": engine.economy.to_dict(),
    }


def _observed_horizon(root: Path, config: Path, provider) -> tuple:
    """Observe admission in the real engine without adding economic state."""
    observed = {}
    caller_state = random.getstate()
    random.seed(23)
    try:
        engine = _engine(root, "fresh", config, provider)
        review = engine.review_growth_proposals

        def observed_review(day):
            waiting = engine.growth_proposals.remaining_capacity("commerce")
            if waiting:
                economy_before = deepcopy(engine.economy.to_dict())
                material_before = deepcopy(engine.materials.to_dict())
            record = review(day)
            if record is not None and record.kind == "commerce":
                observed["admission_no_economic_mutation"] = (
                    economy_before == engine.economy.to_dict()
                    and material_before == engine.materials.to_dict()
                )
                authority = dict(
                    day=day, commerce_growth=engine.commerce_growth,
                    institution_growth=engine.institution_growth,
                    location_growth=engine.location_growth, economy=engine.economy,
                    materials=engine.materials, agents=engine.agents,
                    locations=engine.locations, activity_records=engine.activity_records,
                    prior_records=engine.growth_proposals.records[:-1],
                )
                selector = engine.growth_proposals.select_commerce_target
                observed["authoritative_target_ready"] = selector(**authority) is not None
                # Missing real evidence cannot be replaced by an admitted proposal.
                institution = deepcopy(engine.institution_growth)
                institution.formation_records = []
                observed["formation_required"] = selector(**(authority | {"institution_growth": institution})) is None
                economy = deepcopy(engine.economy)
                economy.work_events = []
                observed["ordinary_work_required"] = selector(**(authority | {"economy": economy})) is None
                economy = deepcopy(engine.economy)
                economy.employments.pop(next(item.employment_id for item in engine.institution_growth.formation_records
                                             if item.template_id == record.target_institution_template_id))
                observed["real_employment_required"] = selector(**(authority | {"economy": economy})) is None
                observed["local_use_required"] = selector(**(authority | {"activity_records": []})) is None
                materials = deepcopy(engine.materials)
                materials.exchanges = []
                observed["actual_demand_required"] = selector(**(authority | {"materials": materials})) is None
            return record

        engine.review_growth_proposals = observed_review
        _run(engine, HORIZON_DAYS)
        return engine, observed
    finally:
        random.setstate(caller_state)


def evaluate_procedural_commerce() -> dict:
    scenarios = {}
    with TemporaryDirectory() as directory:
        root = Path(directory)
        config = _write_config(root)
        provider = StaticProceduralCommerceProvider()
        fresh, observations = _observed_horizon(root, config, provider)
        scenarios.update(observations)
        record = next((item for item in fresh.growth_proposals.records
                       if item.kind == "commerce"), None)
        if record is None or record.status != "admitted":
            return {"passed": False, "diagnostics": {
                "records": [asdict(item) for item in fresh.growth_proposals.records],
                "reviews": fresh.commerce_growth.to_dict(),
            }}
        template = fresh.growth_proposals.commerce_templates[record.generated_template_id]
        activation = next((item for item in fresh.commerce_growth.activation_records
                           if item.template_id == template.id), None)
        if activation is None or activation.status != "activated":
            return {"passed": False, "diagnostics": fresh.commerce_growth.to_dict()}
        procurement = [item for item in fresh.materials.exchanges
                       if item.buyer_inventory_id == activation.inventory_id]
        production = [item for item in fresh.materials.production_records
                      if item.recipe_id == activation.recipe_id]
        sales = [item for item in fresh.materials.exchanges
                 if item.seller_id == activation.seller_id]
        procurement_lots = {lot_id for exchange in procurement
                            for lot_id in fresh.materials.lot_ids_moved_by_transfer(exchange.inventory_transfer_id)}
        recipe = fresh.materials.production_recipes[activation.recipe_id]
        seller = fresh.materials.sellers[activation.seller_id]
        scenarios.update({
            "one_admitted_bounded_proposal": provider.calls["commerce"] == 1,
            "exact_target": record.target_institution_template_id == "generated_institution_template_0001"
                and record.target_location_template_id == "generated_location_template_0001",
            "later_ordinary_activation": activation.review_day > record.admission_day,
            "exact_operator": recipe.eligible_actor_ids == (activation.operator_agent_id,)
                and recipe.eligible_employment_ids == (activation.operator_employment_id,),
            "exact_seller": seller.location_id == activation.location_id
                and seller.account_id == activation.institution_account_id,
            "empty_inventory_baseline": fresh.materials.initial_quantities[activation.inventory_id] == {},
            "real_procurement": bool(procurement) and all(item.seller_id == "seller:market_stall" for item in procurement),
            "real_production": bool(production) and all(item.input_lot_ids and item.output_lot_ids for item in production),
            "revenue_funds_later_wage": _revenue_funds_later_wage(fresh, activation),
            "production_consumes_procured_provenance": bool(production)
                and all(set(item.input_lot_ids).issubset(procurement_lots) for item in production),
            "output_lot_provenance": bool(production)
                and all(fresh.materials.lots[lot_id].origin_type == "production"
                        and fresh.materials.lots[lot_id].parent_lot_ids
                        for item in production for lot_id in item.output_lot_ids),
            "sale_payments_reach_account": bool(sales)
                and all(next(tx for tx in fresh.economy.ledger if tx.id == item.monetary_transaction_id).destination_account_id == activation.institution_account_id
                        for item in sales),
            "real_sales_and_revenue": bool(sales) and all(item.seller_account_id == activation.institution_account_id for item in sales),
            "garden_retains_commerce": any(item.template_id == "commerce_template_001" and item.status == "activated" for item in fresh.commerce_growth.activation_records),
            "pavilion_noncommercial": all(item.institution_template_id != "institution_template_002" for item in fresh.commerce_growth.templates.values()),
            "bounded_semantic_context": set(provider.commerce_contexts[0]) == {"target_institution", "target_place", "observed_evidence", "permitted_offers"},
        })
        repeat = _horizon(root, "repeat", config, (HORIZON_DAYS,), StaticProceduralCommerceProvider())
        scenarios["same_seed_signature"] = _signature(fresh) == _signature(repeat)
        for label, split in (("before_proposal", record.proposal_day - 1),
                             ("after_proposal", record.proposal_day),
                             ("after_activation", activation.activation_day)):
            resumed_provider = StaticProceduralCommerceProvider()
            resumed = _horizon(root, label, config, (split, HORIZON_DAYS - split), resumed_provider)
            scenarios[f"resume_{label}"] = _signature(fresh) == _signature(resumed)
            scenarios[f"no_reconstruction_calls_{label}"] = resumed_provider.calls == provider.calls
        # Inspect admission alone with real evidence and compare all economic/material state.
        before = _horizon(root, "admission", config, (record.proposal_day,), StaticProceduralCommerceProvider())
        scenarios["admission_creates_no_material_authority"] = (
            not any(item.template_id == template.id for item in before.commerce_growth.activation_records)
            and not any(item.owner_id == activation.institution_id for item in before.materials.inventories.values())
        )
        before_state = _signature(before)
        scenarios["template_load_without_provider"] = before_state == _signature(_engine(root, "admission", config, NoCallsProvider(), load=True))
        saved = json.loads((root / "fresh.json").read_text())
        def proposal(data):
            return next(item for item in data["growth_proposals"]["records"] if item["kind"] == "commerce")
        def commerce(data):
            return data["growth_proposals"]["commerce_templates"][0]
        def active(data):
            return next(item for item in data["commerce_growth"]["activation_records"] if item["template_id"] == template.id)
        attacks = {
            "payload": lambda data: proposal(data)["canonical_payload"].update(offer="forged"),
            "digest": lambda data: proposal(data).update(canonical_payload_hash="0" * 64),
            "proposal_identity": lambda data: proposal(data).update(id="growth-proposal:9999"),
            "proposal_kind": lambda data: proposal(data).update(kind="institution"),
            "proposal_counter": lambda data: data["growth_proposals"].update(next_proposal_sequence=1),
            "commerce_counter": lambda data: data["growth_proposals"].update(next_commerce_template_sequence=1),
            "target_institution": lambda data: proposal(data).update(target_institution_template_id="generated_institution_template_0002"),
            "target_location": lambda data: proposal(data).update(target_location_template_id="generated_location_template_0002"),
            "garden_binding": lambda data: commerce(data).update(institution_template_id="institution_template_001"),
            "pavilion_binding": lambda data: commerce(data).update(institution_template_id="institution_template_002"),
            "template_price_quantity": lambda data: commerce(data).update(input_quantity=99),
            "template_identity": lambda data: commerce(data).update(id="generated_commerce_template_9999"),
            "missing_template": lambda data: data["growth_proposals"].update(commerce_templates=[]),
            "missing_proposal": lambda data: data["growth_proposals"].update(records=[item for item in data["growth_proposals"]["records"] if item["kind"] != "commerce"]),
            "wrong_formation": lambda data: active(data).update(institution_formation_id=next(item.id for item in fresh.institution_growth.formation_records if item.id != activation.institution_formation_id)),
            "wrong_employment": lambda data: active(data).update(operator_employment_id="employment:forged"),
            "activation_provenance": lambda data: active(data).update(template_id="commerce_template_001"),
        }
        def altered_offer(data):
            row = proposal(data)
            row["canonical_payload"] = {"offer": "arbitrary_goods"}
            row["canonical_payload_hash"] = payload_digest(row["canonical_payload"])

        attacks["offer_with_matching_digest"] = altered_offer
        attacks["fabricated_template"] = lambda data: data["growth_proposals"]["commerce_templates"].append(deepcopy(commerce(data)))
        attacks["missing_all_proposals"] = lambda data: data.pop("growth_proposals")
        def unproven_inventory(data):
            item = deepcopy(next(item for item in data["materials"]["inventories"]
                                 if item.get("commerce_activation_id") == activation.id))
            item.update(id="inventory:institution:forged", commerce_activation_id=None,
                        institution_id=None, quantities={})
            data["materials"]["inventories"].append(item)
            data["materials"]["initial_quantities"][item["id"]] = {}
            data["materials"]["lot_holdings"][item["id"]] = {}

        attacks["unproven_institution_inventory"] = unproven_inventory
        attacks["fabricated_activation"] = lambda data: data["commerce_growth"]["activation_records"].append(deepcopy(active(data)))
        for registry, field, value in (
            ("sellers", "account_id", "account:employer:town_services"),
            ("inventories", "owner_id", "institution:forged"),
            ("production_recipes", "eligible_actor_ids", ["agent_001"]),
            ("purchase_activity_rules", "seller_id", "seller:market_stall"),
            ("sellers", "commerce_activation_id", "commerce-activation:9999"),
        ):
            def mutate(data, registry=registry, field=field, value=value):
                next(item for item in data["materials"][registry]
                     if item.get("commerce_activation_id") == activation.id)[field] = value
            attacks[f"{registry}_{field}"] = mutate
        for registry in ("sellers", "inventories", "production_recipes", "purchase_activity_rules"):
            def fabricate(data, registry=registry):
                item = deepcopy(next(item for item in data["materials"][registry]
                                     if item.get("commerce_activation_id") == activation.id))
                key = "activity_id" if registry == "purchase_activity_rules" else "id"
                item[key] = "fabricated:" + item[key]
                data["materials"][registry].append(item)
            attacks[f"fabricated_{registry}"] = fabricate
        for label, mutate in attacks.items():
            scenarios[f"reject_{label}"] = _mutated_load_rejected(root, config, saved, label, mutate)
        fresh.validate_commerce_authorities()
        invariants = conservation_checks(fresh)
        diagnostics = {"proposal_day": record.proposal_day, "activation_day": activation.activation_day,
                       "procurements": len(procurement), "productions": len(production), "sales": len(sales),
                       "sales_revenue": sum(item.total_price for item in sales), "provider_calls": provider.calls}
    diagnostics["failed_scenarios"] = sorted(name for name, passed in scenarios.items() if not passed)
    diagnostics["failed_invariants"] = sorted(name for name, passed in invariants.items() if not passed)
    return {"scenario_count": len(scenarios), "scenarios_passed": sum(scenarios.values()),
            "invariant_count": len(invariants), "invariants_passed": sum(invariants.values()),
            "passed": all(scenarios.values()) and all(invariants.values()),
            "scenarios": scenarios, "invariants": invariants, "diagnostics": diagnostics}
