"""Bounded authority for one configured institution-commerce lifecycle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re


ACTIVATION_PATTERN = re.compile(r"commerce-activation:(\d{4,})")


def _positive(value: object, name: str, *, zero: bool = False) -> int:
    minimum = 0 if zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True)
class CommerceGrowthPolicy:
    commerce_capacity: int
    earliest_activation_day: int
    review_interval_days: int
    activation_cooldown_days: int
    recent_use_window_days: int
    minimum_distinct_residents: int
    minimum_use_days: int
    operator_work_window_days: int
    minimum_operator_work_days: int
    demand_window_days: int
    minimum_target_good_purchases: int
    history_limit: int

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            _positive(value, name, zero=name == "activation_cooldown_days")


@dataclass(frozen=True)
class CommerceTemplate:
    id: str
    institution_template_id: str
    location_template_id: str
    upstream_seller_id: str
    input_good_id: str
    input_quantity: int
    output_good_id: str
    output_quantity: int
    purchase_activity_id: str
    production_activity_id: str
    target_stock_quantity: int

    @classmethod
    def from_dict(cls, data: dict) -> "CommerceTemplate":
        allowed = {
            "id", "institution_template_id", "location_template_id",
            "upstream_seller_id", "input_good_id", "input_quantity",
            "output_good_id", "output_quantity", "purchase_activity_id",
            "production_activity_id", "target_stock_quantity",
        }
        if not isinstance(data, dict) or set(data) != allowed:
            raise ValueError("commerce template has an invalid schema")
        strings = allowed - {
            "input_quantity", "output_quantity", "target_stock_quantity",
        }
        if any(not isinstance(data[name], str) or not data[name].strip()
               for name in strings):
            raise ValueError("commerce template identities are invalid")
        for name in ("input_quantity", "output_quantity", "target_stock_quantity"):
            _positive(data[name], name)
        if data["input_good_id"] == data["output_good_id"]:
            raise ValueError("commerce production must transform a distinct input")
        return cls(**data)


@dataclass
class CommerceReview:
    event_key: str
    day: int
    status: str
    reason: str
    activation_id: str | None = None
    template_id: str | None = None

    def __post_init__(self) -> None:
        _positive(self.day, "commerce review day")
        if (self.event_key != f"commerce-review:day:{self.day}"
                or self.status not in {"waiting", "proposed", "activated", "rejected"}
                or not isinstance(self.reason, str) or not self.reason):
            raise ValueError("invalid commerce review")
        if self.status == "waiting" and (self.activation_id or self.template_id):
            raise ValueError("waiting commerce review cannot claim an activation")
        if self.status != "waiting" and not (self.activation_id and self.template_id):
            raise ValueError("commerce proposal requires stable identities")


@dataclass
class CommerceActivationRecord:
    id: str
    event_key: str
    template_id: str
    institution_formation_id: str
    institution_id: str
    location_id: str
    location_activation_id: str
    operator_agent_id: str
    operator_employment_id: str
    institution_account_id: str
    inventory_id: str
    seller_id: str
    recipe_id: str
    purchase_activity_id: str
    upstream_seller_id: str
    review_day: int
    status: str = "proposed"
    reason: str = "eligible"
    activation_day: int | None = None

    def __post_init__(self) -> None:
        _positive(self.review_day, "commerce review day")
        strings = (
            self.id, self.template_id, self.institution_formation_id,
            self.institution_id, self.location_id, self.location_activation_id,
            self.operator_agent_id, self.operator_employment_id,
            self.institution_account_id, self.inventory_id, self.seller_id,
            self.recipe_id, self.purchase_activity_id, self.upstream_seller_id,
            self.reason,
        )
        if (ACTIVATION_PATTERN.fullmatch(self.id or "") is None
                or any(not isinstance(item, str) or not item for item in strings)
                or self.event_key != f"commerce-review:day:{self.review_day}"
                or self.status not in {"proposed", "activated", "rejected"}):
            raise ValueError("invalid commerce activation record")
        sequence = ACTIVATION_PATTERN.fullmatch(self.id).group(1)
        if (self.inventory_id != f"inventory:institution:{sequence}"
                or self.seller_id != f"seller:institution:{sequence}"
                or self.recipe_id != f"recipe:institution:{sequence}:garden_meals"):
            raise ValueError("commerce child identities contradict activation identity")
        if self.status == "activated":
            _positive(self.activation_day, "commerce activation day")
            if self.activation_day < self.review_day:
                raise ValueError("commerce cannot activate before review")
        elif self.activation_day is not None:
            raise ValueError("inactive commerce cannot claim activation")


class CommerceGrowthSystem:
    """Own finite commerce eligibility, identities, records, and replay state."""

    SCHEMA_VERSION = 1

    def __init__(
        self, policy: CommerceGrowthPolicy, templates: list[CommerceTemplate], *,
        next_sequence: int = 1,
        review_history: list[CommerceReview] | None = None,
        activation_records: list[CommerceActivationRecord] | None = None,
        processed_event_keys: set[str] | None = None,
        consumed_template_ids: set[str] | None = None,
        last_activation_day: int | None = None,
        public_history: list[dict] | None = None,
    ) -> None:
        if len({item.id for item in templates}) != len(templates):
            raise ValueError("commerce template ids must be unique")
        if len({item.purchase_activity_id for item in templates}) != len(templates):
            raise ValueError("commerce purchase activities must be unique")
        self.policy = policy
        self.templates = {item.id: item for item in templates}
        self.next_sequence = _positive(next_sequence, "next commerce sequence")
        self.review_history = list(review_history or [])[-policy.history_limit:]
        self.activation_records = list(activation_records or [])
        self.processed_event_keys = set(processed_event_keys or ())
        self.consumed_template_ids = set(consumed_template_ids or ())
        self.last_activation_day = last_activation_day
        self.public_history = list(public_history or [])[-policy.history_limit:]
        self._validate_state()

    @classmethod
    def from_config(cls, path: str | Path, state=None) -> "CommerceGrowthSystem":
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        section = config.get("commerce_growth") if isinstance(config, dict) else None
        if not isinstance(section, dict) or set(section) != {"policy", "templates"}:
            raise ValueError("commerce growth config has an invalid schema")
        policy = CommerceGrowthPolicy(**section["policy"])
        templates = [CommerceTemplate.from_dict(item) for item in section["templates"]]
        if state is None:
            return cls(policy, templates)
        allowed = {
            "schema_version", "next_sequence", "review_history",
            "activation_records", "processed_event_keys", "consumed_template_ids",
            "last_activation_day", "public_history",
        }
        if (not isinstance(state, dict) or state.get("schema_version") != cls.SCHEMA_VERSION
                or set(state) != allowed):
            raise ValueError("unsupported commerce growth state schema")
        if any(not isinstance(state[name], list) for name in (
            "review_history", "activation_records", "processed_event_keys",
            "consumed_template_ids", "public_history",
        )):
            raise ValueError("commerce growth state collections must be lists")
        return cls(
            policy, templates, next_sequence=state["next_sequence"],
            review_history=[CommerceReview(**item) for item in state["review_history"]],
            activation_records=[CommerceActivationRecord(**item)
                                for item in state["activation_records"]],
            processed_event_keys=set(state["processed_event_keys"]),
            consumed_template_ids=set(state["consumed_template_ids"]),
            last_activation_day=state["last_activation_day"],
            public_history=state["public_history"],
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "next_sequence": self.next_sequence,
            "review_history": [asdict(item) for item in self.review_history],
            "activation_records": [asdict(item) for item in self.activation_records],
            "processed_event_keys": sorted(self.processed_event_keys),
            "consumed_template_ids": sorted(self.consumed_template_ids),
            "last_activation_day": self.last_activation_day,
            "public_history": list(self.public_history),
        }

    def template(self, template_id: str) -> CommerceTemplate:
        try:
            return self.templates[template_id]
        except KeyError as error:
            raise ValueError("unknown commerce template") from error

    def _validate_state(self) -> None:
        ids = [item.id for item in self.activation_records]
        if len(ids) != len(set(ids)):
            raise ValueError("commerce activation ids must be unique")
        if len(self.activation_records) > self.policy.history_limit:
            raise ValueError("commerce activation history exceeds bound")
        if len(self.review_history) > self.policy.history_limit:
            raise ValueError("commerce review history exceeds bound")
        if any(item.template_id not in self.templates for item in self.activation_records):
            raise ValueError("commerce record references unknown template")
        activated = [item for item in self.activation_records if item.status == "activated"]
        if len(activated) > self.policy.commerce_capacity:
            raise ValueError("commerce capacity exceeded")
        if {item.template_id for item in activated} != self.consumed_template_ids:
            raise ValueError("commerce template consumption contradicts activations")
        if len([item.template_id for item in activated]) != len(
            {item.template_id for item in activated}
        ):
            raise ValueError("commerce template activated more than once")
        reviews = {item.event_key: item for item in self.review_history}
        if len(reviews) != len(self.review_history):
            raise ValueError("commerce review keys must be unique")
        if set(reviews) != self.processed_event_keys:
            raise ValueError("commerce replay guards contradict review history")
        for record in self.activation_records:
            review = reviews.get(record.event_key)
            if (review is None or review.activation_id != record.id
                    or review.template_id != record.template_id
                    or review.status != record.status):
                raise ValueError("commerce activation lacks its exact review")
        sequences = [int(ACTIVATION_PATTERN.fullmatch(item.id).group(1))
                     for item in self.activation_records]
        if self.next_sequence <= max(sequences, default=0):
            raise ValueError("next commerce sequence would reuse identity")
        if self.last_activation_day != max(
            (item.activation_day for item in activated), default=None
        ):
            raise ValueError("commerce activation day is inconsistent")
        expected_public = [{
            "activation_id": item.id, "day": item.activation_day,
            "institution_id": item.institution_id, "seller_id": item.seller_id,
            "location_id": item.location_id,
        } for item in activated][-self.policy.history_limit:]
        if self.public_history != expected_public:
            raise ValueError("commerce public history contradicts authority")

    def _wait(self, day: int, reason: str) -> CommerceReview:
        review = CommerceReview(
            f"commerce-review:day:{day}", day, "waiting", reason,
        )
        self.review_history.append(review)
        self._trim_reviews()
        self.processed_event_keys = {item.event_key for item in self.review_history}
        return review

    def _trim_reviews(self) -> None:
        required_keys = {item.event_key for item in self.activation_records}
        required = [item for item in self.review_history if item.event_key in required_keys]
        optional = [item for item in self.review_history if item.event_key not in required_keys]
        room = max(0, self.policy.history_limit - len(required))
        self.review_history = sorted(
            [*required, *(optional[-room:] if room else [])], key=lambda item: item.day,
        )

    def pending_activation(self) -> CommerceActivationRecord | None:
        pending = [item for item in self.activation_records if item.status == "proposed"]
        if len(pending) > 1:
            raise ValueError("multiple commerce activations are pending")
        return pending[0] if pending else None

    def readiness_reason(
        self, template: CommerceTemplate, *, day: int, agents: list, locations: list,
        institution_growth, location_growth, economy, materials,
        activity_records: list[dict],
    ) -> tuple[str, object | None]:
        formation = next((item for item in institution_growth.formation_records
                          if item.status == "activated"
                          and item.template_id == template.institution_template_id), None)
        if formation is None:
            return "institution_not_active", None
        binding = location_growth.templates.get(template.location_template_id)
        location_activation = next((item for item in location_growth.activation_records
                                    if item.status == "activated"
                                    and item.template_id == template.location_template_id), None)
        if (binding is None or location_activation is None
                or formation.location_id != binding.location_id
                or formation.location_activation_id != location_activation.id
                or binding.location_id not in {item.id for item in locations}):
            return "location_not_active", None
        employment = economy.employments.get(formation.employment_id)
        account = economy.accounts.get(formation.employer_account_id)
        if (employment is None or not employment.active
                or employment.agent_id != formation.employee_agent_id
                or employment.institution_id != formation.institution_id
                or employment.formation_id != formation.id
                or account is None or account.owner_type != "institution"
                or account.owner_id != formation.institution_id):
            return "operator_authority_missing", None
        work_first = day - self.policy.operator_work_window_days
        work_days = {item.get("day") for item in economy.work_events
                     if item.get("eligible")
                     and item.get("employment_id") == formation.employment_id
                     and item.get("agent_id") == formation.employee_agent_id
                     and item.get("location_id") == formation.location_id
                     and work_first <= item.get("day", -1) < day}
        if len(work_days) < self.policy.minimum_operator_work_days:
            return "insufficient_operator_work", None
        use_first = day - self.policy.recent_use_window_days
        uses = [item for item in activity_records
                if item.get("type") == "activity"
                and item.get("location") == formation.location_id
                and use_first <= item.get("day", -1) < day]
        agent_ids = {item.id for item in agents}
        if (len({item.get("agent_id") for item in uses
                 if item.get("agent_id") in agent_ids})
                < self.policy.minimum_distinct_residents
                or len({item.get("day") for item in uses}) < self.policy.minimum_use_days):
            return "insufficient_garden_use", None
        demand_first = day - self.policy.demand_window_days
        demand = [item for item in materials.exchanges
                  if item.good_id == template.output_good_id
                  and demand_first <= item.day < day]
        if len(demand) < self.policy.minimum_target_good_purchases:
            return "insufficient_demand", None
        seller = materials.sellers.get(template.upstream_seller_id)
        if seller is None or not seller.active:
            return "upstream_seller_missing", None
        if materials.quantity(seller.inventory_id, template.input_good_id) < template.input_quantity:
            return "upstream_stock_insufficient", None
        cost = materials.price_for_good(template.input_good_id) * template.input_quantity
        if account.balance < cost:
            return "institution_funds_insufficient", None
        return "eligible", formation

    def review(self, *, day: int, agents: list, locations: list,
               institution_growth, location_growth, economy, materials,
               activity_records: list[dict]) -> CommerceReview:
        _positive(day, "commerce review day")
        event_key = f"commerce-review:day:{day}"
        existing = next((item for item in self.review_history
                         if item.event_key == event_key), None)
        if existing is not None:
            return existing
        if day < self.policy.earliest_activation_day:
            return self._wait(day, "too_early")
        if day % self.policy.review_interval_days:
            return self._wait(day, "not_review_day")
        if self.pending_activation() is not None:
            return self._wait(day, "activation_pending")
        if sum(item.status == "activated" for item in self.activation_records) >= (
            self.policy.commerce_capacity
        ):
            return self._wait(day, "capacity_reached")
        if (self.last_activation_day is not None
                and day - self.last_activation_day < self.policy.activation_cooldown_days):
            return self._wait(day, "cooldown")
        last_reason = "not_ready"
        for template in self.templates.values():
            if template.id in self.consumed_template_ids:
                continue
            reason, formation = self.readiness_reason(
                template, day=day, agents=agents, locations=locations,
                institution_growth=institution_growth, location_growth=location_growth,
                economy=economy, materials=materials, activity_records=activity_records,
            )
            if reason != "eligible":
                last_reason = reason
                continue
            sequence = self.next_sequence
            record = CommerceActivationRecord(
                id=f"commerce-activation:{sequence:04d}", event_key=event_key,
                template_id=template.id, institution_formation_id=formation.id,
                institution_id=formation.institution_id,
                location_id=formation.location_id,
                location_activation_id=formation.location_activation_id,
                operator_agent_id=formation.employee_agent_id,
                operator_employment_id=formation.employment_id,
                institution_account_id=formation.employer_account_id,
                inventory_id=f"inventory:institution:{sequence:04d}",
                seller_id=f"seller:institution:{sequence:04d}",
                recipe_id=f"recipe:institution:{sequence:04d}:garden_meals",
                purchase_activity_id=template.purchase_activity_id,
                upstream_seller_id=template.upstream_seller_id,
                review_day=day,
            )
            review = CommerceReview(
                event_key, day, "proposed", "eligible", record.id, template.id,
            )
            self.next_sequence += 1
            self.activation_records.append(record)
            self.review_history.append(review)
            self._trim_reviews()
            self.processed_event_keys = {item.event_key for item in self.review_history}
            return review
        return self._wait(day, last_reason)

    def activate(self, activation_id: str, *, day: int) -> CommerceActivationRecord:
        record = next((item for item in self.activation_records
                       if item.id == activation_id), None)
        if record is None or record.status != "proposed":
            raise ValueError("commerce activation is not pending")
        record.status = "activated"
        record.reason = "activated"
        record.activation_day = day
        self.consumed_template_ids.add(record.template_id)
        self.last_activation_day = day
        self.public_history.append({
            "activation_id": record.id, "day": day,
            "institution_id": record.institution_id, "seller_id": record.seller_id,
            "location_id": record.location_id,
        })
        self.public_history = self.public_history[-self.policy.history_limit:]
        review = next(item for item in self.review_history
                      if item.event_key == record.event_key)
        review.status = "activated"
        review.reason = "activated"
        self._validate_state()
        return record

    def reject(self, activation_id: str, reason: str) -> None:
        record = next((item for item in self.activation_records
                       if item.id == activation_id), None)
        if record is None or record.status != "proposed":
            return
        record.status = "rejected"
        record.reason = reason or "rejected"
        review = next(item for item in self.review_history
                      if item.event_key == record.event_key)
        review.status = "rejected"
        review.reason = record.reason

