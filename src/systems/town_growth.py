"""Bounded, deterministic authority for resident migration lifecycle state."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from src.systems.economy import EconomyError, EconomySystem


MIGRATION_STATUSES = {"proposed", "activated", "rejected"}
REVIEW_STATUSES = {"waiting", "proposed", "activated", "rejected"}
MIGRATION_ID_PATTERN = re.compile(r"migration:(\d{4,})")
AGENT_ID_PATTERN = re.compile(r"agent_(\d{3,})")


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, field_name)


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
        if (
            not isinstance(self.arrival_location_id, str)
            or not self.arrival_location_id
            or not isinstance(self.settlement_source_account_id, str)
            or not self.settlement_source_account_id
        ):
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
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.id, self.name, self.personality)
        ):
            raise ValueError("resident template identity and personality are required")
        if self.initial_location_policy != "arrival_location":
            raise ValueError("unsupported resident initial location policy")
        if not self.goals or any(
            not isinstance(item, str) or not item.strip() for item in self.goals
        ):
            raise ValueError("resident template goals must be non-empty strings")
        needs = dict(self.initial_needs)
        if len(self.initial_needs) != 3 or set(needs) != {
            "social", "wealth", "knowledge"
        } or any(
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
        if (
            not isinstance(self.event_key, str)
            or not self.event_key
            or self.status not in REVIEW_STATUSES
            or not isinstance(self.reason, str)
            or not self.reason
        ):
            raise ValueError("invalid migration review")
        _positive_int(self.day, "migration review day")
        if self.event_key != f"migration-review:day:{self.day}":
            raise ValueError("migration review event key and day disagree")
        proposal_fields = (self.migration_id, self.template_id, self.agent_id)
        if self.status == "waiting" and any(item is not None for item in proposal_fields):
            raise ValueError("waiting migration review cannot claim a proposal")
        if self.status != "waiting" and any(
            not isinstance(item, str) or not item for item in proposal_fields
        ):
            raise ValueError("migration proposal review requires stable identities")


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
            not isinstance(self.id, str)
            or MIGRATION_ID_PATTERN.fullmatch(self.id) is None
            or not isinstance(self.event_key, str) or not self.event_key
            or not isinstance(self.template_id, str) or not self.template_id
            or not isinstance(self.agent_id, str)
            or AGENT_ID_PATTERN.fullmatch(self.agent_id) is None
            or not isinstance(self.arrival_location_id, str)
            or not self.arrival_location_id
            or self.status not in MIGRATION_STATUSES
            or not isinstance(self.reason, str) or not self.reason
        ):
            raise ValueError("invalid migration record")
        self.review_day = _positive_int(self.review_day, "migration review day")
        self.activation_day = _optional_positive_int(
            self.activation_day, "migration activation day"
        )
        if self.event_key != f"migration-review:day:{self.review_day}":
            raise ValueError("migration event key and review day disagree")
        if self.activation_day is not None and self.activation_day < self.review_day:
            raise ValueError("migration cannot activate before review")
        if self.status == "activated" and (
            self.activation_day is None
            or not isinstance(self.settlement_transaction_id, str)
            or not self.settlement_transaction_id
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
        self.next_migration_sequence = _positive_int(
            next_migration_sequence, "next migration sequence"
        )
        self.next_resident_sequence = _positive_int(
            next_resident_sequence, "next resident sequence"
        )
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
        event_keys = [item.event_key for item in self.migration_records]
        if len(migration_ids) != len(set(migration_ids)):
            raise ValueError("migration ids must be unique")
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("migration resident ids must be unique")
        if len(event_keys) != len(set(event_keys)):
            raise ValueError("migration event keys must be unique")
        if any(item.template_id not in self.templates for item in self.migration_records):
            raise ValueError("migration record references unknown template")
        if not self.consumed_template_ids.issubset(self.templates):
            raise ValueError("consumed migration template is unknown")
        activated_templates = {
            item.template_id for item in self.migration_records
            if item.status == "activated"
        }
        activated_template_ids = [
            item.template_id for item in self.migration_records
            if item.status == "activated"
        ]
        if len(activated_template_ids) != len(set(activated_template_ids)):
            raise ValueError("resident template may activate only once")
        if not activated_templates.issubset(self.consumed_template_ids):
            raise ValueError("activated templates must be consumed")
        if sum(item.status == "proposed" for item in self.migration_records) > 1:
            raise ValueError("only one migration proposal may be pending")
        if any(
            item.status == "proposed" and item.template_id in self.consumed_template_ids
            for item in self.migration_records
        ):
            raise ValueError("consumed resident template cannot remain proposed")
        if any(
            not isinstance(item, str) or not item
            for item in self.processed_event_keys | self.consumed_template_ids
        ):
            raise ValueError("town growth replay identities must be strings")
        if any(item.event_key not in self.processed_event_keys for item in self.review_history):
            raise ValueError("migration review is missing replay guard")
        if any(item.event_key not in self.processed_event_keys for item in self.migration_records):
            raise ValueError("migration record is missing replay guard")
        if len({item.event_key for item in self.review_history}) != len(self.review_history):
            raise ValueError("migration review event keys must be unique")
        records_by_id = {item.id: item for item in self.migration_records}
        for review in self.review_history:
            if review.status == "waiting":
                continue
            record = records_by_id.get(review.migration_id)
            if record is None or (
                review.event_key != record.event_key
                or review.template_id != record.template_id
                or review.agent_id != record.agent_id
                or review.day != record.review_day
                or review.status != record.status
            ):
                raise ValueError("migration review and record disagree")
        if any(
            not isinstance(entry, dict)
            or entry.get("migration_id") not in records_by_id
            or records_by_id[entry.get("migration_id")].status != "activated"
            or entry.get("event_key")
            != f"migration-arrival:{entry.get('migration_id')}"
            or entry.get("agent_id")
            != records_by_id[entry.get("migration_id")].agent_id
            or entry.get("template_id")
            != records_by_id[entry.get("migration_id")].template_id
            or entry.get("day")
            != records_by_id[entry.get("migration_id")].activation_day
            or entry.get("location_id")
            != records_by_id[entry.get("migration_id")].arrival_location_id
            for entry in self.public_history
        ):
            raise ValueError("public migration history is invalid")
        expected_public_ids = [
            item.id for item in self.migration_records if item.status == "activated"
        ][-self.PUBLIC_HISTORY_LIMIT:]
        if [entry["migration_id"] for entry in self.public_history] != expected_public_ids:
            raise ValueError("activated migrations require bounded public history")
        if len(self.public_history) != len({
            entry["migration_id"] for entry in self.public_history
        }):
            raise ValueError("public migration history must be unique")
        activation_days = [
            item.activation_day for item in self.migration_records
            if item.status == "activated"
        ]
        if activation_days:
            if self.last_successful_activation_day != max(activation_days):
                raise ValueError("last migration activation day is inconsistent")
        elif self.last_successful_activation_day is not None:
            raise ValueError("last migration activation day lacks an activated record")

    @staticmethod
    def _safe_next_resident_sequence(agents: list) -> int:
        numeric_ids = []
        for agent in agents:
            match = AGENT_ID_PATTERN.fullmatch(str(agent.id))
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
        if (
            not isinstance(config, dict)
            or set(config) - {
                "policy", "templates", "location_growth", "event_ecology",
            }
            or not {"policy", "templates"}.issubset(config)
        ):
            raise ValueError("town growth config has an invalid schema")
        if not isinstance(config["policy"], dict) or not isinstance(config["templates"], list):
            raise ValueError("town growth policy and templates have invalid shapes")
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
        if not isinstance(state, dict):
            raise ValueError("town growth state must be an object")
        version = state.get("schema_version")
        if version != cls.SCHEMA_VERSION:
            raise ValueError("unsupported town growth schema version")
        collection_fields = (
            "review_history", "migration_records", "processed_event_keys",
            "consumed_template_ids", "public_history",
        )
        if any(
            key in state and not isinstance(state[key], list)
            for key in collection_fields
        ):
            raise ValueError("town growth state collections must be lists")
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
        migration_sequences = [
            int(MIGRATION_ID_PATTERN.fullmatch(item.id).group(1))
            for item in system.migration_records
        ]
        resident_sequences = [
            int(AGENT_ID_PATTERN.fullmatch(item.agent_id).group(1))
            for item in system.migration_records
        ]
        system.next_migration_sequence = max(
            system.next_migration_sequence,
            max(migration_sequences, default=0) + 1,
        )
        system.next_resident_sequence = max(
            system.next_resident_sequence,
            cls._safe_next_resident_sequence(agents),
            max(resident_sequences, default=0) + 1,
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
        day = _positive_int(day, "migration review day")
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
        if event_key in self.processed_event_keys:
            return MigrationReview(
                event_key, int(day), "waiting", "review_already_processed"
            )
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
            ),
            None,
        )
        if candidate is None:
            return self._waiting(event_key, day, "resident_templates_exhausted")
        if candidate.name in {agent.name for agent in agents}:
            return self._waiting(event_key, day, "duplicate_resident_name")

        registered_migration_ids = {item.id for item in self.migration_records}
        while True:
            migration_id = f"migration:{self.next_migration_sequence:04d}"
            self.next_migration_sequence += 1
            if migration_id not in registered_migration_ids:
                break
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
