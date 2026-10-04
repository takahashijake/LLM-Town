"""Deterministic, closed-system economic state and transaction authority."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from src.systems.persistence_validation import require_sequence


class EconomyError(ValueError):
    """A rejected economic mutation. State is unchanged when this is raised."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EconomicAccount:
    id: str
    owner_type: str
    owner_id: str
    balance: int

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("account id is required")
        if isinstance(self.balance, bool) or not isinstance(self.balance, int):
            raise TypeError("account balance must be an integer")
        if self.balance < 0:
            raise ValueError("account balance cannot be negative")
        if self.owner_type not in {"agent", "employer", "institution", "system"}:
            raise ValueError("account owner type is not supported")
        if not self.owner_id:
            raise ValueError("account owner id is required")


@dataclass(frozen=True)
class TransactionRecord:
    id: str
    day: int
    hour: int | None
    source_account_id: str
    destination_account_id: str
    amount: int
    transaction_type: str
    reason: str
    event_key: str | None = None
    metadata: tuple[tuple[str, Any], ...] = ()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["metadata"] = dict(self.metadata)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "TransactionRecord":
        values = dict(data)
        values["metadata"] = tuple(sorted(values.get("metadata", {}).items()))
        return cls(**values)


@dataclass(frozen=True)
class Employment:
    id: str
    agent_id: str
    title: str
    employer_account_id: str
    wage: int
    qualifying_activity_ids: tuple[str, ...]
    active: bool = True
    start_day: int = 1
    activity_locations: tuple[tuple[str, str], ...] = ()
    activity_names: tuple[tuple[str, str], ...] = ()
    institution_id: str | None = None
    formation_id: str | None = None
    role_template_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.wage, bool) or not isinstance(self.wage, int) or self.wage <= 0:
            raise ValueError("employment wage must be a positive integer")
        if not all((self.id, self.agent_id, self.title, self.employer_account_id)):
            raise ValueError("employment identity is incomplete")
        if (isinstance(self.start_day, bool) or not isinstance(self.start_day, int)
                or self.start_day < 1):
            raise ValueError("employment start day must be positive")
        if not self.qualifying_activity_ids or len(self.qualifying_activity_ids) != len(
            set(self.qualifying_activity_ids)
        ):
            raise ValueError("employment activities must be nonempty and unique")
        locations = dict(self.activity_locations)
        names = dict(self.activity_names)
        if len(locations) != len(self.activity_locations) or len(names) != len(
            self.activity_names
        ):
            raise ValueError("employment activity contracts must be unique")
        if (set(locations) - set(self.qualifying_activity_ids)
                or set(names) - set(self.qualifying_activity_ids)
                or any(not key or not value for key, value in self.activity_locations)
                or any(not key or not value for key, value in self.activity_names)):
            raise ValueError("employment activity contract is invalid")
        provenance = (self.institution_id, self.formation_id, self.role_template_id)
        if any(provenance) and not all(provenance):
            raise ValueError("institution employment provenance is incomplete")

    def to_dict(self) -> dict:
        data = asdict(self)
        data["qualifying_activity_ids"] = list(self.qualifying_activity_ids)
        data["activity_locations"] = dict(self.activity_locations)
        data["activity_names"] = dict(self.activity_names)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Employment":
        values = dict(data)
        values["qualifying_activity_ids"] = tuple(
            values.get("qualifying_activity_ids", ())
        )
        values["activity_locations"] = tuple(sorted(
            values.get("activity_locations", {}).items()
        ))
        values["activity_names"] = tuple(sorted(
            values.get("activity_names", {}).items()
        ))
        return cls(**values)


class EconomySystem:
    """Own balances, employment, work eligibility, and the canonical ledger."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        accounts: list[EconomicAccount],
        employments: list[Employment],
        *,
        initial_total_currency: int | None = None,
        initial_balances: dict[str, int] | None = None,
        ledger: list[TransactionRecord] | None = None,
        applied_event_keys: set[str] | None = None,
        work_events: list[dict] | None = None,
        rejected_transactions: list[dict] | None = None,
        next_transaction_number: int = 1,
        wealth_need_gain: int = 4,
    ):
        account_ids = [account.id for account in accounts]
        if len(account_ids) != len(set(account_ids)):
            raise ValueError("economic account ids must be unique")
        employment_ids = [employment.id for employment in employments]
        if len(employment_ids) != len(set(employment_ids)):
            raise ValueError("employment ids must be unique")
        employed_agent_ids = [employment.agent_id for employment in employments]
        if len(employed_agent_ids) != len(set(employed_agent_ids)):
            raise ValueError("an agent may have only one employment")
        agent_owner_ids = [
            account.owner_id for account in accounts if account.owner_type == "agent"
        ]
        if len(agent_owner_ids) != len(set(agent_owner_ids)):
            raise ValueError("an agent may have only one economic account")

        self._accounts = {account.id: account for account in accounts}
        self.employments = {job.id: job for job in employments}
        self._employment_by_agent = {job.agent_id: job for job in employments}
        self.ledger = list(ledger or [])
        self.applied_event_keys = set(applied_event_keys or ())
        self.work_events = list(work_events or [])
        self.rejected_transactions = list(rejected_transactions or [])
        self.next_transaction_number = next_transaction_number
        self.wealth_need_gain = max(0, int(wealth_need_gain))
        total = sum(account.balance for account in accounts)
        self.initial_total_currency = (
            total if initial_total_currency is None else int(initial_total_currency)
        )
        self.initial_balances = (
            {account.id: account.balance for account in accounts}
            if initial_balances is None
            else {key: int(value) for key, value in initial_balances.items()}
        )
        if set(self.initial_balances) != set(self._accounts):
            raise ValueError("initial balances must match current account ids")
        if sum(self.initial_balances.values()) != self.initial_total_currency:
            raise ValueError("initial balances do not match initial total currency")
        self._validate_references()
        self._validate_ledger()

    @property
    def accounts(self) -> dict[str, EconomicAccount]:
        return dict(self._accounts)

    def get_account(self, account_id: str) -> EconomicAccount:
        try:
            return self._accounts[account_id]
        except KeyError as error:
            raise EconomyError("unknown_account", f"unknown account: {account_id}") from error

    def account_for_agent(self, agent_id: str) -> EconomicAccount:
        matches = [
            account for account in self._accounts.values()
            if account.owner_type == "agent" and account.owner_id == agent_id
        ]
        if len(matches) != 1:
            raise EconomyError(
                "unknown_agent_account",
                f"expected one account for agent: {agent_id}",
            )
        return matches[0]

    def employment_for_agent(self, agent_id: str) -> Employment | None:
        return self._employment_by_agent.get(agent_id)

    def can_register_agent_account(
        self,
        agent_id: str,
        account_id: str | None = None,
    ) -> bool:
        """Return whether a new zero-balance resident account can be registered."""
        account_id = account_id or f"account:agent:{agent_id}"
        if not agent_id or not account_id or account_id in self._accounts:
            return False
        return not any(
            account.owner_type == "agent" and account.owner_id == agent_id
            for account in self._accounts.values()
        )

    def register_agent_account(
        self,
        agent_id: str,
        account_id: str | None = None,
    ) -> EconomicAccount:
        """Register exactly one zero-balance account without changing currency."""
        account_id = account_id or f"account:agent:{agent_id}"
        existing = self._accounts.get(account_id)
        if existing is not None:
            if existing.owner_type == "agent" and existing.owner_id == agent_id:
                return existing
            raise EconomyError("duplicate_account", f"account id already exists: {account_id}")
        if not self.can_register_agent_account(agent_id, account_id):
            raise EconomyError(
                "duplicate_agent_account",
                f"agent already has an economic account: {agent_id}",
            )
        account = EconomicAccount(
            id=account_id,
            owner_type="agent",
            owner_id=agent_id,
            balance=0,
        )
        self._accounts[account.id] = account
        self.initial_balances[account.id] = 0
        return account

    def can_register_employer_account(
        self, institution_id: str, account_id: str,
    ) -> bool:
        """Check a new zero-baseline institution employer identity."""
        return bool(institution_id and account_id) and (
            account_id not in self._accounts
            and not any(
                account.owner_type == "institution"
                and account.owner_id == institution_id
                for account in self._accounts.values()
            )
        )

    def register_employer_account(
        self, institution_id: str, account_id: str,
    ) -> EconomicAccount:
        """Register one institution-owned account without minting currency."""
        if not self.can_register_employer_account(institution_id, account_id):
            raise EconomyError(
                "duplicate_employer_account",
                "institution employer account identity is already registered",
            )
        account = EconomicAccount(
            account_id, "institution", institution_id, 0,
        )
        self._accounts[account.id] = account
        self.initial_balances[account.id] = 0
        return account

    def can_register_employment(self, employment: Employment) -> bool:
        """Check one authoritative job against current account authority."""
        if (
            employment.id in self.employments
            or employment.agent_id in self._employment_by_agent
        ):
            return False
        try:
            self.account_for_agent(employment.agent_id)
            employer = self.get_account(employment.employer_account_id)
        except EconomyError:
            return False
        return (
            employer.owner_type == "institution"
            and employment.institution_id == employer.owner_id
            and bool(employment.activity_locations)
            and set(dict(employment.activity_locations))
            == set(employment.qualifying_activity_ids)
            and set(dict(employment.activity_names))
            == set(employment.qualifying_activity_ids)
        )

    def register_employment(self, employment: Employment) -> Employment:
        """Register one validated institution job without changing balances."""
        if not self.can_register_employment(employment):
            raise EconomyError(
                "invalid_employment_registration",
                "employment conflicts with current account or job authority",
            )
        self.employments[employment.id] = employment
        self._employment_by_agent[employment.agent_id] = employment
        return employment

    def _validate_references(self) -> None:
        for job in self.employments.values():
            if job.employer_account_id not in self._accounts:
                raise ValueError(
                    f"employment {job.id} references unknown employer account"
                )
            self.account_for_agent(job.agent_id)

    def _validate_ledger(self) -> None:
        if [item.id for item in self.ledger] != [
            f"txn-{index:08d}" for index in range(1, len(self.ledger) + 1)
        ]:
            raise ValueError("ledger identities are not monotonic")
        require_sequence(list(range(1, len(self.ledger) + 1)),
                         self.next_transaction_number, "ledger")
        transaction_ids = [transaction.id for transaction in self.ledger]
        if len(transaction_ids) != len(set(transaction_ids)):
            raise ValueError("transaction ids must be unique")
        event_keys = [
            transaction.event_key for transaction in self.ledger
            if transaction.event_key is not None
        ]
        if len(event_keys) != len(set(event_keys)):
            raise ValueError("successful transaction event keys must be unique")
        for transaction in self.ledger:
            if (
                transaction.source_account_id not in self._accounts
                or transaction.destination_account_id not in self._accounts
            ):
                raise ValueError("ledger references an unknown account")
            if transaction.source_account_id == transaction.destination_account_id:
                raise ValueError("ledger transaction uses the same account twice")
            if transaction.amount <= 0:
                raise ValueError("ledger transaction amount must be positive")
        if not set(event_keys).issubset(self.applied_event_keys):
            raise ValueError("ledger event keys are missing duplicate guards")
        if not self.conservation_holds() or not self.ledger_reconstructs_balances():
            raise ValueError("ledger does not reconstruct conserved account balances")

    def _reject(self, code: str, message: str, attempt: dict) -> None:
        self.rejected_transactions.append({"code": code, **attempt})
        raise EconomyError(code, message)

    def transfer(
        self,
        source_account_id: str,
        destination_account_id: str,
        amount: int,
        *,
        day: int,
        hour: int | None,
        transaction_type: str,
        reason: str,
        event_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TransactionRecord:
        """Atomically transfer integer currency and append one successful record."""
        attempt = {
            "day": day,
            "hour": hour,
            "source_account_id": source_account_id,
            "destination_account_id": destination_account_id,
            "amount": (
                amount
                if isinstance(amount, (int, float, str, bool)) or amount is None
                else repr(amount)
            ),
            "transaction_type": transaction_type,
            "event_key": event_key,
        }
        if source_account_id not in self._accounts:
            self._reject("unknown_source", "source account does not exist", attempt)
        if destination_account_id not in self._accounts:
            self._reject("unknown_destination", "destination account does not exist", attempt)
        if source_account_id == destination_account_id:
            self._reject("same_account", "source and destination must differ", attempt)
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            self._reject("invalid_amount", "amount must be a positive integer", attempt)
        if event_key and event_key in self.applied_event_keys:
            self._reject("duplicate_event", "economic event was already applied", attempt)

        source = self._accounts[source_account_id]
        destination = self._accounts[destination_account_id]
        if source.balance < amount:
            self._reject("insufficient_funds", "source has insufficient funds", attempt)

        record = TransactionRecord(
            id=f"txn-{self.next_transaction_number:08d}",
            day=int(day),
            hour=None if hour is None else int(hour),
            source_account_id=source_account_id,
            destination_account_id=destination_account_id,
            amount=amount,
            transaction_type=str(transaction_type),
            reason=str(reason),
            event_key=event_key,
            metadata=tuple(sorted((metadata or {}).items())),
        )
        # Every validation happens before these adjacent mutations.
        self._accounts[source_account_id] = replace(source, balance=source.balance - amount)
        self._accounts[destination_account_id] = replace(
            destination, balance=destination.balance + amount
        )
        self.ledger.append(record)
        if event_key:
            self.applied_event_keys.add(event_key)
        self.next_transaction_number += 1
        return record

    def process_activity(self, agent, activity, *, day: int, hour: int) -> TransactionRecord | None:
        """Pay one daily wage for exact, explicitly work-tagged job activity."""
        employment = self.employment_for_agent(agent.id)
        required_location = dict(
            employment.activity_locations
        ).get(activity.id) if employment is not None else None
        if (
            employment is None
            or not employment.active
            or day < employment.start_day
            or "work" not in activity.tags
            or activity.id not in employment.qualifying_activity_ids
            or (
                required_location is not None
                and activity.location_id != required_location
            )
        ):
            return None

        work_event_id = f"work:{employment.id}:{day}:{hour}:{activity.id}"
        wage_event_key = f"wage:{employment.id}:{day}"
        work_event = {
            "id": work_event_id,
            "day": day,
            "hour": hour,
            "agent_id": agent.id,
            "employment_id": employment.id,
            "activity_id": activity.id,
            "location_id": activity.location_id,
            "required_location_id": required_location,
            "institution_id": employment.institution_id,
            "formation_id": employment.formation_id,
            "role_template_id": employment.role_template_id,
            "eligible": True,
            "wage_event_key": wage_event_key,
            "payment_status": "pending",
        }
        if not any(event["id"] == work_event_id for event in self.work_events):
            self.work_events.append(work_event)

        destination = self.account_for_agent(agent.id)
        try:
            transaction = self.transfer(
                employment.employer_account_id,
                destination.id,
                employment.wage,
                day=day,
                hour=hour,
                transaction_type="wage",
                reason=f"Wage for {employment.title}",
                event_key=wage_event_key,
                metadata={
                    "agent_id": agent.id,
                    "employment_id": employment.id,
                    "work_event_id": work_event_id,
                    "activity_id": activity.id,
                    "location_id": activity.location_id,
                    "institution_id": employment.institution_id,
                },
            )
        except EconomyError as error:
            work_event["payment_status"] = f"rejected:{error.code}"
            return None

        work_event["payment_status"] = "paid"
        work_event["transaction_id"] = transaction.id
        agent.satisfy_need("wealth", self.wealth_need_gain)
        return transaction

    def total_currency(self) -> int:
        return sum(account.balance for account in self._accounts.values())

    def conservation_holds(self) -> bool:
        return self.total_currency() == self.initial_total_currency

    def ledger_reconstructs_balances(self) -> bool:
        reconstructed = Counter(self.initial_balances)
        for transaction in self.ledger:
            reconstructed[transaction.source_account_id] -= transaction.amount
            reconstructed[transaction.destination_account_id] += transaction.amount
        return (
            set(reconstructed) == set(self._accounts)
            and all(
                reconstructed[account_id] == account.balance
                for account_id, account in self._accounts.items()
            )
        )

    def diagnostics(self) -> dict:
        transaction_counts = Counter(
            transaction.transaction_type for transaction in self.ledger
        )
        wage_transactions = [
            transaction for transaction in self.ledger
            if transaction.transaction_type == "wage"
        ]
        wage_work_ids = [dict(transaction.metadata).get("work_event_id") for transaction in wage_transactions]
        eligible_ids = {
            event["id"] for event in self.work_events if event.get("eligible")
        }
        return {
            "total_currency": self.total_currency(),
            "initial_total_currency": self.initial_total_currency,
            "initial_balances": self.initial_balances,
            "balances": {
                account_id: account.balance
                for account_id, account in sorted(self._accounts.items())
            },
            "agent_balances": {
                account.owner_id: account.balance
                for account in sorted(self._accounts.values(), key=lambda item: item.owner_id)
                if account.owner_type == "agent"
            },
            "successful_transaction_count": len(self.ledger),
            "transaction_counts_by_type": dict(sorted(transaction_counts.items())),
            "wages_paid": sum(transaction.amount for transaction in wage_transactions),
            "wage_payment_count": len(wage_transactions),
            "agents_employed": sum(job.active for job in self.employments.values()),
            "rejected_transaction_count": len(self.rejected_transactions),
            "rejection_counts_by_code": dict(sorted(Counter(
                attempt["code"] for attempt in self.rejected_transactions
            ).items())),
            "no_negative_balances": all(
                account.balance >= 0 for account in self._accounts.values()
            ),
            "currency_conserved": self.conservation_holds(),
            "ledger_reconstructs_balances": self.ledger_reconstructs_balances(),
            "all_wages_have_work_events": all(
                work_id in eligible_ids for work_id in wage_work_ids
            ),
            "duplicate_wage_event_keys": len({
                transaction.event_key for transaction in wage_transactions
            }) != len(wage_transactions),
        }

    def to_dict(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "initial_total_currency": self.initial_total_currency,
            "initial_balances": self.initial_balances,
            "wealth_need_gain": self.wealth_need_gain,
            "next_transaction_number": self.next_transaction_number,
            "accounts": [asdict(account) for account in self._accounts.values()],
            "employments": [job.to_dict() for job in self.employments.values()],
            "ledger": [transaction.to_dict() for transaction in self.ledger],
            "applied_event_keys": sorted(self.applied_event_keys),
            "work_events": self.work_events,
            "rejected_transactions": self.rejected_transactions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EconomySystem":
        version = data.get("schema_version", 1)
        if type(version) is not int or version != cls.SCHEMA_VERSION:
            raise ValueError("unsupported economy schema version")
        return cls(
            accounts=[EconomicAccount(**item) for item in data.get("accounts", [])],
            employments=[Employment.from_dict(item) for item in data.get("employments", [])],
            initial_total_currency=data.get("initial_total_currency"),
            initial_balances=data.get("initial_balances"),
            ledger=[TransactionRecord.from_dict(item) for item in data.get("ledger", [])],
            applied_event_keys=set(data.get("applied_event_keys", [])),
            work_events=data.get("work_events", []),
            rejected_transactions=data.get("rejected_transactions", []),
            next_transaction_number=data.get("next_transaction_number", 1),
            wealth_need_gain=data.get("wealth_need_gain", 4),
        )

    @classmethod
    def from_config(cls, path: str | Path, agents: list) -> "EconomySystem":
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        agent_ids = {agent.id for agent in agents}
        accounts = [EconomicAccount(**item) for item in config.get("system_accounts", [])]
        starting_balance = config.get("agent_starting_balance", 0)
        for agent in agents:
            accounts.append(EconomicAccount(
                id=f"account:agent:{agent.id}",
                owner_type="agent",
                owner_id=agent.id,
                balance=starting_balance,
            ))
        employments = [
            Employment.from_dict(item)
            for item in config.get("employments", [])
            if item.get("agent_id") in agent_ids
        ]
        return cls(
            accounts=accounts,
            employments=employments,
            wealth_need_gain=config.get("wealth_need_gain", 4),
        )
