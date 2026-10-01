"""Bounded, deterministic authority for resident migration lifecycle state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re

from src.systems.economy import EconomyError, EconomySystem


MIGRATION_STATUSES = {"proposed", "activated", "rejected"}
REVIEW_STATUSES = {"waiting", "proposed", "activated", "rejected"}


@dataclass(frozen=True)
class TownGrowthPolicy:
    resident_capacity: int
    earliest_migration_day: int
    review_interval_days: int
    migration_cooldown_days: int
    arrival_location_id: str
    settlement_source_account_id: str
    settlement_grant: int
    recent_activity_window_days: int
    minimum_active_residents_per_day: int

    def __post_init__(self) -> None:
        integer_fields = (
            "resident_capacity", "earliest_migration_day", "review_interval_days",
            "migration_cooldown_days", "settlement_grant",
            "recent_activity_window_days", "minimum_active_residents_per_day",
        )
        if any(
            isinstance(getattr(self, name), bool)
            or not isinstance(getattr(self, name), int)
            or getattr(self, name) < (0 if name == "migration_cooldown_days" else 1)
            for name in integer_fields
        ):
            raise ValueError("town growth policy values must be bounded integers")
        if not self.arrival_location_id or not self.settlement_source_account_id:
            raise ValueError("town growth location and settlement account are required")


@dataclass(frozen=True)
class ResidentTemplate:
    id: str
    name: str
    personality: str
    goals: tuple[str, ...]
    initial_needs: tuple[tuple[str, int], ...]
    initial_location_policy: str = "arrival_location"

    def __post_init__(self) -> None:
        if not self.id or not self.name or not self.personality:
            raise ValueError("resident template identity and personality are required")
        if self.initial_location_policy != "arrival_location":
            raise ValueError("unsupported resident initial location policy")
        if not self.goals or any(not isinstance(item, str) or not item.strip() for item in self.goals):
            raise ValueError("resident template goals must be non-empty strings")
        needs = dict(self.initial_needs)
        if set(needs) != {"social", "wealth", "knowledge"} or any(
            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100
            for value in needs.values()
        ):
            raise ValueError("resident template needs must define bounded core needs")

    @classmethod
    def from_dict(cls, data: dict) -> "ResidentTemplate":
        allowed = {
            "id", "name", "personality", "goals", "initial_needs",
            "initial_location_policy",
        }
        if set(data) - allowed:
            raise ValueError("resident template contains unsupported fields")
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            personality=data.get("personality", ""),
            goals=tuple(data.get("goals", ())),
            initial_needs=tuple(sorted(data.get("initial_needs", {}).items())),
            initial_location_policy=data.get(
                "initial_location_policy", "arrival_location"
            ),
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["goals"] = list(self.goals)
        data["initial_needs"] = dict(self.initial_needs)
        return data


@dataclass
class MigrationReview:
    event_key: str
    day: int
    status: str
    reason: str
    migration_id: str | None = None
    template_id: str | None = None
    agent_id: str | None = None

    def __post_init__(self) -> None:
        if not self.event_key or self.status not in REVIEW_STATUSES:
            raise ValueError("invalid migration review")


@dataclass
class MigrationRecord:
    id: str
    event_key: str
    template_id: str
    agent_id: str
    review_day: int
    arrival_location_id: str
    status: str = "proposed"
    reason: str = "eligible"
    activation_day: int | None = None
    settlement_transaction_id: str | None = None

    def __post_init__(self) -> None:
        if (
            not self.id or not self.event_key or not self.template_id
            or not self.agent_id or not self.arrival_location_id
            or self.status not in MIGRATION_STATUSES
        ):
            raise ValueError("invalid migration record")
        if self.status == "activated" and (
            self.activation_day is None or not self.settlement_transaction_id
        ):
            raise ValueError("activated migration requires activation proof")
        if self.status != "activated" and (
            self.activation_day is not None or self.settlement_transaction_id is not None
        ):
            raise ValueError("non-activated migration cannot claim activation proof")


class TownGrowthSystem:
    """Own migration eligibility, stable proposals, records, and public history."""

    SCHEMA_VERSION = 1
    REVIEW_HISTORY_LIMIT = 128
    PUBLIC_HISTORY_LIMIT = 50

    def __init__(
        self,
        policy: TownGrowthPolicy,
        templates: list[ResidentTemplate],
        *,
        next_migration_sequence: int = 1,
        next_resident_sequence: int = 1,
        review_history: list[MigrationReview] | None = None,
        migration_records: list[MigrationRecord] | None = None,
        last_successful_activation_day: int | None = None,
        processed_event_keys: set[str] | None = None,
        consumed_template_ids: set[str] | None = None,
        public_history: list[dict] | None = None,
    ):
        if len({item.id for item in templates}) != len(templates):
            raise ValueError("resident template ids must be unique")
        if len({item.name for item in templates}) != len(templates):
            raise ValueError("resident template names must be unique")
        self.policy = policy
        self.templates = {item.id: item for item in templates}
        self.next_migration_sequence = max(1, int(next_migration_sequence))
        self.next_resident_sequence = max(1, int(next_resident_sequence))
        self.review_history = list(review_history or [])[-self.REVIEW_HISTORY_LIMIT:]
        self.migration_records = list(migration_records or [])
        self.last_successful_activation_day = last_successful_activation_day
        self.processed_event_keys = set(processed_event_keys or ())
        self.consumed_template_ids = set(consumed_template_ids or ())
        self.public_history = list(public_history or [])[-self.PUBLIC_HISTORY_LIMIT:]
        self._validate_state()

    def _validate_state(self) -> None:
        migration_ids = [item.id for item in self.migration_records]
        agent_ids = [item.agent_id for item in self.migration_records]
        if len(migration_ids) != len(set(migration_ids)):
            raise ValueError("migration ids must be unique")
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("migration resident ids must be unique")
        if any(item.template_id not in self.templates for item in self.migration_records):
            raise ValueError("migration record references unknown template")
        if not self.consumed_template_ids.issubset(self.templates):
            raise ValueError("consumed migration template is unknown")
        activated_templates = {
            item.template_id for item in self.migration_records
            if item.status == "activated"
        }
        if not activated_templates.issubset(self.consumed_template_ids):
            raise ValueError("activated templates must be consumed")
        if any(item.event_key not in self.processed_event_keys for item in self.review_history):
            raise ValueError("migration review is missing replay guard")
        if len({item.event_key for item in self.review_history}) != len(self.review_history):
            raise ValueError("migration review event keys must be unique")
        if any(
            entry.get("migration_id") not in migration_ids
            or not entry.get("event_key")
            for entry in self.public_history
        ):
            raise ValueError("public migration history is invalid")

    @staticmethod
    def _safe_next_resident_sequence(agents: list) -> int:
        numeric_ids = []
        for agent in agents:
            match = re.fullmatch(r"agent_(\d+)", str(agent.id))
            if match:
                numeric_ids.append(int(match.group(1)))
        return max(numeric_ids, default=0) + 1

    @classmethod
    def from_config(
        cls,
        path: str | Path,
        agents: list,
        state: dict | None = None,
    ) -> "TownGrowthSystem":
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        policy = TownGrowthPolicy(**config["policy"])
        templates = [ResidentTemplate.from_dict(item) for item in config["templates"]]
        if state is None:
            existing_names = {agent.name for agent in agents}
            return cls(
                policy,
                templates,
                next_resident_sequence=cls._safe_next_resident_sequence(agents),
                consumed_template_ids={
                    item.id for item in templates if item.name in existing_names
                },
            )
        version = state.get("schema_version", 1)
        if version != cls.SCHEMA_VERSION:
            raise ValueError("unsupported town growth schema version")
        system = cls(
            policy,
            templates,
            next_migration_sequence=state.get("next_migration_sequence", 1),
            next_resident_sequence=state.get(
                "next_resident_sequence", cls._safe_next_resident_sequence(agents)
            ),
            review_history=[
                MigrationReview(**item) for item in state.get("review_history", [])
            ],
            migration_records=[
                MigrationRecord(**item) for item in state.get("migration_records", [])
            ],
            last_successful_activation_day=state.get(
                "last_successful_activation_day"
            ),
            processed_event_keys=set(state.get("processed_event_keys", [])),
            consumed_template_ids=set(state.get("consumed_template_ids", [])),
            public_history=state.get("public_history", []),
        )
        existing_ids = {agent.id for agent in agents}
        system.next_resident_sequence = max(
            system.next_resident_sequence,
            cls._safe_next_resident_sequence(agents),
        )
        while f"agent_{system.next_resident_sequence:03d}" in existing_ids:
            system.next_resident_sequence += 1
        return system

    def to_dict(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "next_migration_sequence": self.next_migration_sequence,
            "next_resident_sequence": self.next_resident_sequence,
            "review_history": [asdict(item) for item in self.review_history],
            "migration_records": [asdict(item) for item in self.migration_records],
            "last_successful_activation_day": self.last_successful_activation_day,
            "processed_event_keys": sorted(self.processed_event_keys),
            "consumed_template_ids": sorted(self.consumed_template_ids),
            "public_history": list(self.public_history),
        }

    def template(self, template_id: str) -> ResidentTemplate:
        try:
            return self.templates[template_id]
        except KeyError as error:
            raise ValueError("migration record references unknown template") from error

    def pending_migration(self) -> MigrationRecord | None:
        return next(
            (item for item in self.migration_records if item.status == "proposed"),
            None,
        )

    def _record_review(self, review: MigrationReview) -> MigrationReview:
        self.review_history.append(review)
        self.review_history = self.review_history[-self.REVIEW_HISTORY_LIMIT:]
        self.processed_event_keys.add(review.event_key)
        return review

    def _waiting(self, event_key: str, day: int, reason: str) -> MigrationReview:
        return self._record_review(MigrationReview(event_key, day, "waiting", reason))

    def _activity_gate_passes(
        self,
        day: int,
        activity_records: list[dict],
        registered_agent_ids: set[str],
    ) -> bool:
        first_day = day - self.policy.recent_activity_window_days + 1
        if first_day < 1:
            return False
        for activity_day in range(first_day, day + 1):
            active = {
                record.get("agent_id")
                for record in activity_records
                if record.get("type") == "activity"
                and record.get("day") == activity_day
                and record.get("agent_id") in registered_agent_ids
            }
            if len(active) < self.policy.minimum_active_residents_per_day:
                return False
        return True

    def review(
        self,
        *,
        day: int,
        agents: list,
        locations: list,
        activity_records: list[dict],
        economy: EconomySystem,
    ) -> MigrationReview:
        """Perform one scheduled, replay-safe readiness review."""
        pending = self.pending_migration()
        if pending is not None:
            return MigrationReview(
                pending.event_key, pending.review_day, "proposed", "pending_activation",
                pending.id, pending.template_id, pending.agent_id,
            )
        event_key = f"migration-review:day:{int(day)}"
        existing = next(
            (item for item in self.review_history if item.event_key == event_key),
            None,
        )
        if existing is not None:
            return existing
        if len(agents) >= self.policy.resident_capacity:
            return self._waiting(event_key, day, "resident_capacity_reached")
        if day < self.policy.earliest_migration_day:
            return self._waiting(event_key, day, "before_earliest_migration_day")
        if (
            day - self.policy.earliest_migration_day
        ) % self.policy.review_interval_days:
            return self._waiting(event_key, day, "outside_review_schedule")
        if (
            self.last_successful_activation_day is not None
            and day - self.last_successful_activation_day
            < self.policy.migration_cooldown_days
        ):
            return self._waiting(event_key, day, "migration_cooldown")
        if self.policy.arrival_location_id not in {item.id for item in locations}:
            return self._waiting(event_key, day, "invalid_arrival_location")
        try:
            source = economy.get_account(self.policy.settlement_source_account_id)
        except EconomyError:
            return self._waiting(event_key, day, "unknown_settlement_account")
        if source.balance < self.policy.settlement_grant:
            return self._waiting(event_key, day, "insufficient_settlement_funds")
        registered_ids = {agent.id for agent in agents}
        if not self._activity_gate_passes(
            day, activity_records, registered_ids
        ):
            return self._waiting(event_key, day, "insufficient_sustained_activity")
        candidate = next(
            (
                item for item in self.templates.values()
                if item.id not in self.consumed_template_ids
                and all(record.template_id != item.id for record in self.migration_records)
            ),
            None,
        )
        if candidate is None:
            return self._waiting(event_key, day, "resident_templates_exhausted")
        if candidate.name in {agent.name for agent in agents}:
            return self._waiting(event_key, day, "duplicate_resident_name")

        migration_id = f"migration:{self.next_migration_sequence:04d}"
        self.next_migration_sequence += 1
        while True:
            agent_id = f"agent_{self.next_resident_sequence:03d}"
            self.next_resident_sequence += 1
            if agent_id not in registered_ids:
                break
        record = MigrationRecord(
            id=migration_id,
            event_key=event_key,
            template_id=candidate.id,
            agent_id=agent_id,
            review_day=int(day),
            arrival_location_id=self.policy.arrival_location_id,
        )
        self.migration_records.append(record)
        return self._record_review(MigrationReview(
            event_key, int(day), "proposed", "eligible", migration_id,
            candidate.id, agent_id,
        ))

    def reject(self, migration_id: str, reason: str) -> None:
        record = next(item for item in self.migration_records if item.id == migration_id)
        if record.status == "activated":
            raise ValueError("activated migration cannot be rejected")
        record.status = "rejected"
        record.reason = str(reason)[:160]
        review = next(
            item for item in self.review_history if item.migration_id == migration_id
        )
        review.status = "rejected"
        review.reason = record.reason

    def activate(
        self,
        migration_id: str,
        *,
        day: int,
        settlement_transaction_id: str,
    ) -> MigrationRecord:
        record = next(item for item in self.migration_records if item.id == migration_id)
        if record.status == "activated":
            return record
        if record.status != "proposed" or not settlement_transaction_id:
            raise ValueError("migration is not eligible for activation")
        record.status = "activated"
        record.reason = "activated"
        record.activation_day = int(day)
        record.settlement_transaction_id = settlement_transaction_id
        self.consumed_template_ids.add(record.template_id)
        self.last_successful_activation_day = int(day)
        review = next(
            item for item in self.review_history if item.migration_id == migration_id
        )
        review.status = "activated"
        review.reason = "activated"
        self.public_history.append({
            "event_key": f"migration-arrival:{record.id}",
            "migration_id": record.id,
            "agent_id": record.agent_id,
            "template_id": record.template_id,
            "day": int(day),
            "location_id": record.arrival_location_id,
        })
        self.public_history = self.public_history[-self.PUBLIC_HISTORY_LIMIT:]
        return record

