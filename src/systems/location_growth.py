"""Bounded deterministic authority for activating configured public places."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from src.town.location import Location


KNOWN_LOCATION_AFFINITIES = {"social", "knowledge", "community"}
ACTIVATION_ID_PATTERN = re.compile(r"location-activation:(\d{4,})")
REVIEW_STATUSES = {"waiting", "proposed", "activated", "rejected"}
ACTIVATION_STATUSES = {"proposed", "activated", "rejected"}


def _positive_int(value: object, name: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be a bounded integer")
    return value


@dataclass(frozen=True)
class LocationGrowthPolicy:
    location_capacity: int
    minimum_resident_population: int
    earliest_development_day: int
    review_interval_days: int
    development_cooldown_days: int
    recent_activity_window_days: int
    minimum_active_residents_per_day: int

    def __post_init__(self) -> None:
        for name in (
            "location_capacity", "minimum_resident_population",
            "earliest_development_day", "review_interval_days",
            "recent_activity_window_days", "minimum_active_residents_per_day",
        ):
            _positive_int(getattr(self, name), name)
        _positive_int(
            self.development_cooldown_days,
            "development_cooldown_days",
            allow_zero=True,
        )


@dataclass(frozen=True)
class LocationTemplate:
    id: str
    location_id: str
    name: str
    description: str
    affinities: tuple[str, ...]

    def __post_init__(self) -> None:
        values = (self.id, self.location_id, self.name, self.description)
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("location template identity and description are required")
        if not self.affinities or len(self.affinities) != len(set(self.affinities)):
            raise ValueError("location template affinities must be non-empty and unique")
        if any(item not in KNOWN_LOCATION_AFFINITIES for item in self.affinities):
            raise ValueError("location template contains an unknown affinity")

    @classmethod
    def from_dict(cls, data: dict) -> "LocationTemplate":
        allowed = {"id", "location_id", "name", "description", "affinities"}
        if not isinstance(data, dict) or set(data) != allowed:
            raise ValueError("location template has an invalid schema")
        affinities = data.get("affinities")
        if not isinstance(affinities, list):
            raise ValueError("location template affinities must be a list")
        return cls(
            id=data.get("id", ""), location_id=data.get("location_id", ""),
            name=data.get("name", ""), description=data.get("description", ""),
            affinities=tuple(affinities),
        )


@dataclass
class DevelopmentReview:
    event_key: str
    day: int
    status: str
    reason: str
    activation_id: str | None = None
    template_id: str | None = None

    def __post_init__(self) -> None:
        _positive_int(self.day, "development review day")
        if self.event_key != f"location-review:day:{self.day}":
            raise ValueError("development review identity disagrees with day")
        if self.status not in REVIEW_STATUSES or not self.reason:
            raise ValueError("invalid development review")
        if self.status == "waiting" and (self.activation_id or self.template_id):
            raise ValueError("waiting review cannot claim an activation")
        if self.status != "waiting" and not (self.activation_id and self.template_id):
            raise ValueError("development proposal requires stable identities")


@dataclass
class LocationActivationRecord:
    id: str
    event_key: str
    template_id: str
    location_id: str
    review_day: int
    status: str = "proposed"
    reason: str = "eligible"
    activation_day: int | None = None

    def __post_init__(self) -> None:
        _positive_int(self.review_day, "location review day")
        if (
            ACTIVATION_ID_PATTERN.fullmatch(self.id or "") is None
            or self.event_key != f"location-review:day:{self.review_day}"
            or not self.template_id or not self.location_id
            or self.status not in ACTIVATION_STATUSES or not self.reason
        ):
            raise ValueError("invalid location activation record")
        if self.status == "activated":
            _positive_int(self.activation_day, "location activation day")
            if self.activation_day < self.review_day:
                raise ValueError("location cannot activate before review")
        elif self.activation_day is not None:
            raise ValueError("inactive location record cannot claim activation")


class LocationGrowthSystem:
    """Own finite templates, reviews, activation evidence, and public history."""

    SCHEMA_VERSION = 1
    REVIEW_HISTORY_LIMIT = 128
    ACTIVATION_HISTORY_LIMIT = 128
    PUBLIC_HISTORY_LIMIT = 50

    def __init__(
        self, policy: LocationGrowthPolicy, templates: list[LocationTemplate],
        base_locations: list[Location], *, next_activation_sequence: int = 1,
        review_history: list[DevelopmentReview] | None = None,
        activation_records: list[LocationActivationRecord] | None = None,
        processed_event_keys: set[str] | None = None,
        consumed_template_ids: set[str] | None = None,
        last_activation_day: int | None = None,
        last_review_day: int | None = None,
        public_history: list[dict] | None = None,
    ):
        if len({item.id for item in templates}) != len(templates):
            raise ValueError("location template ids must be unique")
        if len({item.location_id for item in templates}) != len(templates):
            raise ValueError("location template location ids must be unique")
        if len({item.name for item in templates}) != len(templates):
            raise ValueError("location template names must be unique")
        base_ids = [item.id for item in base_locations]
        base_names = [item.name for item in base_locations]
        if len(base_ids) != len(set(base_ids)) or len(base_names) != len(set(base_names)):
            raise ValueError("base location identities must be unique")
        if any(item.location_id in base_ids or item.name in base_names for item in templates):
            raise ValueError("location template conflicts with a base location")
        self.policy = policy
        self.templates = {item.id: item for item in templates}
        self.base_location_ids = tuple(base_ids)
        self.base_location_names = tuple(base_names)
        self.next_activation_sequence = _positive_int(
            next_activation_sequence, "next location activation sequence"
        )
        self.review_history = list(review_history or [])[-self.REVIEW_HISTORY_LIMIT:]
        self.activation_records = list(activation_records or [])
        self.processed_event_keys = set(processed_event_keys or ())
        self.consumed_template_ids = set(consumed_template_ids or ())
        self.last_activation_day = last_activation_day
        self.last_review_day = last_review_day
        self.public_history = list(public_history or [])[-self.PUBLIC_HISTORY_LIMIT:]
        self._validate_state()

    @classmethod
    def from_config(cls, path: str | Path, base_locations: list[Location], state=None):
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        section = config.get("location_growth") if isinstance(config, dict) else None
        if not isinstance(section, dict) or set(section) != {"policy", "templates"}:
            raise ValueError("location growth config has an invalid schema")
        if not isinstance(section["policy"], dict) or not isinstance(section["templates"], list):
            raise ValueError("location growth policy and templates have invalid shapes")
        policy = LocationGrowthPolicy(**section["policy"])
        templates = [LocationTemplate.from_dict(item) for item in section["templates"]]
        if state is None:
            return cls(policy, templates, base_locations)
        if not isinstance(state, dict) or state.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("unsupported location growth schema version")
        allowed_state = {
            "schema_version", "next_activation_sequence", "review_history",
            "activation_records", "processed_event_keys", "consumed_template_ids",
            "last_activation_day", "public_history",
            "last_review_day",
        }
        if set(state) - allowed_state:
            raise ValueError("location growth state contains unsupported fields")
        collections = (
            "review_history", "activation_records", "processed_event_keys",
            "consumed_template_ids", "public_history",
        )
        if any(key in state and not isinstance(state[key], list) for key in collections):
            raise ValueError("location growth state collections must be lists")
        system = cls(
            policy, templates, base_locations,
            next_activation_sequence=state.get("next_activation_sequence", 1),
            review_history=[DevelopmentReview(**x) for x in state.get("review_history", [])],
            activation_records=[LocationActivationRecord(**x) for x in state.get("activation_records", [])],
            processed_event_keys=set(state.get("processed_event_keys", [])),
            consumed_template_ids=set(state.get("consumed_template_ids", [])),
            last_activation_day=state.get("last_activation_day"),
            last_review_day=state.get("last_review_day"),
            public_history=state.get("public_history", []),
        )
        sequences = [int(ACTIVATION_ID_PATTERN.fullmatch(x.id).group(1)) for x in system.activation_records]
        system.next_activation_sequence = max(
            system.next_activation_sequence, max(sequences, default=0) + 1
        )
        return system

    def to_dict(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "next_activation_sequence": self.next_activation_sequence,
            "review_history": [asdict(x) for x in self.review_history],
            "activation_records": [asdict(x) for x in self.activation_records],
            "processed_event_keys": sorted(self.processed_event_keys),
            "consumed_template_ids": sorted(self.consumed_template_ids),
            "last_activation_day": self.last_activation_day,
            "last_review_day": self.last_review_day,
            "public_history": list(self.public_history),
        }

    def template(self, template_id: str) -> LocationTemplate:
        try:
            return self.templates[template_id]
        except KeyError as error:
            raise ValueError("location activation references unknown template") from error

    def activated_locations(self) -> list[Location]:
        return [
            Location(
                self.template(record.template_id).location_id,
                self.template(record.template_id).name,
                self.template(record.template_id).description,
                list(self.template(record.template_id).affinities),
            )
            for record in self.activation_records if record.status == "activated"
        ]

    def pending_activation(self) -> LocationActivationRecord | None:
        return next((x for x in self.activation_records if x.status == "proposed"), None)

    def _validate_state(self) -> None:
        ids = [x.id for x in self.activation_records]
        event_keys = [x.event_key for x in self.activation_records]
        location_ids = [x.location_id for x in self.activation_records]
        if len(ids) != len(set(ids)) or len(event_keys) != len(set(event_keys)):
            raise ValueError("location activation identities must be unique")
        if len(location_ids) != len(set(location_ids)):
            raise ValueError("location ids may be proposed only once")
        if any(x.template_id not in self.templates for x in self.activation_records):
            raise ValueError("location activation references unknown template")
        if any(self.template(x.template_id).location_id != x.location_id for x in self.activation_records):
            raise ValueError("location activation identity contradicts its template")
        activated = [x for x in self.activation_records if x.status == "activated"]
        activated_templates = [x.template_id for x in activated]
        if len(activated_templates) != len(set(activated_templates)):
            raise ValueError("location template may activate only once")
        if set(activated_templates) != self.consumed_template_ids:
            raise ValueError("consumed location templates must exactly match activations")
        if not self.consumed_template_ids.issubset(self.templates):
            raise ValueError("consumed location template is unknown")
        if sum(x.status == "proposed" for x in self.activation_records) > 1:
            raise ValueError("only one location proposal may be pending")
        if any(x.event_key not in self.processed_event_keys for x in self.review_history):
            raise ValueError("development review lacks replay guard")
        if any(x.event_key not in self.processed_event_keys for x in self.activation_records):
            raise ValueError("activation record lacks replay guard")
        if len({x.event_key for x in self.review_history}) != len(self.review_history):
            raise ValueError("development review event keys must be unique")
        review_days = [x.day for x in self.review_history]
        if review_days and (
            self.last_review_day is None or self.last_review_day < max(review_days)
        ):
            raise ValueError("last development review day is inconsistent")
        records = {x.id: x for x in self.activation_records}
        for review in self.review_history:
            if review.status == "waiting":
                continue
            record = records.get(review.activation_id)
            if record is None or (
                review.event_key != record.event_key
                or review.template_id != record.template_id
                or review.day != record.review_day
                or review.status != record.status
            ):
                raise ValueError("development review and activation disagree")
        expected = [x.id for x in activated][-self.PUBLIC_HISTORY_LIMIT:]
        if [x.get("activation_id") for x in self.public_history] != expected:
            raise ValueError("activated locations require exact bounded public history")
        for entry in self.public_history:
            record = records.get(entry.get("activation_id"))
            if record is None or record.status != "activated" or entry != {
                "event_key": f"location-opened:{record.id}",
                "activation_id": record.id,
                "template_id": record.template_id,
                "location_id": record.location_id,
                "day": record.activation_day,
            }:
                raise ValueError("public location history is invalid")
        days = [x.activation_day for x in activated]
        if (max(days) if days else None) != self.last_activation_day:
            raise ValueError("last location activation day is inconsistent")

    def _record(self, review: DevelopmentReview) -> DevelopmentReview:
        self.review_history.append(review)
        self.review_history = self.review_history[-self.REVIEW_HISTORY_LIMIT:]
        referenced = {
            item.activation_id for item in self.review_history
            if item.activation_id is not None
        }
        activated = [
            item for item in self.activation_records if item.status == "activated"
        ]
        retained = [
            item for item in self.activation_records
            if item.id in referenced and item.status != "activated"
        ]
        self.activation_records = (
            activated + retained
        )[-self.ACTIVATION_HISTORY_LIMIT:]
        self.processed_event_keys.add(review.event_key)
        self.last_review_day = max(self.last_review_day or 0, review.day)
        retained_keys = {item.event_key for item in self.review_history}
        retained_keys.update(item.event_key for item in self.activation_records)
        self.processed_event_keys.intersection_update(retained_keys)
        return review

    def _waiting(self, day: int, reason: str) -> DevelopmentReview:
        return self._record(DevelopmentReview(
            f"location-review:day:{day}", day, "waiting", reason
        ))

    def review(self, *, day: int, agents: list, locations: list, activity_records: list[dict]):
        day = _positive_int(day, "development review day")
        pending = self.pending_activation()
        if pending:
            return DevelopmentReview(
                pending.event_key, pending.review_day, "proposed", "pending_activation",
                pending.id, pending.template_id,
            )
        event_key = f"location-review:day:{day}"
        existing = next((x for x in self.review_history if x.event_key == event_key), None)
        if existing:
            return existing
        if self.last_review_day is not None and day <= self.last_review_day:
            return DevelopmentReview(event_key, day, "waiting", "review_already_processed")
        # Once expansion is impossible, settle without accumulating audit noise.
        if len(locations) >= self.policy.location_capacity or not (
            set(self.templates) - self.consumed_template_ids
        ):
            return DevelopmentReview(event_key, day, "waiting", "location_capacity_or_templates_exhausted")
        if day < self.policy.earliest_development_day:
            return DevelopmentReview(
                event_key, day, "waiting", "before_earliest_development_day"
            )
        if (day - self.policy.earliest_development_day) % self.policy.review_interval_days:
            return DevelopmentReview(event_key, day, "waiting", "outside_review_schedule")
        if len(agents) < self.policy.minimum_resident_population:
            return self._waiting(day, "insufficient_population")
        if self.last_activation_day is not None and day - self.last_activation_day < self.policy.development_cooldown_days:
            return self._waiting(day, "development_cooldown")
        if not self.activity_gate_passes(day, agents, activity_records):
            return self._waiting(day, "insufficient_sustained_activity")
        candidate = next(x for x in self.templates.values() if x.id not in self.consumed_template_ids)
        active_location_ids = {x.id for x in locations}
        active_names = {x.name for x in locations}
        if candidate.location_id in active_location_ids or candidate.name in active_names:
            return self._waiting(day, "location_identity_conflict")
        used_ids = {x.id for x in self.activation_records}
        while True:
            activation_id = f"location-activation:{self.next_activation_sequence:04d}"
            self.next_activation_sequence += 1
            if activation_id not in used_ids:
                break
        record = LocationActivationRecord(
            activation_id, event_key, candidate.id, candidate.location_id, day
        )
        self.activation_records.append(record)
        return self._record(DevelopmentReview(
            event_key, day, "proposed", "eligible", activation_id, candidate.id
        ))

    def activity_gate_passes(
        self, day: int, agents: list, activity_records: list[dict]
    ) -> bool:
        first_day = day - self.policy.recent_activity_window_days + 1
        active_ids = {agent.id for agent in agents}
        return first_day >= 1 and not any(
            len({
                x.get("agent_id") for x in activity_records
                if x.get("type") == "activity" and x.get("day") == activity_day
                and x.get("agent_id") in active_ids
            }) < self.policy.minimum_active_residents_per_day
            for activity_day in range(first_day, day + 1)
        )

    def reject(self, activation_id: str, reason: str) -> None:
        record = next(x for x in self.activation_records if x.id == activation_id)
        if record.status == "activated":
            raise ValueError("activated location cannot be rejected")
        record.status = "rejected"
        record.reason = str(reason)[:160]
        review = next(x for x in self.review_history if x.activation_id == activation_id)
        review.status = "rejected"
        review.reason = record.reason

    def activate(self, activation_id: str, *, day: int) -> LocationActivationRecord:
        record = next(x for x in self.activation_records if x.id == activation_id)
        if record.status == "activated":
            return record
        if record.status != "proposed":
            raise ValueError("location is not eligible for activation")
        record.status = "activated"
        record.reason = "activated"
        record.activation_day = int(day)
        self.consumed_template_ids.add(record.template_id)
        self.last_activation_day = int(day)
        review = next(x for x in self.review_history if x.activation_id == activation_id)
        review.status = "activated"
        review.reason = "activated"
        self.public_history.append({
            "event_key": f"location-opened:{record.id}",
            "activation_id": record.id,
            "template_id": record.template_id,
            "location_id": record.location_id,
            "day": int(day),
        })
        self.public_history = self.public_history[-self.PUBLIC_HISTORY_LIMIT:]
        return record

    def validate(self, locations: list[Location], agents: list) -> dict[str, bool]:
        try:
            self._validate_state()
        except (TypeError, ValueError):
            state_valid = False
        else:
            state_valid = True
        ids = [x.id for x in locations]
        names = [x.name for x in locations]
        activated_ids = {x.location_id for x in self.activation_records if x.status == "activated"}
        return {
            "location_growth_state_valid": state_valid,
            "active_location_ids_unique": len(ids) == len(set(ids)),
            "active_location_names_unique": len(names) == len(set(names)),
            "activated_locations_exactly_reconstructed": (
                set(ids) == set(self.base_location_ids) | activated_ids
            ),
            "resident_locations_are_active": all(x.location_id in set(ids) for x in agents),
            "location_growth_histories_bounded": (
                len(self.review_history) <= self.REVIEW_HISTORY_LIMIT
                and len(self.activation_records) <= self.ACTIVATION_HISTORY_LIMIT
                and len(self.processed_event_keys) <= self.REVIEW_HISTORY_LIMIT
                and len(self.public_history) <= self.PUBLIC_HISTORY_LIMIT
            ),
        }
