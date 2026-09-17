"""Deterministic acceptance evaluation for material ownership and exchange."""

from __future__ import annotations

import json
from pathlib import Path

from src.behavior.activity import Activity
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.materials import MaterialError


def _balances(engine) -> dict[str, int]:
    return {
        account_id: account.balance
        for account_id, account in engine.economy.accounts.items()
    }


def _quantities(engine) -> dict[str, dict[str, int]]:
    return {
        inventory_id: dict(inventory.quantities)
        for inventory_id, inventory in engine.materials.inventories.items()
    }


def run_material_evaluation(
    work_dir: str | Path,
    *,
    project_root: str | Path = ".",
) -> dict:
    project_root = Path(project_root).resolve()
    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    state_path = work_dir / "save_state.json"
    engine = SimulationEngine(
        agents_path=project_root / "data/agents.json",
        locations_path=project_root / "data/locations.json",
        economy_path=project_root / "data/economy.json",
        materials_path=project_root / "data/materials.json",
        llm_client=FakeLLMClient(),
        state_path=state_path,
        logs_dir=work_dir / "logs",
    )
    buyer = next(agent for agent in engine.agents if agent.id == "agent_001")
    buyer_inventory = engine.materials.inventory_for_agent(buyer.id)
    buyer_account = engine.economy.account_for_agent(buyer.id)
    seller = engine.materials.sellers["seller:market_stall"]
    good_id = "prepared_meal"

    before_purchase = {
        "buyer_balance": buyer_account.balance,
        "seller_balance": engine.economy.get_account(seller.account_id).balance,
        "buyer_quantity": engine.materials.quantity(buyer_inventory.id, good_id),
        "seller_quantity": engine.materials.quantity(seller.inventory_id, good_id),
    }
    purchase_activity = Activity(
        "buy_meal",
        "Buy a prepared meal",
        "market",
        "Deterministic material evaluation purchase",
        ["purchase"],
    )
    exchange = engine.materials.process_activity(
        buyer, purchase_activity, day=1, hour=8
    )
    after_purchase = {
        "buyer_balance": engine.economy.get_account(buyer_account.id).balance,
        "seller_balance": engine.economy.get_account(seller.account_id).balance,
        "buyer_quantity": engine.materials.quantity(buyer_inventory.id, good_id),
        "seller_quantity": engine.materials.quantity(seller.inventory_id, good_id),
    }

    balances_before_failure = _balances(engine)
    quantities_before_failure = _quantities(engine)
    ledger_before_failure = len(engine.economy.ledger)
    exchanges_before_failure = len(engine.materials.exchanges)
    failed_code = None
    try:
        engine.materials.purchase(
            buyer_inventory.id,
            buyer_account.id,
            seller.id,
            good_id,
            10_000,
            day=1,
            hour=9,
            event_key="evaluation:known-failure",
        )
    except MaterialError as error:
        failed_code = error.code
    failed_purchase_atomic = (
        failed_code == "insufficient_stock"
        and _balances(engine) == balances_before_failure
        and _quantities(engine) == quantities_before_failure
        and len(engine.economy.ledger) == ledger_before_failure
        and len(engine.materials.exchanges) == exchanges_before_failure
    )

    need_before_consumption = buyer.needs["social"]
    consume_activity = Activity(
        "eat_meal",
        "Eat an owned prepared meal",
        buyer.location_id,
        "Deterministic material evaluation consumption",
        ["consume"],
    )
    consumption = engine.materials.process_activity(
        buyer, consume_activity, day=1, hour=12
    )
    need_after_consumption = buyer.needs["social"]
    engine.state.save(engine, 1, 12, day_complete=False)
    economy_before_resume = engine.economy.to_dict()
    materials_before_resume = engine.materials.to_dict()

    resumed = SimulationEngine(
        agents_path=project_root / "data/agents.json",
        locations_path=project_root / "data/locations.json",
        economy_path=project_root / "data/economy.json",
        materials_path=project_root / "data/materials.json",
        load_state=True,
        llm_client=FakeLLMClient(),
        state_path=state_path,
        logs_dir=work_dir / "resumed_logs",
    )
    persistence_preserved = (
        resumed.economy.to_dict() == economy_before_resume
        and resumed.materials.to_dict() == materials_before_resume
    )
    resumed_buyer = next(agent for agent in resumed.agents if agent.id == buyer.id)
    counts_before_duplicates = (
        len(resumed.economy.ledger),
        len(resumed.materials.exchanges),
        len(resumed.materials.consumptions),
    )
    quantities_before_duplicates = _quantities(resumed)
    balances_before_duplicates = _balances(resumed)
    duplicate_codes = []
    for operation in (
        lambda: resumed.materials.purchase(
            buyer_inventory.id,
            buyer_account.id,
            seller.id,
            good_id,
            1,
            day=1,
            hour=18,
            event_key=f"purchase:{buyer.id}:buy_meal:1",
        ),
        lambda: resumed.materials.consume(
            resumed_buyer,
            buyer_inventory.id,
            good_id,
            1,
            day=1,
            hour=18,
            activity_id="eat_meal",
            event_key=f"consume:{buyer.id}:eat_meal:1",
        ),
    ):
        try:
            operation()
        except MaterialError as error:
            duplicate_codes.append(error.code)

    diagnostics = resumed.materials.diagnostics()
    economy_diagnostics = resumed.economy.diagnostics()
    duplicate_guards_hold = (
        duplicate_codes == ["duplicate_event", "duplicate_event"]
        and counts_before_duplicates
        == (
            len(resumed.economy.ledger),
            len(resumed.materials.exchanges),
            len(resumed.materials.consumptions),
        )
        and quantities_before_duplicates == _quantities(resumed)
        and balances_before_duplicates == _balances(resumed)
    )
    purchase_deltas_valid = (
        exchange is not None
        and before_purchase["buyer_balance"] >= exchange.total_price
        and before_purchase["seller_quantity"] >= exchange.quantity
        and after_purchase["buyer_balance"]
        == before_purchase["buyer_balance"] - exchange.total_price
        and after_purchase["seller_balance"]
        == before_purchase["seller_balance"] + exchange.total_price
        and after_purchase["buyer_quantity"]
        == before_purchase["buyer_quantity"] + exchange.quantity
        and after_purchase["seller_quantity"]
        == before_purchase["seller_quantity"] - exchange.quantity
    )
    consumption_valid = (
        consumption is not None
        and after_purchase["buyer_quantity"] >= consumption.quantity
        and need_after_consumption
        == min(100, need_before_consumption + consumption.need_effect_amount)
    )
    invariants = {
        "successful_purchase_changed_money_and_goods": purchase_deltas_valid,
        "configured_price_was_used": exchange.unit_price
        == resumed.materials.price_for_good(good_id),
        "failed_purchase_was_atomic": failed_purchase_atomic,
        "currency_conserved": economy_diagnostics["currency_conserved"],
        "ledger_reconstructs_balances": economy_diagnostics[
            "ledger_reconstructs_balances"
        ],
        "no_negative_inventory": diagnostics["no_negative_inventory"],
        "material_conserved_with_consumption": diagnostics[
            "material_conserved_with_consumption"
        ],
        "history_reconstructs_inventories": diagnostics[
            "history_reconstructs_inventories"
        ],
        "exchange_reconciles_with_ledger": diagnostics[
            "exchanges_reconcile_with_ledger"
        ],
        "consumption_record_is_valid": diagnostics["consumption_records_valid"],
        "consumption_required_owned_stock_and_changed_need": consumption_valid,
        "persistence_preserved": persistence_preserved,
        "resume_idempotency_guards_hold": duplicate_guards_hold,
    }
    return {
        "schema_version": 1,
        "kind": "llm-town-material-evaluation",
        "passed": all(invariants.values()),
        "invariants": invariants,
        "material_diagnostics": diagnostics,
        "economy_diagnostics": economy_diagnostics,
        "purchase": {
            "exchange_id": exchange.id,
            "monetary_transaction_id": exchange.monetary_transaction_id,
            "inventory_transfer_id": exchange.inventory_transfer_id,
            "good_id": exchange.good_id,
            "quantity": exchange.quantity,
            "unit_price": exchange.unit_price,
            "total_price": exchange.total_price,
            "before": before_purchase,
            "after": after_purchase,
        },
        "failed_purchase": {
            "rejection_code": failed_code,
            "no_partial_mutation": failed_purchase_atomic,
        },
        "consumption": {
            "record_id": consumption.id,
            "good_id": consumption.good_id,
            "quantity": consumption.quantity,
            "need": consumption.need,
            "need_before": need_before_consumption,
            "need_after": need_after_consumption,
        },
        "duplicate_rejection_codes": duplicate_codes,
    }


def write_material_evaluation(document: dict, output_path: str | Path) -> None:
    Path(output_path).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
