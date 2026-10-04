"""Bounded authority for configured civic institution formation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from src.systems.persistence_validation import require_record_fields, require_sequence


FORMATION_PATTERN = re.compile(r"institution-formation:(\d{4,})")
INSTITUTION_PATTERN = re.compile(r"institution:(\d{4,})")
GENERATED_INSTITUTION_TEMPLATE_PATTERN = re.compile(
    r"generated_institution_template_(\d{4,})"
)
GENERATED_INSTITUTION_KEY_PATTERN = re.compile(
    r"generated_institution_key_(\d{4,})"
)
GENERATED_ROLE_TEMPLATE_PATTERN = re.compile(
    r"generated_role_template_(\d{4,})"
)
GENERATED_WORK_ACTIVITY_PATTERN = re.compile(
    r"generated_work_activity_(\d{4,})"
)


def _positive(value: object, name: str, *, zero: bool = False) -> int:
    minimum = 0 if zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True)
class InstitutionGrowthPolicy:
    institution_capacity: int
    earliest_formation_day: int
    review_interval_days: int
    formation_cooldown_days: int
    recent_activity_window_days: int
    minimum_distinct_residents: int
    minimum_activity_days: int
    minimum_dynamic_event_occurrences: int
    candidate_activity_window_days: int
    minimum_candidate_activities: int
    history_limit: int

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            _positive(value, name, zero=name == "formation_cooldown_days")


@dataclass(frozen=True)
class InstitutionRoleTemplate:
    role_template_id: str
    title: str
    wage: int
    work_activity_id: str
    work_activity_name: str

    @classmethod
    def from_dict(cls, data: dict) -> "InstitutionRoleTemplate":
        allowed = {
            "role_template_id", "title", "wage", "work_activity_id",
            "work_activity_name",
        }
        if not isinstance(data, dict) or set(data) != allowed:
            raise ValueError("institution role template has an invalid schema")
        if any(not isinstance(data[key], str) or not data[key].strip()
               for key in allowed - {"wage"}):
            raise ValueError("institution role template identity is invalid")
        _positive(data["wage"], "institution wage")
        return cls(**data)


@dataclass(frozen=True)
class InstitutionTemplate:
    id: str
    institution_key: str
    name: str
    location_template_id: str
    startup_funding_source_account_id: str
    startup_grant: int
    relevant_dynamic_event_template_ids: tuple[str, ...]
    role: InstitutionRoleTemplate
    minimum_activity_days: int | None = None
    minimum_candidate_activities: int | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "InstitutionTemplate":
        allowed = {
            "id", "institution_key", "name", "location_template_id",
            "startup_funding_source_account_id", "startup_grant",
            "relevant_dynamic_event_template_ids", "role",
            "minimum_activity_days", "minimum_candidate_activities",
        }
        required = allowed - {
            "minimum_activity_days", "minimum_candidate_activities",
        }
        if (not isinstance(data, dict) or not required.issubset(data)
                or not set(data).issubset(allowed)):
            raise ValueError("institution template has an invalid schema")
        for key in (
            "id", "institution_key", "name", "location_template_id",
            "startup_funding_source_account_id",
        ):
            if not isinstance(data[key], str) or not data[key].strip():
                raise ValueError("institution template identity is invalid")
        _positive(data["startup_grant"], "startup grant")
        events = data["relevant_dynamic_event_template_ids"]
        if (not isinstance(events, list) or not events
                or not all(isinstance(item, str) and item for item in events)
                or len(events) != len(set(events))):
            raise ValueError("institution event allowlist is invalid")
        for key in ("minimum_activity_days", "minimum_candidate_activities"):
            if key in data and data[key] is not None:
                _positive(data[key], f"institution template {key}")
        return cls(
            id=data["id"], institution_key=data["institution_key"],
            name=data["name"], location_template_id=data["location_template_id"],
            startup_funding_source_account_id=data[
                "startup_funding_source_account_id"
            ],
            startup_grant=data["startup_grant"],
            relevant_dynamic_event_template_ids=tuple(events),
            role=InstitutionRoleTemplate.from_dict(data["role"]),
            minimum_activity_days=data.get("minimum_activity_days"),
            minimum_candidate_activities=data.get(
                "minimum_candidate_activities"
            ),
        )


@dataclass
class InstitutionReview:
    event_key: str
    day: int
    status: str
    reason: str
    formation_id: str | None = None
    template_id: str | None = None
    candidate_agent_id: str | None = None

    def __post_init__(self) -> None:
        _positive(self.day, "institution review day")
        if (self.event_key != f"institution-review:day:{self.day}"
                or self.status not in {"waiting", "proposed", "activated", "rejected"}
                or not isinstance(self.reason, str) or not self.reason):
            raise ValueError("invalid institution review")
        identities = (self.formation_id, self.template_id, self.candidate_agent_id)
        if self.status == "waiting" and any(item is not None for item in identities):
            raise ValueError("waiting institution review cannot claim authority")
        if self.status != "waiting" and any(not isinstance(item, str) or not item for item in identities):
            raise ValueError("institution proposal requires stable identities")


@dataclass
class InstitutionFormationRecord:
    id: str
    institution_id: str
    event_key: str
    template_id: str
    institution_key: str
    name: str
    location_id: str
    location_activation_id: str
    employee_agent_id: str
    employer_account_id: str
    employment_id: str
    role_template_id: str
    review_day: int
    status: str = "proposed"
    reason: str = "eligible"
    activation_day: int | None = None
    startup_transaction_id: str | None = None

    def __post_init__(self) -> None:
        _positive(self.review_day, "institution formation review day")
        strings = (
            self.id, self.institution_id, self.template_id, self.institution_key,
            self.name, self.location_id, self.location_activation_id,
            self.employee_agent_id, self.employer_account_id, self.employment_id,
            self.role_template_id, self.reason,
        )
        if (any(not isinstance(item, str) or not item for item in strings)
                or FORMATION_PATTERN.fullmatch(self.id) is None
                or INSTITUTION_PATTERN.fullmatch(self.institution_id) is None
                or self.event_key != f"institution-review:day:{self.review_day}"
                or self.status not in {"proposed", "activated", "rejected"}):
            raise ValueError("invalid institution formation record")
        if self.status == "activated":
            _positive(self.activation_day, "institution activation day")
            if not self.startup_transaction_id:
                raise ValueError("activated institution requires startup transfer")
        elif self.activation_day is not None or self.startup_transaction_id is not None:
            raise ValueError("inactive institution cannot claim activation proof")


class InstitutionGrowthSystem:
    """Owns finite templates, deterministic reviews, and formation provenance."""

    SCHEMA_VERSION = 1

    def __init__(
        self, policy: InstitutionGrowthPolicy,
        templates: list[InstitutionTemplate], *, next_sequence: int = 1,
        review_history: list[InstitutionReview] | None = None,
        formation_records: list[InstitutionFormationRecord] | None = None,
        processed_event_keys: set[str] | None = None,
        consumed_template_ids: set[str] | None = None,
        last_activation_day: int | None = None,
        public_history: list[dict] | None = None,
        configured_template_ids: set[str] | None = None,
    ) -> None:
        if len({item.id for item in templates}) != len(templates):
            raise ValueError("institution template ids must be unique")
        if len({item.institution_key for item in templates}) != len(templates):
            raise ValueError("institution template keys must be unique")
        if len({item.name for item in templates}) != len(templates):
            raise ValueError("institution template names must be unique")
        if len({item.role.role_template_id for item in templates}) != len(templates):
            raise ValueError("institution role template ids must be unique")
        if len({item.role.work_activity_id for item in templates}) != len(templates):
            raise ValueError("institution work activity ids must be unique")
        self.policy = policy
        self.templates = {item.id: item for item in templates}
        self.configured_template_ids = set(
            configured_template_ids or self.templates
        )
        self.next_sequence = _positive(next_sequence, "next institution sequence")
        self.review_history = list(review_history or [])
        self.formation_records = list(formation_records or [])
        self.processed_event_keys = set(processed_event_keys or ())
        self.consumed_template_ids = set(consumed_template_ids or ())
        self.last_activation_day = last_activation_day
        self.public_history = list(public_history or [])
        self._validate_state()

    @classmethod
    def from_config(
        cls, path: str | Path, state=None, *,
        supplemental_templates: list[InstitutionTemplate] | None = None,
        location_growth=None, event_ecology=None,
    ) -> "InstitutionGrowthSystem":
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        section = config.get("institution_growth") if isinstance(config, dict) else None
        if not isinstance(section, dict) or set(section) != {"policy", "templates"}:
            raise ValueError("institution growth config has an invalid schema")
        policy = InstitutionGrowthPolicy(**section["policy"])
        templates = [InstitutionTemplate.from_dict(item) for item in section["templates"]]
        configured_ids = {item.id for item in templates}
        if any(
            GENERATED_INSTITUTION_TEMPLATE_PATTERN.fullmatch(item.id)
            or GENERATED_INSTITUTION_KEY_PATTERN.fullmatch(item.institution_key)
            or GENERATED_ROLE_TEMPLATE_PATTERN.fullmatch(
                item.role.role_template_id
            )
            or GENERATED_WORK_ACTIVITY_PATTERN.fullmatch(
                item.role.work_activity_id
            )
            for item in templates
        ):
            raise ValueError(
                "checked-in institution configuration uses generated namespace"
            )
        combined = list(templates)
        validator = cls(policy, combined, configured_template_ids=configured_ids)
        for template in supplemental_templates or ():
            validator.register_generated_template(
                template, location_growth=location_growth,
                event_ecology=event_ecology,
            )
        templates = list(validator.templates.values())
        if state is None:
            return validator
        allowed = {
            "schema_version", "next_sequence", "review_history",
            "formation_records", "processed_event_keys", "consumed_template_ids",
            "last_activation_day", "public_history",
        }
        if (not isinstance(state, dict) or (type(state.get("schema_version")) is not int
                or state.get("schema_version") != cls.SCHEMA_VERSION)
                or set(state) != allowed):
            raise ValueError("unsupported institution growth state schema")
        if any(not isinstance(state[key], list) for key in (
            "review_history", "formation_records", "processed_event_keys",
            "consumed_template_ids", "public_history",
        )):
            raise ValueError("institution growth state collections must be lists")
        return cls(
            policy, templates, next_sequence=state["next_sequence"],
            review_history=[InstitutionReview(**require_record_fields(item, InstitutionReview)) for item in state["review_history"]],
            formation_records=[InstitutionFormationRecord(**require_record_fields(item, InstitutionFormationRecord))
                               for item in state["formation_records"]],
            processed_event_keys=set(state["processed_event_keys"]),
            consumed_template_ids=set(state["consumed_template_ids"]),
            last_activation_day=state["last_activation_day"],
            public_history=state["public_history"],
            configured_template_ids=configured_ids,
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "next_sequence": self.next_sequence,
            "review_history": [asdict(item) for item in self.review_history],
            "formation_records": [asdict(item) for item in self.formation_records],
            "processed_event_keys": sorted(self.processed_event_keys),
            "consumed_template_ids": sorted(self.consumed_template_ids),
            "last_activation_day": self.last_activation_day,
            "public_history": list(self.public_history),
        }

    def template(self, template_id: str) -> InstitutionTemplate:
        try:
            return self.templates[template_id]
        except KeyError as error:
            raise ValueError("unknown institution template") from error

    def register_generated_template(
        self, template: InstitutionTemplate, *, location_growth,
        event_ecology,
    ) -> None:
        """Register an admitted possibility without forming an institution."""
        if not isinstance(template, InstitutionTemplate):
            raise ValueError("generated institution template has invalid type")
        template_match = GENERATED_INSTITUTION_TEMPLATE_PATTERN.fullmatch(
            template.id
        )
        if template_match is None:
            raise ValueError("generated institution uses a reserved namespace")
        sequence = template_match.group(1)
        if (
            GENERATED_INSTITUTION_KEY_PATTERN.fullmatch(
                template.institution_key
            ) is None
            or template.institution_key
            != f"generated_institution_key_{sequence}"
            or template.role.role_template_id
            != f"generated_role_template_{sequence}"
            or template.role.work_activity_id
            != f"generated_work_activity_{sequence}"
        ):
            raise ValueError("generated institution identities are inconsistent")
        existing = list(self.templates.values())
        if (
            template.id in self.templates
            or template.institution_key in {
                item.institution_key for item in existing
            }
            or template.name.casefold() in {
                item.name.casefold() for item in existing
            }
            or template.role.role_template_id in {
                item.role.role_template_id for item in existing
            }
            or template.role.work_activity_id in {
                item.role.work_activity_id for item in existing
            }
        ):
            raise ValueError("generated institution identity collides")
        location_template = location_growth.templates.get(
            template.location_template_id
        ) if location_growth is not None else None
        if (
            location_template is None
            or not template.location_template_id.startswith(
                "generated_location_template_"
            )
        ):
            raise ValueError(
                "generated institution lacks generated-location authority"
            )
        if not template.relevant_dynamic_event_template_ids:
            raise ValueError("generated institution lacks event authority")
        for event_id in template.relevant_dynamic_event_template_ids:
            event_template = (
                event_ecology.templates.get(event_id)
                if event_ecology is not None else None
            )
            if (
                not event_id.startswith("generated_event_template_")
                or event_template is None
                or event_template.location_template_id
                != template.location_template_id
            ):
                raise ValueError(
                    "generated institution event authority is invalid"
                )
        self.templates[template.id] = template

    def _validate_state(self) -> None:
        ids = [item.id for item in self.formation_records]
        live = [item for item in self.formation_records if item.status != "rejected"]
        institutions = [item.institution_id for item in live]
        keys = [item.institution_key for item in live]
        names = [item.name for item in live]
        if len(ids) != len(set(ids)) or any(
            len(items) != len(set(items)) for items in (institutions, keys, names)
        ):
            raise ValueError("institution authority identities must be unique")
        if (sum(item.status == "activated" for item in self.formation_records)
                > self.policy.institution_capacity
                or len(self.formation_records) > self.policy.history_limit):
            raise ValueError("institution formation history or capacity exceeded")
        if len(self.review_history) > self.policy.history_limit:
            raise ValueError("institution review history exceeds bound")
        if any(item.template_id not in self.templates for item in self.formation_records):
            raise ValueError("institution record references unknown template")
        activated = [item for item in self.formation_records if item.status == "activated"]
        activated_template_ids = [item.template_id for item in activated]
        if len(activated_template_ids) != len(set(activated_template_ids)):
            raise ValueError("institution template may activate only once")
        if {item.template_id for item in activated} != self.consumed_template_ids:
            raise ValueError("institution consumed templates contradict activations")
        employee_ids = [item.employee_agent_id for item in live]
        employer_account_ids = [item.employer_account_id for item in live]
        employment_ids = [item.employment_id for item in live]
        if any(len(values) != len(set(values)) for values in (
            employee_ids, employer_account_ids, employment_ids,
        )):
            raise ValueError("institution employment identities must be independent")
        review_keys = {item.event_key for item in self.review_history}
        if len(review_keys) != len(self.review_history):
            raise ValueError("institution review keys must be unique")
        if review_keys != self.processed_event_keys:
            raise ValueError("institution review replay guards contradict history")
        reviews = {item.event_key: item for item in self.review_history}
        for record in self.formation_records:
            review = reviews.get(record.event_key)
            sequence = FORMATION_PATTERN.fullmatch(record.id).group(1)
            if (review is None or review.formation_id != record.id
                    or review.template_id != record.template_id
                    or review.candidate_agent_id != record.employee_agent_id
                    or review.status != record.status
                    or record.institution_id != f"institution:{sequence}"
                    or record.employer_account_id
                    != f"account:institution:{sequence}"
                    or record.employment_id
                    != f"employment:institution:{sequence}"):
                raise ValueError("institution formation lacks its review")
        sequences = [int(FORMATION_PATTERN.fullmatch(item.id).group(1))
                     for item in self.formation_records]
        require_sequence(sequences, self.next_sequence, "institution")
        if self.last_activation_day != max(
            (item.activation_day for item in activated), default=None
        ):
            raise ValueError("institution activation day is inconsistent")
        expected_public = [
            {
                "formation_id": item.id,
                "institution_id": item.institution_id,
                "day": item.activation_day,
                "name": item.name,
                "location_id": item.location_id,
            }
            for item in activated
        ][-self.policy.history_limit:]
        if self.public_history != expected_public:
            raise ValueError("institution public history contradicts authority")

    def _wait(self, day: int, reason: str) -> InstitutionReview:
        review = InstitutionReview(
            event_key=f"institution-review:day:{day}", day=day,
            status="waiting", reason=reason,
        )
        self.review_history.append(review)
        self._trim_reviews()
        self.processed_event_keys = {item.event_key for item in self.review_history}
        return review

    def _trim_reviews(self) -> None:
        formation_keys = {item.event_key for item in self.formation_records}
        required = [item for item in self.review_history
                    if item.event_key in formation_keys]
        optional = [item for item in self.review_history
                    if item.event_key not in formation_keys]
        room = max(0, self.policy.history_limit - len(required))
        self.review_history = sorted(
            [*required, *(optional[-room:] if room else [])],
            key=lambda item: item.day,
        )

    def pending_formation(self) -> InstitutionFormationRecord | None:
        pending = [item for item in self.formation_records if item.status == "proposed"]
        if len(pending) > 1:
            raise ValueError("multiple institution formations are pending")
        return pending[0] if pending else None

    def review(
        self, *, day: int, agents: list, locations: list, location_growth,
        event_ecology, activity_records: list[dict], economy,
    ) -> InstitutionReview:
        _positive(day, "institution review day")
        event_key = f"institution-review:day:{day}"
        existing = next((item for item in self.review_history
                         if item.event_key == event_key), None)
        if existing is not None:
            return existing
        if day < self.policy.earliest_formation_day:
            return self._wait(day, "too_early")
        if day % self.policy.review_interval_days:
            return self._wait(day, "not_review_day")
        if self.pending_formation() is not None:
            return self._wait(day, "formation_pending")
        activated = [item for item in self.formation_records if item.status == "activated"]
        if len(activated) >= self.policy.institution_capacity:
            return self._wait(day, "capacity_reached")
        if (self.last_activation_day is not None
                and day - self.last_activation_day < self.policy.formation_cooldown_days):
            return self._wait(day, "cooldown")

        active_locations = {item.id for item in locations}
        active_agents = {item.id for item in agents}
        first_day = day - self.policy.recent_activity_window_days
        candidate_first_day = day - self.policy.candidate_activity_window_days
        for template_id in sorted(self.templates):
            template = self.templates[template_id]
            if template.id in self.consumed_template_ids:
                continue
            binding = location_growth.templates.get(template.location_template_id)
            if binding is None or binding.location_id not in active_locations:
                continue
            activation = next((item for item in location_growth.activation_records
                               if item.status == "activated"
                               and item.template_id == template.location_template_id
                               and item.location_id == binding.location_id), None)
            if activation is None:
                continue
            recent = [item for item in activity_records
                      if item.get("type") == "activity"
                      and item.get("location") == binding.location_id
                      and first_day <= item.get("day", -1) <= day]
            residents = {item.get("agent_id") for item in recent
                         if item.get("agent_id") in active_agents}
            activity_days = {item.get("day") for item in recent}
            minimum_activity_days = (
                template.minimum_activity_days
                or self.policy.minimum_activity_days
            )
            if (len(residents) < self.policy.minimum_distinct_residents
                    or len(activity_days) < minimum_activity_days):
                continue
            occurrences = [item for item in event_ecology.occurrence_history
                           if item.location_id == binding.location_id
                           and item.template_id in template.relevant_dynamic_event_template_ids
                           and item.day < day]
            if len(occurrences) < self.policy.minimum_dynamic_event_occurrences:
                continue
            occurrence_ids = {item.occurrence_id for item in occurrences}
            unemployed = []
            for agent in agents:
                if economy.employment_for_agent(agent.id) is not None:
                    continue
                try:
                    economy.account_for_agent(agent.id)
                except Exception:
                    continue
                evidence = [item for item in activity_records
                            if item.get("type") == "activity"
                            and item.get("agent_id") == agent.id
                            and item.get("location") == binding.location_id
                            and candidate_first_day <= item.get("day", -1) <= day]
                minimum_candidate_activities = (
                    template.minimum_candidate_activities
                    or self.policy.minimum_candidate_activities
                )
                if len(evidence) < minimum_candidate_activities:
                    continue
                attendance = sum(
                    item.get("activity_id") == "attend_event"
                    and item.get("source_event_occurrence_id") in occurrence_ids
                    for item in evidence
                )
                unemployed.append((-len(evidence), -attendance, agent.id))
            if not unemployed:
                continue
            source = economy.accounts.get(template.startup_funding_source_account_id)
            if source is None or source.balance < template.startup_grant:
                continue
            candidate_id = min(unemployed)[2]
            sequence = self.next_sequence
            record = InstitutionFormationRecord(
                id=f"institution-formation:{sequence:04d}",
                institution_id=f"institution:{sequence:04d}", event_key=event_key,
                template_id=template.id, institution_key=template.institution_key,
                name=template.name, location_id=binding.location_id,
                location_activation_id=activation.id, employee_agent_id=candidate_id,
                employer_account_id=f"account:institution:{sequence:04d}",
                employment_id=f"employment:institution:{sequence:04d}",
                role_template_id=template.role.role_template_id, review_day=day,
            )
            review = InstitutionReview(
                event_key, day, "proposed", "eligible", record.id,
                template.id, candidate_id,
            )
            self.next_sequence += 1
            self.formation_records.append(record)
            self.review_history.append(review)
            self._trim_reviews()
            self.processed_event_keys = {item.event_key for item in self.review_history}
            return review
        return self._wait(day, "not_ready")

    def activate(
        self, formation_id: str, *, day: int, startup_transaction_id: str,
    ) -> InstitutionFormationRecord:
        record = next((item for item in self.formation_records
                       if item.id == formation_id), None)
        if record is None or record.status != "proposed":
            raise ValueError("institution formation is not pending")
        record.status = "activated"
        record.activation_day = day
        record.startup_transaction_id = startup_transaction_id
        self.consumed_template_ids.add(record.template_id)
        self.last_activation_day = day
        self.public_history.append({
            "formation_id": record.id, "institution_id": record.institution_id,
            "day": day, "name": record.name, "location_id": record.location_id,
        })
        self.public_history = self.public_history[-self.policy.history_limit:]
        review = next(item for item in self.review_history
                      if item.event_key == record.event_key)
        review.status = "activated"
        review.reason = "activated"
        self._validate_state()
        return record

    def reject(self, formation_id: str, reason: str) -> None:
        record = next((item for item in self.formation_records
                       if item.id == formation_id), None)
        if record is None or record.status != "proposed":
            return
        record.status = "rejected"
        record.reason = reason or "rejected"
        review = next(item for item in self.review_history
                      if item.event_key == record.event_key)
        review.status = "rejected"
        review.reason = record.reason

    def validate(self, *, agents: list, locations: list, location_growth,
                 event_ecology, economy,
                 activity_records: list[dict] | None = None) -> dict[str, bool]:
        self._validate_state()
        agent_ids = {item.id for item in agents}
        location_ids = {item.id for item in locations}
        checks = {
            "institution_capacity_bounded": sum(
                item.status == "activated" for item in self.formation_records
            ) <= self.policy.institution_capacity,
            "institution_histories_bounded": len(self.review_history)
            <= self.policy.history_limit and len(self.public_history)
            <= self.policy.history_limit,
            "institution_templates_known": all(
                item.template_id in self.templates for item in self.formation_records
            ),
            "institution_locations_active": True,
            "institution_economy_provenance": True,
            "no_orphan_institution_economy": True,
            "institution_employee_selection": True,
        }
        activated = [item for item in self.formation_records
                     if item.status == "activated"]
        expected_accounts = {item.employer_account_id for item in activated}
        expected_employments = {item.employment_id for item in activated}
        expected_startups = {
            f"institution-startup:{item.id}" for item in activated
        }
        checks["no_orphan_institution_economy"] = (
            {item.id for item in economy.accounts.values()
             if item.owner_type == "institution"} == expected_accounts
            and {item.id for item in economy.employments.values()
                 if item.institution_id is not None} == expected_employments
            and {item.event_key for item in economy.ledger
                 if item.transaction_type == "institution_startup"}
            == expected_startups
        )
        for record in self.formation_records:
            if activity_records is not None and record.status == "activated":
                template = self.templates[record.template_id]
                candidate_first_day = (
                    record.review_day
                    - self.policy.candidate_activity_window_days
                )
                occurrence_ids = {
                    item.occurrence_id for item in event_ecology.occurrence_history
                    if item.location_id == record.location_id
                    and item.template_id
                    in template.relevant_dynamic_event_template_ids
                    and item.day < record.review_day
                }
                ranked = []
                for agent in agents:
                    employed_at_review = any(
                        employment.agent_id == agent.id
                        and employment.active
                        and employment.start_day <= record.review_day
                        for employment in economy.employments.values()
                    )
                    if employed_at_review:
                        continue
                    try:
                        economy.account_for_agent(agent.id)
                    except Exception:
                        continue
                    evidence = [
                        item for item in activity_records
                        if item.get("type") == "activity"
                        and item.get("agent_id") == agent.id
                        and item.get("location") == record.location_id
                        and candidate_first_day <= item.get("day", -1)
                        <= record.review_day
                    ]
                    minimum = (
                        template.minimum_candidate_activities
                        or self.policy.minimum_candidate_activities
                    )
                    if len(evidence) < minimum:
                        continue
                    attendance = sum(
                        item.get("activity_id") == "attend_event"
                        and item.get("source_event_occurrence_id")
                        in occurrence_ids
                        for item in evidence
                    )
                    ranked.append((-len(evidence), -attendance, agent.id))
                checks["institution_employee_selection"] &= bool(
                    ranked and min(ranked)[2] == record.employee_agent_id
                )
            if record.status != "activated":
                continue
            template = self.templates[record.template_id]
            binding = location_growth.templates.get(template.location_template_id)
            activation = next((item for item in location_growth.activation_records
                               if item.id == record.location_activation_id
                               and item.status == "activated"), None)
            checks["institution_locations_active"] &= bool(
                binding and activation and record.location_id in location_ids
                and binding.location_id == record.location_id
                and activation.template_id == template.location_template_id
                and activation.location_id == record.location_id
            )
            account = economy.accounts.get(record.employer_account_id)
            employment = economy.employments.get(record.employment_id)
            startup = [item for item in economy.ledger
                       if item.id == record.startup_transaction_id]
            checks["institution_economy_provenance"] &= bool(
                record.employee_agent_id in agent_ids
                and account and account.owner_type == "institution"
                and account.owner_id == record.institution_id
                and economy.initial_balances.get(account.id) == 0
                and employment and employment.agent_id == record.employee_agent_id
                and employment.institution_id == record.institution_id
                and employment.formation_id == record.id
                and employment.employer_account_id == account.id
                and record.role_template_id == template.role.role_template_id
                and employment.role_template_id == record.role_template_id
                and employment.active
                and employment.title == template.role.title
                and employment.wage == template.role.wage
                and employment.start_day == record.activation_day + 1
                and employment.qualifying_activity_ids
                == (template.role.work_activity_id,)
                and dict(employment.activity_names).get(
                    template.role.work_activity_id
                ) == template.role.work_activity_name
                and dict(employment.activity_locations).get(
                    template.role.work_activity_id
                ) == record.location_id
                and len(startup) == 1
                and startup[0].event_key == f"institution-startup:{record.id}"
                and startup[0].source_account_id
                == template.startup_funding_source_account_id
                and startup[0].destination_account_id == account.id
                and startup[0].amount == template.startup_grant
                and startup[0].transaction_type == "institution_startup"
                and dict(startup[0].metadata).get("formation_id") == record.id
                and dict(startup[0].metadata).get("institution_id")
                == record.institution_id
                and dict(startup[0].metadata).get("template_id") == template.id
            )
        return checks
