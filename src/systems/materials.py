"""Authoritative goods, inventory ownership, exchange, and consumption."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from src.systems.economy import EconomyError, EconomySystem


class MaterialError(ValueError):
    """A rejected material operation with no authoritative state mutation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class GoodDefinition:
    id: str
    name: str
    category: str
    unit_price: int
    consumable: bool = False
    need_effect: str | None = None
    need_effect_amount: int = 0

    def __post_init__(self) -> None:
        if not self.id or not self.name or not self.category:
            raise ValueError("good id, name, and category are required")
        if (
            isinstance(self.unit_price, bool)
            or not isinstance(self.unit_price, int)
            or self.unit_price <= 0
        ):
            raise ValueError("good unit price must be a positive integer")
        if self.need_effect_amount < 0:
            raise ValueError("good need effect cannot be negative")
        if self.need_effect_amount and not self.need_effect:
            raise ValueError("a need effect amount requires a need name")
        if self.need_effect and not self.consumable:
            raise ValueError("only consumable goods may define a need effect")


@dataclass(frozen=True)
class Inventory:
    id: str
    owner_type: str
    owner_id: str
    account_id: str | None
    quantities: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        if not self.id or not self.owner_type or not self.owner_id:
            raise ValueError("inventory id and owner identity are required")
        keys = [good_id for good_id, _quantity in self.quantities]
        if len(keys) != len(set(keys)):
            raise ValueError("inventory good ids must be unique")
        if any(
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity < 0
            for _good_id, quantity in self.quantities
        ):
            raise ValueError("inventory quantities must be non-negative integers")
        object.__setattr__(
            self,
            "quantities",
            tuple(sorted(
                (good_id, quantity)
                for good_id, quantity in self.quantities
                if quantity > 0
            )),
        )

    def quantity(self, good_id: str) -> int:
        return dict(self.quantities).get(good_id, 0)

    def with_quantity(self, good_id: str, quantity: int) -> "Inventory":
        values = dict(self.quantities)
        if quantity:
            values[good_id] = quantity
        else:
            values.pop(good_id, None)
        return replace(self, quantities=tuple(sorted(values.items())))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["quantities"] = dict(self.quantities)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Inventory":
        values = dict(data)
        values["quantities"] = tuple(sorted(values.get("quantities", {}).items()))
        return cls(**values)


@dataclass(frozen=True)
class Seller:
    id: str
    inventory_id: str
    account_id: str
    location_id: str
    operator_employment_id: str
    active: bool = True


@dataclass(frozen=True)
class PurchaseActivityRule:
    activity_id: str
    seller_id: str
    good_id: str
    quantity: int = 1


@dataclass(frozen=True)
class ConsumptionActivityRule:
    activity_id: str
    good_id: str
    quantity: int = 1


@dataclass(frozen=True)
class InventoryTransferRecord:
    id: str
    day: int
    hour: int | None
    source_inventory_id: str
    destination_inventory_id: str
    good_id: str
    quantity: int
    reason: str
    authorization_type: str
    authorization_id: str
    event_key: str | None = None


@dataclass(frozen=True)
class ExchangeRecord:
    id: str
    day: int
    hour: int | None
    buyer_inventory_id: str
    seller_id: str
    seller_inventory_id: str
    buyer_account_id: str
    seller_account_id: str
    good_id: str
    quantity: int
    unit_price: int
    total_price: int
    monetary_transaction_id: str
    inventory_transfer_id: str
    event_key: str


@dataclass(frozen=True)
class ConsumptionRecord:
    id: str
    day: int
    hour: int | None
    agent_id: str
    inventory_id: str
    good_id: str
    quantity: int
    need: str
    need_effect_amount: int
    activity_id: str
    event_key: str


class MaterialSystem:
    """Own all material quantities and coordinate atomic purchases with money."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        *,
        economy: EconomySystem,
        goods: list[GoodDefinition],
        inventories: list[Inventory],
        sellers: list[Seller],
        purchase_activity_rules: list[PurchaseActivityRule] | None = None,
        consumption_activity_rules: list[ConsumptionActivityRule] | None = None,
        initial_quantities: dict[str, dict[str, int]] | None = None,
        inventory_transfers: list[InventoryTransferRecord] | None = None,
        exchanges: list[ExchangeRecord] | None = None,
        consumptions: list[ConsumptionRecord] | None = None,
        applied_event_keys: set[str] | None = None,
        rejected_operations: list[dict] | None = None,
        next_transfer_number: int = 1,
        next_exchange_number: int = 1,
        next_consumption_number: int = 1,
    ):
        self.economy = economy
        self.goods = self._unique_by_id(goods, "good")
        self._inventories = self._unique_by_id(inventories, "inventory")
        self.sellers = self._unique_by_id(sellers, "seller")
        self.purchase_activity_rules = self._unique_by_field(
            purchase_activity_rules or [], "activity_id", "purchase activity"
        )
        self.consumption_activity_rules = self._unique_by_field(
            consumption_activity_rules or [], "activity_id", "consumption activity"
        )
        self.inventory_transfers = list(inventory_transfers or [])
        self.exchanges = list(exchanges or [])
        self.consumptions = list(consumptions or [])
        self.applied_event_keys = set(applied_event_keys or ())
        self.rejected_operations = list(rejected_operations or [])
        self.next_transfer_number = int(next_transfer_number)
        self.next_exchange_number = int(next_exchange_number)
        self.next_consumption_number = int(next_consumption_number)
        self.initial_quantities = (
            self._quantity_snapshot()
            if initial_quantities is None
            else {
                inventory_id: {good_id: int(quantity) for good_id, quantity in values.items()}
                for inventory_id, values in initial_quantities.items()
            }
        )
        self._validate_model()
        self._validate_history()

    @staticmethod
    def _unique_by_id(items: list, label: str) -> dict:
        ids = [item.id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{label} ids must be unique")
        return {item.id: item for item in items}

    @staticmethod
    def _unique_by_field(items: list, field: str, label: str) -> dict:
        values = [getattr(item, field) for item in items]
        if len(values) != len(set(values)):
            raise ValueError(f"{label} ids must be unique")
        return {getattr(item, field): item for item in items}

    @property
    def inventories(self) -> dict[str, Inventory]:
        return dict(self._inventories)

    def get_good(self, good_id: str) -> GoodDefinition:
        try:
            return self.goods[good_id]
        except KeyError as error:
            raise MaterialError("unknown_good", f"unknown good: {good_id}") from error

    def get_inventory(self, inventory_id: str) -> Inventory:
        try:
            return self._inventories[inventory_id]
        except KeyError as error:
            raise MaterialError(
                "unknown_inventory", f"unknown inventory: {inventory_id}"
            ) from error

    def inventory_for_agent(self, agent_id: str) -> Inventory:
        matches = [
            inventory for inventory in self._inventories.values()
            if inventory.owner_type == "agent" and inventory.owner_id == agent_id
        ]
        if len(matches) != 1:
            raise MaterialError(
                "unknown_inventory", f"expected one inventory for agent: {agent_id}"
            )
        return matches[0]

    def quantity(self, inventory_id: str, good_id: str) -> int:
        self.get_good(good_id)
        return self.get_inventory(inventory_id).quantity(good_id)

    def owners_of_good(self, good_id: str) -> dict[str, int]:
        self.get_good(good_id)
        return {
            inventory.id: inventory.quantity(good_id)
            for inventory in self._inventories.values()
            if inventory.quantity(good_id) > 0
        }

    def price_for_good(self, good_id: str) -> int:
        return self.get_good(good_id).unit_price

    def _quantity_snapshot(self) -> dict[str, dict[str, int]]:
        return {
            inventory_id: dict(inventory.quantities)
            for inventory_id, inventory in self._inventories.items()
        }

    def _validate_model(self) -> None:
        if set(self.initial_quantities) != set(self._inventories):
            raise ValueError("initial quantities must match inventory ids")
        agent_owners = [
            inventory.owner_id for inventory in self._inventories.values()
            if inventory.owner_type == "agent"
        ]
        if len(agent_owners) != len(set(agent_owners)):
            raise ValueError("an agent may have only one inventory")
        account_ids = self.economy.accounts
        for inventory in self._inventories.values():
            if inventory.account_id is not None and inventory.account_id not in account_ids:
                raise ValueError(f"inventory {inventory.id} references unknown account")
            if inventory.owner_type == "agent":
                if inventory.account_id is None:
                    raise ValueError(f"agent inventory {inventory.id} requires an account")
                account = account_ids[inventory.account_id]
                if account.owner_type != "agent" or account.owner_id != inventory.owner_id:
                    raise ValueError(
                        f"agent inventory {inventory.id} does not control its account"
                    )
            for good_id, quantity in inventory.quantities:
                if good_id not in self.goods:
                    raise ValueError(f"inventory {inventory.id} references unknown good")
                if quantity < 0:
                    raise ValueError("inventory quantity cannot be negative")
        for inventory_id, values in self.initial_quantities.items():
            for good_id, quantity in values.items():
                if good_id not in self.goods or quantity < 0:
                    raise ValueError(f"invalid initial quantity in {inventory_id}")
        for seller in self.sellers.values():
            inventory = self.get_inventory(seller.inventory_id)
            if inventory.owner_type != "business" or inventory.owner_id != seller.id:
                raise ValueError(f"seller {seller.id} does not own its inventory")
            if seller.account_id not in account_ids:
                raise ValueError(f"seller {seller.id} references unknown account")
            if inventory.account_id != seller.account_id:
                raise ValueError(f"seller {seller.id} account linkage is inconsistent")
            if seller.operator_employment_id not in self.economy.employments:
                raise ValueError(f"seller {seller.id} has no valid operator employment")
        for rule in self.purchase_activity_rules.values():
            if rule.seller_id not in self.sellers or rule.good_id not in self.goods:
                raise ValueError("purchase activity references unknown seller or good")
            self._validate_quantity(rule.quantity)
        for rule in self.consumption_activity_rules.values():
            good = self.goods.get(rule.good_id)
            if good is None or not good.consumable:
                raise ValueError("consumption activity requires a consumable good")
            self._validate_quantity(rule.quantity)

    def _validate_history(self) -> None:
        record_groups = (
            (self.inventory_transfers, "inventory transfer"),
            (self.exchanges, "exchange"),
            (self.consumptions, "consumption"),
        )
        for records, label in record_groups:
            ids = [record.id for record in records]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label} ids must be unique")
        event_keys = [
            record.event_key
            for records, _label in record_groups
            for record in records
            if record.event_key
        ]
        if len(event_keys) != len(set(event_keys)):
            raise ValueError("material event keys must be unique")
        if not set(event_keys).issubset(self.applied_event_keys):
            raise ValueError("material history is missing idempotency guards")
        if not self.material_history_reconstructs_inventories():
            raise ValueError("material history does not reconstruct inventories")
        if not self.exchanges_reconcile_with_ledger():
            raise ValueError("exchange history does not reconcile with ledger")
        if not self.consumption_records_are_valid():
            raise ValueError("consumption history is invalid")

    def _attempt(self, operation: str, **values) -> dict:
        return {"operation": operation, **values}

    def _reject(self, code: str, message: str, attempt: dict) -> None:
        self.rejected_operations.append({"code": code, **attempt})
        raise MaterialError(code, message)

    def _validate_quantity(self, quantity: int, attempt: dict | None = None) -> None:
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            if attempt is None:
                raise ValueError("quantity must be a positive integer")
            self._reject("invalid_quantity", "quantity must be a positive integer", attempt)

    def _validate_transfer(
        self,
        source_inventory_id: str,
        destination_inventory_id: str,
        good_id: str,
        quantity: int,
        event_key: str | None,
        attempt: dict,
    ) -> tuple[Inventory, Inventory, GoodDefinition]:
        if source_inventory_id not in self._inventories:
            self._reject("unknown_source_inventory", "source inventory does not exist", attempt)
        if destination_inventory_id not in self._inventories:
            self._reject(
                "unknown_destination_inventory", "destination inventory does not exist", attempt
            )
        if source_inventory_id == destination_inventory_id:
            self._reject("same_inventory", "source and destination must differ", attempt)
        if good_id not in self.goods:
            self._reject("unknown_good", "good does not exist", attempt)
        self._validate_quantity(quantity, attempt)
        if event_key and event_key in self.applied_event_keys:
            self._reject("duplicate_event", "material event was already applied", attempt)
        source = self._inventories[source_inventory_id]
        destination = self._inventories[destination_inventory_id]
        if source.quantity(good_id) < quantity:
            self._reject("insufficient_stock", "source has insufficient stock", attempt)
        return source, destination, self.goods[good_id]

    def _commit_transfer(
        self,
        source: Inventory,
        destination: Inventory,
        good_id: str,
        quantity: int,
        *,
        day: int,
        hour: int | None,
        reason: str,
        authorization_type: str,
        authorization_id: str,
        event_key: str | None,
    ) -> InventoryTransferRecord:
        record = InventoryTransferRecord(
            id=f"material-transfer-{self.next_transfer_number:08d}",
            day=int(day),
            hour=None if hour is None else int(hour),
            source_inventory_id=source.id,
            destination_inventory_id=destination.id,
            good_id=good_id,
            quantity=quantity,
            reason=reason,
            authorization_type=authorization_type,
            authorization_id=authorization_id,
            event_key=event_key,
        )
        self._inventories[source.id] = source.with_quantity(
            good_id, source.quantity(good_id) - quantity
        )
        self._inventories[destination.id] = destination.with_quantity(
            good_id, destination.quantity(good_id) + quantity
        )
        self.inventory_transfers.append(record)
        if event_key:
            self.applied_event_keys.add(event_key)
        self.next_transfer_number += 1
        return record

    def transfer_good(
        self,
        source_inventory_id: str,
        destination_inventory_id: str,
        good_id: str,
        quantity: int,
        *,
        day: int,
        hour: int | None,
        reason: str,
        authorization_type: str,
        authorization_id: str,
        event_key: str | None = None,
    ) -> InventoryTransferRecord:
        attempt = self._attempt(
            "transfer",
            day=day,
            hour=hour,
            source_inventory_id=source_inventory_id,
            destination_inventory_id=destination_inventory_id,
            good_id=good_id,
            quantity=quantity,
            event_key=event_key,
        )
        source, destination, _good = self._validate_transfer(
            source_inventory_id,
            destination_inventory_id,
            good_id,
            quantity,
            event_key,
            attempt,
        )
        return self._commit_transfer(
            source,
            destination,
            good_id,
            quantity,
            day=day,
            hour=hour,
            reason=reason,
            authorization_type=authorization_type,
            authorization_id=authorization_id,
            event_key=event_key,
        )

    def purchase(
        self,
        buyer_inventory_id: str,
        buyer_account_id: str,
        seller_id: str,
        good_id: str,
        quantity: int,
        *,
        day: int,
        hour: int | None,
        event_key: str,
    ) -> ExchangeRecord:
        attempt = self._attempt(
            "purchase",
            day=day,
            hour=hour,
            buyer_inventory_id=buyer_inventory_id,
            buyer_account_id=buyer_account_id,
            seller_id=seller_id,
            good_id=good_id,
            quantity=quantity,
            event_key=event_key,
        )
        if event_key in self.applied_event_keys:
            self._reject("duplicate_event", "purchase was already applied", attempt)
        if seller_id not in self.sellers:
            self._reject("unknown_seller", "seller does not exist", attempt)
        if buyer_inventory_id not in self._inventories:
            self._reject("unknown_buyer_inventory", "buyer inventory does not exist", attempt)
        if buyer_account_id not in self.economy.accounts:
            self._reject("unknown_buyer_account", "buyer account does not exist", attempt)
        seller = self.sellers[seller_id]
        buyer_inventory = self._inventories[buyer_inventory_id]
        if buyer_inventory.account_id != buyer_account_id:
            self._reject("buyer_account_mismatch", "buyer does not control that account", attempt)
        if not seller.active:
            self._reject("inactive_seller", "seller is not active", attempt)
        source, destination, good = self._validate_transfer(
            seller.inventory_id,
            buyer_inventory_id,
            good_id,
            quantity,
            None,
            attempt,
        )
        buyer_account = self.economy.get_account(buyer_account_id)
        total_price = good.unit_price * quantity
        if buyer_account.balance < total_price:
            self._reject("insufficient_funds", "buyer has insufficient funds", attempt)

        exchange_id = f"exchange-{self.next_exchange_number:08d}"
        transfer_id = f"material-transfer-{self.next_transfer_number:08d}"
        try:
            payment = self.economy.transfer(
                buyer_account_id,
                seller.account_id,
                total_price,
                day=day,
                hour=hour,
                transaction_type="purchase",
                reason=f"Purchase of {quantity} {good.name}",
                event_key=f"material-payment:{event_key}",
                metadata={
                    "exchange_id": exchange_id,
                    "good_id": good_id,
                    "quantity": quantity,
                },
            )
        except EconomyError as error:
            self._reject(
                f"payment_{error.code}",
                "purchase payment was rejected",
                attempt,
            )
        transfer = self._commit_transfer(
            source,
            destination,
            good_id,
            quantity,
            day=day,
            hour=hour,
            reason=f"Authorized purchase {exchange_id}",
            authorization_type="exchange",
            authorization_id=exchange_id,
            event_key=None,
        )
        if transfer.id != transfer_id:
            raise RuntimeError("material transfer counter changed during purchase")
        exchange = ExchangeRecord(
            id=exchange_id,
            day=int(day),
            hour=None if hour is None else int(hour),
            buyer_inventory_id=buyer_inventory_id,
            seller_id=seller_id,
            seller_inventory_id=seller.inventory_id,
            buyer_account_id=buyer_account_id,
            seller_account_id=seller.account_id,
            good_id=good_id,
            quantity=quantity,
            unit_price=good.unit_price,
            total_price=total_price,
            monetary_transaction_id=payment.id,
            inventory_transfer_id=transfer.id,
            event_key=event_key,
        )
        self.exchanges.append(exchange)
        self.applied_event_keys.add(event_key)
        self.next_exchange_number += 1
        return exchange

    def consume(
        self,
        agent,
        inventory_id: str,
        good_id: str,
        quantity: int,
        *,
        day: int,
        hour: int | None,
        activity_id: str,
        event_key: str,
    ) -> ConsumptionRecord:
        attempt = self._attempt(
            "consume",
            day=day,
            hour=hour,
            agent_id=agent.id,
            inventory_id=inventory_id,
            good_id=good_id,
            quantity=quantity,
            event_key=event_key,
        )
        if event_key in self.applied_event_keys:
            self._reject("duplicate_event", "consumption was already applied", attempt)
        if inventory_id not in self._inventories:
            self._reject("unknown_inventory", "inventory does not exist", attempt)
        if good_id not in self.goods:
            self._reject("unknown_good", "good does not exist", attempt)
        self._validate_quantity(quantity, attempt)
        inventory = self._inventories[inventory_id]
        good = self.goods[good_id]
        if inventory.owner_type != "agent" or inventory.owner_id != agent.id:
            self._reject("not_owner", "agent does not own this inventory", attempt)
        if not good.consumable or not good.need_effect:
            self._reject("not_consumable", "good has no consumption effect", attempt)
        if inventory.quantity(good_id) < quantity:
            self._reject("insufficient_stock", "agent does not own enough goods", attempt)
        if good.need_effect not in agent.needs:
            self._reject("unknown_need", "agent does not have the configured need", attempt)

        record = ConsumptionRecord(
            id=f"consumption-{self.next_consumption_number:08d}",
            day=int(day),
            hour=None if hour is None else int(hour),
            agent_id=agent.id,
            inventory_id=inventory_id,
            good_id=good_id,
            quantity=quantity,
            need=good.need_effect,
            need_effect_amount=good.need_effect_amount * quantity,
            activity_id=activity_id,
            event_key=event_key,
        )
        self._inventories[inventory_id] = inventory.with_quantity(
            good_id, inventory.quantity(good_id) - quantity
        )
        self.consumptions.append(record)
        self.applied_event_keys.add(event_key)
        self.next_consumption_number += 1
        agent.satisfy_need(record.need, record.need_effect_amount)
        return record

    def process_activity(self, agent, activity, *, day: int, hour: int):
        if activity.id in self.purchase_activity_rules:
            rule = self.purchase_activity_rules[activity.id]
            seller = self.sellers[rule.seller_id]
            if activity.location_id != seller.location_id or "purchase" not in activity.tags:
                return None
            inventory = self.inventory_for_agent(agent.id)
            account = self.economy.account_for_agent(agent.id)
            try:
                return self.purchase(
                    inventory.id,
                    account.id,
                    seller.id,
                    rule.good_id,
                    rule.quantity,
                    day=day,
                    hour=hour,
                    event_key=f"purchase:{agent.id}:{activity.id}:{day}",
                )
            except MaterialError:
                return None

        if activity.id in self.consumption_activity_rules:
            rule = self.consumption_activity_rules[activity.id]
            if "consume" not in activity.tags:
                return None
            inventory = self.inventory_for_agent(agent.id)
            try:
                return self.consume(
                    agent,
                    inventory.id,
                    rule.good_id,
                    rule.quantity,
                    day=day,
                    hour=hour,
                    activity_id=activity.id,
                    event_key=f"consume:{agent.id}:{activity.id}:{day}",
                )
            except MaterialError:
                return None
        return None

    def total_quantities(self) -> dict[str, int]:
        totals = Counter()
        for inventory in self._inventories.values():
            totals.update(dict(inventory.quantities))
        return {good_id: totals[good_id] for good_id in sorted(self.goods)}

    def initial_total_quantities(self) -> dict[str, int]:
        totals = Counter()
        for quantities in self.initial_quantities.values():
            totals.update(quantities)
        return {good_id: totals[good_id] for good_id in sorted(self.goods)}

    def consumed_quantities(self) -> dict[str, int]:
        totals = Counter()
        for record in self.consumptions:
            totals[record.good_id] += record.quantity
        return {good_id: totals[good_id] for good_id in sorted(self.goods)}

    def material_conservation_holds(self) -> bool:
        initial = self.initial_total_quantities()
        current = self.total_quantities()
        consumed = self.consumed_quantities()
        return all(current[good_id] + consumed[good_id] == initial[good_id] for good_id in self.goods)

    def material_history_reconstructs_inventories(self) -> bool:
        reconstructed = {
            inventory_id: Counter(values)
            for inventory_id, values in self.initial_quantities.items()
        }
        for record in self.inventory_transfers:
            if (
                record.source_inventory_id not in reconstructed
                or record.destination_inventory_id not in reconstructed
                or record.good_id not in self.goods
                or record.quantity <= 0
            ):
                return False
            reconstructed[record.source_inventory_id][record.good_id] -= record.quantity
            if reconstructed[record.source_inventory_id][record.good_id] < 0:
                return False
            reconstructed[record.destination_inventory_id][record.good_id] += record.quantity
        for record in self.consumptions:
            if record.inventory_id not in reconstructed or record.good_id not in self.goods:
                return False
            reconstructed[record.inventory_id][record.good_id] -= record.quantity
            if reconstructed[record.inventory_id][record.good_id] < 0:
                return False
        return all(
            all(quantity >= 0 for quantity in reconstructed[inventory_id].values())
            and {
                good_id: quantity
                for good_id, quantity in reconstructed[inventory_id].items()
                if quantity
            } == dict(inventory.quantities)
            for inventory_id, inventory in self._inventories.items()
        )

    def exchanges_reconcile_with_ledger(self) -> bool:
        ledger = {transaction.id: transaction for transaction in self.economy.ledger}
        transfers = {record.id: record for record in self.inventory_transfers}
        purchase_transactions = [
            transaction for transaction in self.economy.ledger
            if transaction.transaction_type == "purchase"
        ]
        exchange_ids = {exchange.id for exchange in self.exchanges}
        if {
            dict(transaction.metadata).get("exchange_id")
            for transaction in purchase_transactions
        } != exchange_ids:
            return False
        if {
            transfer.authorization_id
            for transfer in self.inventory_transfers
            if transfer.authorization_type == "exchange"
        } != exchange_ids:
            return False
        for exchange in self.exchanges:
            transaction = ledger.get(exchange.monetary_transaction_id)
            transfer = transfers.get(exchange.inventory_transfer_id)
            if transaction is None or transfer is None:
                return False
            metadata = dict(transaction.metadata)
            if not (
                transaction.transaction_type == "purchase"
                and transaction.source_account_id == exchange.buyer_account_id
                and transaction.destination_account_id == exchange.seller_account_id
                and transaction.amount == exchange.total_price
                and metadata.get("exchange_id") == exchange.id
                and transfer.authorization_type == "exchange"
                and transfer.authorization_id == exchange.id
                and transfer.good_id == exchange.good_id
                and transfer.quantity == exchange.quantity
                and transfer.source_inventory_id == exchange.seller_inventory_id
                and transfer.destination_inventory_id == exchange.buyer_inventory_id
            ):
                return False
        return True

    def consumption_records_are_valid(self) -> bool:
        for record in self.consumptions:
            inventory = self._inventories.get(record.inventory_id)
            good = self.goods.get(record.good_id)
            if (
                inventory is None
                or good is None
                or inventory.owner_type != "agent"
                or inventory.owner_id != record.agent_id
                or not good.consumable
                or record.quantity <= 0
                or record.need != good.need_effect
                or record.need_effect_amount
                != good.need_effect_amount * record.quantity
            ):
                return False
        return True

    def diagnostics(self) -> dict:
        return {
            "goods": len(self.goods),
            "inventories": len(self._inventories),
            "sellers": len(self.sellers),
            "exchange_count": len(self.exchanges),
            "consumption_count": len(self.consumptions),
            "inventory_transfer_count": len(self.inventory_transfers),
            "goods_exchanged": dict(sorted(Counter(
                exchange.good_id for exchange in self.exchanges
            ).items())),
            "quantities_exchanged": dict(sorted({
                good_id: sum(
                    exchange.quantity for exchange in self.exchanges
                    if exchange.good_id == good_id
                )
                for good_id in self.goods
                if any(exchange.good_id == good_id for exchange in self.exchanges)
            }.items())),
            "total_quantities": self.total_quantities(),
            "initial_total_quantities": self.initial_total_quantities(),
            "consumed_quantities": self.consumed_quantities(),
            "no_negative_inventory": all(
                quantity >= 0
                for inventory in self._inventories.values()
                for _good_id, quantity in inventory.quantities
            ),
            "material_conserved_with_consumption": self.material_conservation_holds(),
            "history_reconstructs_inventories": self.material_history_reconstructs_inventories(),
            "exchanges_reconcile_with_ledger": self.exchanges_reconcile_with_ledger(),
            "consumption_records_valid": self.consumption_records_are_valid(),
            "rejected_operation_count": len(self.rejected_operations),
            "rejection_counts_by_code": dict(sorted(Counter(
                record["code"] for record in self.rejected_operations
            ).items())),
            "idempotency_rejections": sum(
                record["code"] == "duplicate_event" for record in self.rejected_operations
            ),
        }

    def to_dict(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "goods": [asdict(good) for good in self.goods.values()],
            "inventories": [inventory.to_dict() for inventory in self._inventories.values()],
            "sellers": [asdict(seller) for seller in self.sellers.values()],
            "purchase_activity_rules": [
                asdict(rule) for rule in self.purchase_activity_rules.values()
            ],
            "consumption_activity_rules": [
                asdict(rule) for rule in self.consumption_activity_rules.values()
            ],
            "initial_quantities": self.initial_quantities,
            "inventory_transfers": [asdict(record) for record in self.inventory_transfers],
            "exchanges": [asdict(record) for record in self.exchanges],
            "consumptions": [asdict(record) for record in self.consumptions],
            "applied_event_keys": sorted(self.applied_event_keys),
            "rejected_operations": self.rejected_operations,
            "next_transfer_number": self.next_transfer_number,
            "next_exchange_number": self.next_exchange_number,
            "next_consumption_number": self.next_consumption_number,
        }

    @classmethod
    def from_dict(cls, data: dict, *, economy: EconomySystem) -> "MaterialSystem":
        if data.get("schema_version", 1) != cls.SCHEMA_VERSION:
            raise ValueError("unsupported material schema version")
        return cls(
            economy=economy,
            goods=[GoodDefinition(**item) for item in data.get("goods", [])],
            inventories=[Inventory.from_dict(item) for item in data.get("inventories", [])],
            sellers=[Seller(**item) for item in data.get("sellers", [])],
            purchase_activity_rules=[
                PurchaseActivityRule(**item)
                for item in data.get("purchase_activity_rules", [])
            ],
            consumption_activity_rules=[
                ConsumptionActivityRule(**item)
                for item in data.get("consumption_activity_rules", [])
            ],
            initial_quantities=data.get("initial_quantities"),
            inventory_transfers=[
                InventoryTransferRecord(**item)
                for item in data.get("inventory_transfers", [])
            ],
            exchanges=[ExchangeRecord(**item) for item in data.get("exchanges", [])],
            consumptions=[
                ConsumptionRecord(**item) for item in data.get("consumptions", [])
            ],
            applied_event_keys=set(data.get("applied_event_keys", [])),
            rejected_operations=data.get("rejected_operations", []),
            next_transfer_number=data.get("next_transfer_number", 1),
            next_exchange_number=data.get("next_exchange_number", 1),
            next_consumption_number=data.get("next_consumption_number", 1),
        )

    @classmethod
    def from_config(
        cls,
        path: str | Path,
        *,
        economy: EconomySystem,
        agents: list,
    ) -> "MaterialSystem":
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        agent_ids = {agent.id for agent in agents}
        employments = set(economy.employments)
        sellers = [
            Seller(**item)
            for item in config.get("sellers", [])
            if item.get("operator_employment_id") in employments
        ]
        seller_inventory_ids = {seller.inventory_id for seller in sellers}
        inventories = [
            Inventory.from_dict(item)
            for item in config.get("business_inventories", [])
            if item.get("id") in seller_inventory_ids
        ]
        for agent in agents:
            account = economy.account_for_agent(agent.id)
            starting_quantities = config.get(
                "agent_starting_quantities", {}
            ).get(agent.id, {})
            inventories.append(Inventory(
                id=f"inventory:agent:{agent.id}",
                owner_type="agent",
                owner_id=agent.id,
                account_id=account.id,
                quantities=tuple(sorted(starting_quantities.items())),
            ))
        seller_ids = {seller.id for seller in sellers}
        goods = [GoodDefinition(**item) for item in config.get("goods", [])]
        purchase_rules = [
            PurchaseActivityRule(**item)
            for item in config.get("purchase_activity_rules", [])
            if item.get("seller_id") in seller_ids
        ]
        return cls(
            economy=economy,
            goods=goods,
            inventories=inventories,
            sellers=sellers,
            purchase_activity_rules=purchase_rules,
            consumption_activity_rules=[
                ConsumptionActivityRule(**item)
                for item in config.get("consumption_activity_rules", [])
            ],
        )
