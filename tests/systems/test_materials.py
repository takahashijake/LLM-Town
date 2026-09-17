import pytest

from src.agents.agent import Agent
from src.systems.economy import EconomicAccount, EconomySystem, Employment
from src.systems.materials import (
    GoodDefinition,
    Inventory,
    MaterialError,
    MaterialSystem,
    Seller,
)


def build_agent():
    return Agent(
        id="buyer_agent",
        name="Buyer",
        personality="careful",
        location_id="market",
        needs={"social": 50, "wealth": 50, "knowledge": 50},
    )


def build_materials(*, buyer_balance=100, meal_stock=5):
    economy = EconomySystem(
        accounts=[
            EconomicAccount("buyer_account", "agent", "buyer_agent", buyer_balance),
            EconomicAccount("seller_account", "employer", "shop", 50),
        ],
        employments=[
            Employment(
                "merchant_job",
                "buyer_agent",
                "merchant",
                "seller_account",
                10,
                ("work",),
            )
        ],
    )
    materials = MaterialSystem(
        economy=economy,
        goods=[
            GoodDefinition("meal", "meal", "food", 8, True, "social", 3),
            GoodDefinition("book", "book", "information", 25),
        ],
        inventories=[
            Inventory("buyer_inventory", "agent", "buyer_agent", "buyer_account"),
            Inventory(
                "seller_inventory",
                "business",
                "seller",
                "seller_account",
                (("meal", meal_stock),),
            ),
        ],
        sellers=[
            Seller(
                "seller",
                "seller_inventory",
                "seller_account",
                "market",
                "merchant_job",
            )
        ],
    )
    return economy, materials


def purchase(materials, **overrides):
    values = {
        "buyer_inventory_id": "buyer_inventory",
        "buyer_account_id": "buyer_account",
        "seller_id": "seller",
        "good_id": "meal",
        "quantity": 1,
        "day": 1,
        "hour": 8,
        "event_key": "purchase:one",
    }
    values.update(overrides)
    return materials.purchase(**values)


def test_goods_inventory_and_ownership_initialize_deterministically():
    first_economy, first = build_materials()
    _second_economy, second = build_materials()
    assert first.to_dict() == second.to_dict()
    assert first.price_for_good("meal") == 8
    assert first.quantity("seller_inventory", "meal") == 5
    assert first.owners_of_good("meal") == {"seller_inventory": 5}
    assert first_economy.total_currency() == 150


def test_valid_inventory_transfer_changes_ownership_and_conserves_quantity():
    _economy, materials = build_materials()
    record = materials.transfer_good(
        "seller_inventory",
        "buyer_inventory",
        "meal",
        2,
        day=1,
        hour=8,
        reason="authorized stock transfer",
        authorization_type="test",
        authorization_id="authorization:one",
        event_key="transfer:one",
    )
    assert record.quantity == 2
    assert materials.owners_of_good("meal") == {
        "buyer_inventory": 2,
        "seller_inventory": 3,
    }
    assert materials.material_conservation_holds()
    assert materials.material_history_reconstructs_inventories()


@pytest.mark.parametrize(
    ("source", "destination", "good", "quantity", "code"),
    [
        ("seller_inventory", "buyer_inventory", "meal", 6, "insufficient_stock"),
        ("seller_inventory", "buyer_inventory", "meal", 0, "invalid_quantity"),
        ("seller_inventory", "buyer_inventory", "meal", -1, "invalid_quantity"),
        ("seller_inventory", "buyer_inventory", "meal", 1.5, "invalid_quantity"),
        ("seller_inventory", "buyer_inventory", "missing", 1, "unknown_good"),
        ("missing", "buyer_inventory", "meal", 1, "unknown_source_inventory"),
        ("seller_inventory", "missing", "meal", 1, "unknown_destination_inventory"),
    ],
)
def test_failed_inventory_transfer_is_atomic(source, destination, good, quantity, code):
    _economy, materials = build_materials()
    before = materials._quantity_snapshot()
    with pytest.raises(MaterialError) as error:
        materials.transfer_good(
            source,
            destination,
            good,
            quantity,
            day=1,
            hour=8,
            reason="invalid transfer",
            authorization_type="test",
            authorization_id="invalid",
        )
    assert error.value.code == code
    assert materials._quantity_snapshot() == before
    assert materials.inventory_transfers == []


def test_purchase_atomically_transfers_configured_price_and_stock():
    economy, materials = build_materials()
    exchange = purchase(materials, quantity=2)
    assert exchange.unit_price == 8
    assert exchange.total_price == 16
    assert economy.get_account("buyer_account").balance == 84
    assert economy.get_account("seller_account").balance == 66
    assert materials.quantity("seller_inventory", "meal") == 3
    assert materials.quantity("buyer_inventory", "meal") == 2
    assert economy.conservation_holds()
    assert materials.material_conservation_holds()
    transaction = economy.ledger[0]
    assert exchange.monetary_transaction_id == transaction.id
    assert dict(transaction.metadata)["exchange_id"] == exchange.id
    assert materials.exchanges_reconcile_with_ledger()


def test_purchase_api_does_not_accept_an_arbitrary_price():
    _economy, materials = build_materials()
    with pytest.raises(TypeError, match="unit_price"):
        purchase(materials, unit_price=1)
    assert materials.exchanges == []


@pytest.mark.parametrize(
    ("buyer_balance", "meal_stock", "overrides", "code"),
    [
        (7, 5, {}, "insufficient_funds"),
        (100, 0, {}, "insufficient_stock"),
        (100, 5, {"buyer_account_id": "missing"}, "unknown_buyer_account"),
        (100, 5, {"good_id": "book"}, "insufficient_stock"),
    ],
)
def test_failed_purchase_never_partially_mutates_money_or_goods(
    buyer_balance, meal_stock, overrides, code
):
    economy, materials = build_materials(
        buyer_balance=buyer_balance, meal_stock=meal_stock
    )
    balances = {key: account.balance for key, account in economy.accounts.items()}
    quantities = materials._quantity_snapshot()
    with pytest.raises(MaterialError) as error:
        purchase(materials, **overrides)
    assert error.value.code == code
    assert {key: account.balance for key, account in economy.accounts.items()} == balances
    assert materials._quantity_snapshot() == quantities
    assert economy.ledger == []
    assert materials.exchanges == []
    assert materials.inventory_transfers == []


def test_seller_must_own_its_linked_inventory():
    economy, _materials = build_materials()
    with pytest.raises(ValueError, match="does not own"):
        MaterialSystem(
            economy=economy,
            goods=[GoodDefinition("meal", "meal", "food", 8)],
            inventories=[
                Inventory(
                    "seller_inventory", "business", "someone_else", "seller_account"
                )
            ],
            sellers=[
                Seller(
                    "seller",
                    "seller_inventory",
                    "seller_account",
                    "market",
                    "merchant_job",
                )
            ],
        )


def test_consumption_requires_ownership_is_bounded_and_idempotent():
    _economy, materials = build_materials()
    agent = build_agent()
    with pytest.raises(MaterialError) as error:
        materials.consume(
            agent,
            "buyer_inventory",
            "meal",
            1,
            day=1,
            hour=8,
            activity_id="eat",
            event_key="consume:one",
        )
    assert error.value.code == "insufficient_stock"
    assert agent.needs["social"] == 50

    purchase(materials)
    agent.needs["social"] = 99
    record = materials.consume(
        agent,
        "buyer_inventory",
        "meal",
        1,
        day=1,
        hour=12,
        activity_id="eat",
        event_key="consume:one",
    )
    assert record.need_effect_amount == 3
    assert materials.quantity("buyer_inventory", "meal") == 0
    assert agent.needs["social"] == 100
    assert materials.material_conservation_holds()

    with pytest.raises(MaterialError) as duplicate:
        materials.consume(
            agent,
            "buyer_inventory",
            "meal",
            1,
            day=1,
            hour=18,
            activity_id="eat",
            event_key="consume:one",
        )
    assert duplicate.value.code == "duplicate_event"
    assert agent.needs["social"] == 100
    assert len(materials.consumptions) == 1


def test_material_round_trip_preserves_ownership_history_and_guards():
    economy, materials = build_materials()
    purchase(materials)
    restored = MaterialSystem.from_dict(materials.to_dict(), economy=economy)
    assert restored.to_dict() == materials.to_dict()
    assert restored.quantity("buyer_inventory", "meal") == 1
    with pytest.raises(MaterialError) as error:
        purchase(restored)
    assert error.value.code == "duplicate_event"
    assert len(restored.exchanges) == 1
