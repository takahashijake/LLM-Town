"""Deterministic V5 Phase 5 institutional-commerce acceptance gate."""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory

from src.behavior.activity import Activity
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.economy import EconomySystem
from src.systems.materials import MaterialError, MaterialSystem


HORIZON_DAYS = 240


def _engine(root: Path, name: str, *, load: bool = False) -> SimulationEngine:
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs", simulation_seed=11,
    )


def _run(engine: SimulationEngine, days: int) -> None:
    with redirect_stdout(StringIO()):
        engine.run(days, [8])


def _horizon(root: Path, name: str, splits: tuple[int, ...]) -> SimulationEngine:
    state = random.getstate()
    random.seed(11)
    try:
        engine = _engine(root, name)
        for index, days in enumerate(splits):
            if index:
                engine = _engine(root, name, load=True)
            _run(engine, days)
        return engine
    finally:
        random.setstate(state)


def _signature(engine: SimulationEngine) -> dict:
    active = [item for item in engine.commerce_growth.activation_records
              if item.status == "activated"]
    ids = {item.id for item in active}
    return {
        "migration_ids": [item.id for item in engine.town_growth.migration_records],
        "location_ids": [item.id for item in engine.location_growth.activation_records],
        "institution_ids": [item.id for item in engine.institution_growth.formation_records],
        "commerce_ids": [item.id for item in active],
        "activation_days": [item.activation_day for item in active],
        "inventory_ids": sorted(item.id for item in engine.materials.inventories.values()
                                if item.commerce_activation_id in ids),
        "seller_ids": sorted(item.id for item in engine.materials.sellers.values()
                             if item.commerce_activation_id in ids),
        "recipe_ids": sorted(item.id for item in engine.materials.production_recipes.values()
                             if item.commerce_activation_id in ids),
        "purchase_activity_ids": sorted(
            item.activity_id for item in engine.materials.purchase_activity_rules.values()
            if item.commerce_activation_id in ids
        ),
        "commerce_exchange_keys": [item.event_key for item in engine.materials.exchanges
                                   if item.seller_id.startswith("seller:institution:")
                                   or item.buyer_inventory_id.startswith(
                                       "inventory:institution:"
                                   )],
        "commerce_production_keys": [item.event_key
                                     for item in engine.materials.production_records
                                     if item.recipe_id.startswith("recipe:institution:")],
        "institution_transactions": [
            (item.event_key, item.transaction_type, item.source_account_id,
             item.destination_account_id, item.amount)
            for item in engine.economy.ledger
            if item.source_account_id.startswith("account:institution:")
            or item.destination_account_id.startswith("account:institution:")
        ],
        "balances": sorted((key, value.balance)
                           for key, value in engine.economy.accounts.items()),
        "dynamic_inventory_quantities": sorted(
            (item.id, item.quantities) for item in engine.materials.inventories.values()
            if item.commerce_activation_id in ids
        ),
        "commerce_memory_ids": sorted(
            memory.id for agent in engine.agents
            for memory in agent.memory + agent.memory_archive
            if memory.source_system == "commerce_growth"
        ),
        "review_history_size": len(engine.commerce_growth.review_history),
    }


def _mutated_load_rejected(root: Path, saved: dict, name: str, mutate) -> bool:
    data = deepcopy(saved)
    mutate(data)
    (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    try:
        _engine(root, name, load=True)
    except (KeyError, TypeError, ValueError):
        return True
    return False


def _forge_commerce_memory(data: dict) -> None:
    agent = data["agents"][0]
    source = deepcopy((agent.get("memory") or agent.get("memory_archive"))[0])
    source.update({
        "id": "memory:agent_001:commerce_growth:forged:institution_commerce_opened",
        "source_system": "commerce_growth", "source_id": "forged",
        "event_type": "institution_commerce_opened", "causal": True,
        "owner_id": "agent_001", "knowledge_basis": "public_event",
    })
    agent.setdefault("memory", []).append(source)


def _revenue_funds_later_wage(engine: SimulationEngine, record) -> bool:
    transactions = sorted(
        engine.economy.ledger,
        key=lambda item: (item.day, -1 if item.hour is None else item.hour, item.id),
    )
    actual = counterfactual = engine.economy.initial_balances[
        record.institution_account_id
    ]
    saw_revenue = False
    for transaction in transactions:
        incoming = transaction.destination_account_id == record.institution_account_id
        outgoing = transaction.source_account_id == record.institution_account_id
        if not incoming and not outgoing:
            continue
        if (transaction.day >= record.activation_day
                and transaction.transaction_type == "purchase" and incoming):
            actual += transaction.amount
            saw_revenue = True
            continue
        delta = transaction.amount if incoming else -transaction.amount
        if (transaction.day >= record.activation_day
                and transaction.transaction_type == "wage"
                and saw_revenue and actual >= transaction.amount
                and counterfactual < transaction.amount):
            return True
        actual += delta
        counterfactual += delta
    return False


def evaluate_commerce_growth() -> dict:
    scenarios: dict[str, bool] = {}
    invariants: dict[str, bool] = {}
    diagnostics: dict[str, object] = {"horizon_days": HORIZON_DAYS}
    with TemporaryDirectory() as directory:
        root = Path(directory)
        fresh = _horizon(root, "fresh", (HORIZON_DAYS,))
        resumed = _horizon(root, "resumed", (60, 40, 140))
        repeated = _horizon(root, "repeated", (HORIZON_DAYS,))
        signature = _signature(fresh)
        diagnostics["long_horizon_signature"] = signature
        active = [item for item in fresh.commerce_growth.activation_records
                  if item.status == "activated"]
        record = active[0]
        template = fresh.commerce_growth.template(record.template_id)
        inventory = fresh.materials.get_inventory(record.inventory_id)
        seller = fresh.materials.sellers[record.seller_id]
        recipe = fresh.materials.production_recipes[record.recipe_id]
        rule = fresh.materials.purchase_activity_rules[record.purchase_activity_id]
        formation = next(item for item in fresh.institution_growth.formation_records
                         if item.id == record.institution_formation_id)
        procurements = [item for item in fresh.materials.exchanges
                        if item.buyer_inventory_id == record.inventory_id
                        and item.seller_id == record.upstream_seller_id]
        sales = [item for item in fresh.materials.exchanges
                 if item.seller_id == record.seller_id]
        productions = [item for item in fresh.materials.production_records
                       if item.recipe_id == record.recipe_id]
        output_lots = [fresh.materials.lots[lot_id]
                       for item in productions for lot_id in item.output_lot_ids]
        procurement_lots = {
            lot_id for item in procurements
            for lot_id in fresh.materials.lot_ids_moved_by_transfer(
                item.inventory_transfer_id
            )
        }
        sale_transactions = {
            item.monetary_transaction_id: item for item in sales
        }

        scenarios.update({
            "one_configured_commerce_entity_activates": len(active) == 1
            and record.id == "commerce-activation:0001",
            "institution_precedes_commerce": formation.activation_day
            < record.activation_day,
            "exact_phase4_authority_is_bound": (
                record.institution_id == formation.institution_id
                and record.operator_agent_id == formation.employee_agent_id
                and record.operator_employment_id == formation.employment_id
                and record.institution_account_id == formation.employer_account_id
            ),
            "one_empty_baseline_institution_inventory": (
                inventory.owner_type == "institution"
                and inventory.owner_id == record.institution_id
                and fresh.materials.initial_quantities[record.inventory_id] == {}
            ),
            "one_exact_garden_seller": seller.location_id == "community_garden"
            and seller.inventory_id == record.inventory_id,
            "one_bounded_recipe": (
                recipe.inputs == (("meal_ingredients", 2),)
                and recipe.outputs == (("prepared_meal", 4),)
                and recipe.eligible_actor_ids == (record.operator_agent_id,)
                and recipe.eligible_employment_ids == (record.operator_employment_id,)
            ),
            "one_exact_resident_purchase_route": (
                rule.seller_id == record.seller_id
                and rule.good_id == "prepared_meal"
            ),
            "activation_mints_no_initial_stock": fresh.materials.initial_quantities[
                record.inventory_id
            ] == {},
            "procurement_uses_authoritative_exchange": bool(procurements),
            "procurement_pays_upstream_seller": all(
                item.seller_account_id
                == fresh.materials.sellers[record.upstream_seller_id].account_id
                for item in procurements
            ),
            "procurement_moves_existing_lots": bool(procurement_lots)
            and all(fresh.materials.lots[item].origin_type == "initial_configuration"
                    for item in procurement_lots),
            "production_consumes_procured_lots": bool(productions)
            and all(set(item.input_lot_ids).issubset(procurement_lots)
                    for item in productions),
            "production_creates_traceable_output_lots": bool(output_lots)
            and all(item.origin_type == "production" and item.parent_lot_ids
                    for item in output_lots),
            "ordinary_residents_buy_garden_meals": bool(sales)
            and all(fresh.materials.get_inventory(item.buyer_inventory_id).owner_type
                    == "agent" for item in sales),
            "sales_transfer_money_to_institution": bool(sale_transactions)
            and all(
                next(tx for tx in fresh.economy.ledger if tx.id == transaction_id
                     ).destination_account_id == record.institution_account_id
                for transaction_id in sale_transactions
            ),
            "sales_transfer_goods_to_residents": all(
                item.inventory_transfer_id in {
                    transfer.id for transfer in fresh.materials.inventory_transfers
                    if transfer.destination_inventory_id == item.buyer_inventory_id
                } for item in sales
            ),
            "commerce_revenue_funds_subsequent_wage": _revenue_funds_later_wage(
                fresh, record
            ),
            "fresh_save_resume_match": signature == _signature(resumed),
            "same_seed_runs_match": signature == _signature(repeated),
            "finite_capacity_stabilizes": len(
                fresh.commerce_growth.activation_records
            ) == 1 and len(fresh.commerce_growth.review_history)
            <= fresh.commerce_growth.policy.history_limit,
            "no_good_is_dynamically_invented": set(fresh.materials.goods) == {
                "meal_ingredients", "prepared_meal", "reference_book",
                "household_supplies", "trade_materials",
            },
        })

        employee = next(item for item in fresh.agents
                        if item.id == record.operator_agent_id)
        wrong_location = Activity(
            template.production_activity_id, "Forged", "market", "attack",
            ["work", "production"],
        )
        before_production = len(fresh.materials.production_records)
        scenarios["wrong_location_production_fails"] = (
            fresh.materials.process_activity(
                employee, wrong_location, day=241, hour=8
            ) is None
            and len(fresh.materials.production_records) == before_production
        )
        wrong_actor = fresh.agents[0]
        right_location = Activity(
            template.production_activity_id, "Forged", record.location_id, "attack",
            ["work", "production"],
        )
        scenarios["wrong_operator_production_fails"] = fresh.materials.process_activity(
            wrong_actor, right_location, day=241, hour=8
        ) is None
        buyer = fresh.agents[0]
        wrong_purchase = Activity(
            record.purchase_activity_id, "Forged", "market", "attack", ["purchase"],
        )
        before_exchanges = len(fresh.materials.exchanges)
        scenarios["wrong_location_purchase_fails"] = (
            fresh.materials.process_activity(
                buyer, wrong_purchase, day=241, hour=8
            ) is None and len(fresh.materials.exchanges) == before_exchanges
        )
        try:
            fresh.materials.purchase(
                fresh.materials.inventory_for_agent(buyer.id).id,
                fresh.economy.account_for_agent(buyer.id).id,
                "seller:forged", "prepared_meal", 1, day=241, hour=8,
                event_key="attack:forged-seller",
            )
        except MaterialError as error:
            scenarios["forged_seller_fails"] = error.code == "unknown_seller"
        try:
            fresh.materials.produce(
                "recipe:forged", actor_id=record.operator_agent_id,
                employment_id=record.operator_employment_id,
                inventory_id=record.inventory_id, day=241, hour=8,
                activity_id=template.production_activity_id,
                location_id=record.location_id, event_key="attack:forged-recipe",
            )
        except MaterialError as error:
            scenarios["forged_recipe_fails"] = error.code == "unknown_recipe"
        existing = procurements[0]
        try:
            fresh.materials.purchase(
                existing.buyer_inventory_id, existing.buyer_account_id,
                existing.seller_id, existing.good_id, existing.quantity,
                day=existing.day, hour=existing.hour, event_key=existing.event_key,
            )
        except MaterialError as error:
            scenarios["duplicate_procurement_fails"] = error.code == "duplicate_event"
        stock_economy = EconomySystem.from_dict(deepcopy(fresh.economy.to_dict()))
        stock_materials = MaterialSystem.from_dict(
            deepcopy(fresh.materials.to_dict()), economy=stock_economy,
        )
        remaining = stock_materials.quantity(record.inventory_id, template.output_good_id)
        if remaining:
            stock_materials.transfer_good(
                record.inventory_id,
                stock_materials.inventory_for_agent(buyer.id).id,
                template.output_good_id, remaining, day=241, hour=None,
                reason="evaluation stock isolation", authorization_type="evaluation",
                authorization_id="evaluation:empty-seller",
                event_key="evaluation:empty-seller",
            )
        try:
            stock_materials.purchase(
                stock_materials.inventory_for_agent(buyer.id).id,
                stock_economy.account_for_agent(buyer.id).id,
                record.seller_id, template.output_good_id, 1,
                day=241, hour=8, event_key="attack:insufficient-stock",
            )
        except MaterialError as error:
            scenarios["insufficient_stock_fails"] = error.code == "insufficient_stock"
        attack_economy = EconomySystem.from_dict(deepcopy(fresh.economy.to_dict()))
        poor_account = attack_economy.account_for_agent(buyer.id)
        if poor_account.balance:
            attack_economy.transfer(
                poor_account.id, "account:employer:town_services",
                poor_account.balance, day=241, hour=None,
                transaction_type="attack_setup", reason="evaluation funds isolation",
                event_key="evaluation:drain-buyer",
            )
        attack_materials = MaterialSystem.from_dict(
            deepcopy(fresh.materials.to_dict()), economy=attack_economy,
        )
        try:
            attack_materials.purchase(
                attack_materials.inventory_for_agent(buyer.id).id,
                poor_account.id, record.seller_id, template.output_good_id, 1,
                day=241, hour=8, event_key="attack:insufficient-funds",
            )
        except MaterialError as error:
            scenarios["insufficient_buyer_funds_fail"] = error.code == "insufficient_funds"
        try:
            attack_materials.purchase(
                "inventory:institution:forged", poor_account.id,
                record.seller_id, template.output_good_id, 1,
                day=241, hour=8, event_key="attack:forged-inventory",
            )
        except MaterialError as error:
            scenarios["forged_buyer_inventory_fails"] = (
                error.code == "unknown_buyer_inventory"
            )
        production = productions[0]
        try:
            fresh.materials.produce(
                record.recipe_id, actor_id=record.operator_agent_id,
                employment_id=record.operator_employment_id,
                inventory_id=record.inventory_id, day=production.day,
                hour=production.hour, activity_id=template.production_activity_id,
                location_id=record.location_id, event_key=production.event_key,
            )
        except MaterialError as error:
            scenarios["duplicate_production_fails"] = error.code == "duplicate_event"
        sale = sales[0]
        try:
            fresh.materials.purchase(
                sale.buyer_inventory_id, sale.buyer_account_id, sale.seller_id,
                sale.good_id, sale.quantity, day=sale.day, hour=sale.hour,
                event_key=sale.event_key,
            )
        except MaterialError as error:
            scenarios["duplicate_sale_fails"] = error.code == "duplicate_event"

        fresh.state.save(fresh, HORIZON_DAYS, 8, day_complete=True)
        saved = json.loads((root / "fresh.json").read_text(encoding="utf-8"))
        mutations = {
            "unknown_commerce_schema_fails": lambda data: data[
                "commerce_growth"
            ].update(schema_version=999),
            "wrong_institution_binding_fails": lambda data: data[
                "commerce_growth"
            ]["activation_records"][0].update(institution_id="institution:forged"),
            "forged_inventory_owner_fails": lambda data: next(
                item for item in data["materials"]["inventories"]
                if item.get("commerce_activation_id")
            ).update(owner_id="institution:forged"),
            "fabricated_initial_stock_fails": lambda data: data[
                "materials"
            ]["initial_quantities"][record.inventory_id].update(prepared_meal=4),
            "forged_seller_inventory_fails": lambda data: next(
                item for item in data["materials"]["sellers"]
                if item.get("commerce_activation_id")
            ).update(inventory_id="inventory:business:market_stall"),
            "inactive_dynamic_seller_fails": lambda data: next(
                item for item in data["materials"]["sellers"]
                if item.get("commerce_activation_id")
            ).update(active=False),
            "forged_recipe_operator_fails": lambda data: next(
                item for item in data["materials"]["production_recipes"]
                if item.get("commerce_activation_id")
            ).update(eligible_actor_ids=["agent_001"]),
            "forged_purchase_rule_fails": lambda data: next(
                item for item in data["materials"]["purchase_activity_rules"]
                if item.get("commerce_activation_id")
            ).update(seller_id="seller:forged"),
            "orphan_material_authority_fails": lambda data: data.pop(
                "commerce_growth"
            ),
            "forged_phase5_memory_fails": _forge_commerce_memory,
            "forged_good_definition_fails": lambda data: data[
                "materials"
            ]["goods"].append({
                "id": "model_invented_good", "name": "invented",
                "category": "forged", "unit_price": 1,
            }),
            "malformed_replay_state_fails": lambda data: data[
                "commerce_growth"
            ]["processed_event_keys"].append("commerce-review:day:999"),
        }
        for index, (name, mutate) in enumerate(mutations.items()):
            scenarios[name] = _mutated_load_rejected(
                root, saved, f"mutation-{index}", mutate,
            )

        # Existing static market purchase and production remain executable.
        static = _engine(root, "static-regression")
        merchant = next(item for item in static.agents if item.id == "agent_004")
        buyer = static.agents[0]
        buy = Activity("buy_meal", "Buy", "market", "static route", ["purchase"])
        static_purchase = static.materials.process_activity(buyer, buy, day=1, hour=8)
        produce = Activity(
            "restock_market", "Restock", "market", "static recipe",
            ["work", "production"],
        )
        static_production = static.materials.process_activity(
            merchant, produce, day=1, hour=12
        )
        scenarios["static_market_and_production_remain_operational"] = bool(
            static_purchase and static_production
        )

        invariants.update({
            "commerce_authority_valid": True,
            "currency_conserved": fresh.economy.conservation_holds(),
            "ledger_reconstructs": fresh.economy.ledger_reconstructs_balances(),
            "material_conservation_valid": fresh.materials.material_conservation_holds(),
            "material_history_reconstructs": fresh.materials.material_history_reconstructs_inventories(),
            "exchange_ledger_reconciles": fresh.materials.exchanges_reconcile_with_ledger(),
            "material_provenance_valid": fresh.materials.provenance_reconciles(),
            "production_provenance_valid": fresh.materials.production_records_are_valid(),
            "outcome_memory_provenance_valid": all(
                fresh.outcome_memory.validate().values()
            ),
            "migration_invariants_valid": True,
            "location_invariants_valid": all(
                fresh.location_growth.validate(fresh.locations, fresh.agents).values()
            ),
            "event_invariants_valid": all(
                fresh.event_ecology.validate(
                    locations=fresh.locations,
                    location_growth=fresh.location_growth,
                    activity_records=fresh.activity_records,
                ).values()
            ),
            "institution_invariants_valid": all(
                fresh.institution_growth.validate(
                    agents=fresh.agents, locations=fresh.locations,
                    location_growth=fresh.location_growth,
                    event_ecology=fresh.event_ecology, economy=fresh.economy,
                ).values()
            ),
            "commitments_valid": all(
                fresh.commitment_system.validate_invariants().values()
            ),
            "plans_valid": all(fresh.plan_system.validate_invariants().values()),
            "crime_valid": fresh.crime.evidence_is_valid(),
            "justice_valid": fresh.justice.history_is_valid(),
        })
        try:
            fresh.validate_population_authorities()
            fresh.validate_commerce_authorities()
        except ValueError:
            invariants["commerce_authority_valid"] = False
            invariants["migration_invariants_valid"] = False

    failed_scenarios = sorted(name for name, passed in scenarios.items() if not passed)
    failed_invariants = sorted(name for name, passed in invariants.items() if not passed)
    diagnostics["failed_scenarios"] = failed_scenarios
    diagnostics["failed_invariants"] = failed_invariants
    return {
        "passed": not failed_scenarios and not failed_invariants,
        "scenario_count": len(scenarios),
        "scenarios_passed": sum(scenarios.values()),
        "scenarios": scenarios,
        "invariant_count": len(invariants),
        "invariants_passed": sum(invariants.values()),
        "invariants": invariants,
        "diagnostics": diagnostics,
    }
