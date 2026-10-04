"""Bounded deterministic authority for place-local daily events."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re

from src.town.daily_event import DailyEvent, EVENT_POOL, instantiate_base_event


KNOWN_DYNAMIC_EVENT_TAGS = {
    "art", "community", "food", "help", "knowledge", "learning",
    "music", "planning", "social", "sports", "work",
}
KNOWN_LOCATION_AFFINITIES = {"social", "knowledge", "community"}
KNOWN_EVENT_SOURCES = {"base", "dynamic", "legacy"}
GENERATED_EVENT_TEMPLATE_PREFIX = "generated_event_template_"
GENERATED_EVENT_TEMPLATE_PATTERN = re.compile(r"generated_event_template_(\d{4,})")


def _positive_int(value: object, name: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True)
class EventEcologyPolicy:
    minimum_location_age_days: int
    recent_activity_window_days: int
    minimum_distinct_residents: int
    minimum_activity_days: int
    dynamic_selection_interval_days: int
    history_limit: int

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            _positive_int(value, name)


@dataclass(frozen=True)
class DynamicEventTemplate:
    id: str
    name: str
    description: str
    tags: tuple[str, ...]
    required_affinities: tuple[str, ...]
    location_template_id: str | None
    minimum_location_age_days: int
    minimum_distinct_residents: int
    minimum_activity_days: int
    cooldown_days: int

    @classmethod
    def from_dict(cls, data: dict) -> "DynamicEventTemplate":
        allowed = {
            "id", "name", "description", "tags", "required_affinities",
            "location_template_id", "minimum_location_age_days",
            "minimum_distinct_residents", "minimum_activity_days",
            "cooldown_days",
        }
        if not isinstance(data, dict) or set(data) != allowed:
            raise ValueError("dynamic event template has an invalid schema")
        if not all(isinstance(data[key], str) and data[key].strip()
                   for key in ("id", "name", "description")):
            raise ValueError("dynamic event template identity is invalid")
        tags = data["tags"]
        affinities = data["required_affinities"]
        if (not isinstance(tags, list) or not tags
                or not all(isinstance(item, str) for item in tags)
                or len(tags) != len(set(tags))
                or not set(tags).issubset(KNOWN_DYNAMIC_EVENT_TAGS)):
            raise ValueError("dynamic event template contains unknown tags")
        if (not isinstance(affinities, list) or not affinities
                or not all(isinstance(item, str) for item in affinities)
                or len(affinities) != len(set(affinities))
                or not set(affinities).issubset(KNOWN_LOCATION_AFFINITIES)):
            raise ValueError("dynamic event affinity requirements are invalid")
        binding = data["location_template_id"]
        if binding is not None and (not isinstance(binding, str) or not binding):
            raise ValueError("dynamic event location binding is invalid")
        for key in (
            "minimum_location_age_days", "minimum_distinct_residents",
            "minimum_activity_days", "cooldown_days",
        ):
            _positive_int(data[key], key, allow_zero=key == "minimum_location_age_days")
        return cls(
            data["id"], data["name"], data["description"], tuple(tags),
            tuple(affinities), binding, data["minimum_location_age_days"],
            data["minimum_distinct_residents"], data["minimum_activity_days"],
            data["cooldown_days"],
        )


@dataclass(frozen=True)
class DynamicEventOccurrenceRecord:
    occurrence_id: str
    template_id: str
    location_id: str
    day: int
    source_kind: str = "dynamic"

    def __post_init__(self) -> None:
        _positive_int(self.day, "dynamic event day")
        expected = f"daily-event:{self.day}:{self.template_id}:{self.location_id}"
        if (self.occurrence_id != expected or self.source_kind != "dynamic"
                or not self.template_id or not self.location_id):
            raise ValueError("invalid dynamic event occurrence identity")


class EventEcologySystem:
    """Selects one daily event while owning only bounded dynamic-event state."""

    SCHEMA_VERSION = 1

    def __init__(
        self, policy: EventEcologyPolicy, templates: list[DynamicEventTemplate],
        *, simulation_seed: int = 0,
        configured_template_ids: set[str] | None = None,
        generated_location_templates: dict[str, object] | None = None,
        occurrence_history: list[DynamicEventOccurrenceRecord] | None = None,
        processed_occurrence_ids: set[str] | None = None,
    ) -> None:
        if len({item.id for item in templates}) != len(templates):
            raise ValueError("dynamic event template ids must be unique")
        self.policy = policy
        self.templates = {item.id: item for item in templates}
        self.configured_template_ids = set(configured_template_ids or self.templates)
        self.generated_location_templates = dict(generated_location_templates or {})
        self.simulation_seed = int(simulation_seed)
        self.occurrence_history = list(occurrence_history or [])
        self.processed_occurrence_ids = set(processed_occurrence_ids or ())
        self._validate_state()

    @classmethod
    def from_config(
        cls, path: str | Path, *, simulation_seed: int = 0, state=None,
        supplemental_templates: list[DynamicEventTemplate] | None = None,
        generated_location_templates: dict[str, object] | None = None,
    ):
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        section = config.get("event_ecology") if isinstance(config, dict) else None
        if not isinstance(section, dict) or set(section) != {"policy", "templates"}:
            raise ValueError("event ecology config has an invalid schema")
        if not isinstance(section["policy"], dict) or not isinstance(section["templates"], list):
            raise ValueError("event ecology policy and templates have invalid shapes")
        policy = EventEcologyPolicy(**section["policy"])
        templates = [DynamicEventTemplate.from_dict(item) for item in section["templates"]]
        configured_ids = {item.id for item in templates}
        if any(item.id.startswith(GENERATED_EVENT_TEMPLATE_PREFIX) for item in templates):
            raise ValueError("checked-in event configuration uses a generated namespace")
        instance = cls(
            policy, templates, simulation_seed=simulation_seed,
            configured_template_ids=configured_ids,
            generated_location_templates=generated_location_templates,
        )
        for template in supplemental_templates or ():
            instance.register_generated_template(template)
        if state is None:
            return instance
        if not isinstance(state, dict) or state.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("unsupported event ecology schema version")
        if set(state) != {"schema_version", "occurrence_history", "processed_occurrence_ids"}:
            raise ValueError("event ecology state contains unsupported fields")
        if not isinstance(state["occurrence_history"], list) or not isinstance(
            state["processed_occurrence_ids"], list
        ):
            raise ValueError("event ecology state collections must be lists")
        return cls(
            policy, list(instance.templates.values()), simulation_seed=simulation_seed,
            configured_template_ids=configured_ids,
            generated_location_templates=generated_location_templates,
            occurrence_history=[DynamicEventOccurrenceRecord(**item)
                                for item in state["occurrence_history"]],
            processed_occurrence_ids=set(state["processed_occurrence_ids"]),
        )

    def register_generated_template(self, template: DynamicEventTemplate) -> None:
        """Register admitted procedural possibility without creating an occurrence."""
        if not isinstance(template, DynamicEventTemplate):
            raise ValueError("generated event template has an invalid type")
        if GENERATED_EVENT_TEMPLATE_PATTERN.fullmatch(template.id) is None:
            raise ValueError("generated event template uses a reserved namespace")
        if template.id in self.templates or template.id in self.configured_template_ids:
            raise ValueError("generated event template identity collides")
        location_template = self.generated_location_templates.get(
            template.location_template_id
        )
        if location_template is None:
            raise ValueError("generated event lacks generated-location authority")
        location_affinities = set(getattr(location_template, "affinities", ()))
        if not set(template.required_affinities).issubset(location_affinities):
            raise ValueError("generated event has impossible affinity requirements")
        if (
            template.minimum_location_age_days < self.policy.minimum_location_age_days
            or template.minimum_distinct_residents < self.policy.minimum_distinct_residents
            or template.minimum_activity_days < self.policy.minimum_activity_days
        ):
            raise ValueError("generated event weakens event-ecology eligibility")
        self.templates[template.id] = template

    def register_generated_location_authority(self, template_id: str, template) -> None:
        if (
            not isinstance(template_id, str)
            or not template_id.startswith("generated_location_template_")
            or getattr(template, "id", None) != template_id
        ):
            raise ValueError("invalid generated-location authority")
        existing = self.generated_location_templates.get(template_id)
        if existing is not None and existing != template:
            raise ValueError("generated-location authority contradicts registry")
        self.generated_location_templates[template_id] = template

    def to_dict(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "occurrence_history": [asdict(item) for item in self.occurrence_history],
            "processed_occurrence_ids": sorted(self.processed_occurrence_ids),
        }

    def _validate_state(self) -> None:
        ids = [item.occurrence_id for item in self.occurrence_history]
        if len(ids) != len(set(ids)):
            raise ValueError("dynamic event occurrence identities must be unique")
        if any(item.template_id not in self.templates for item in self.occurrence_history):
            raise ValueError("dynamic event occurrence references unknown template")
        if set(ids) != self.processed_occurrence_ids:
            raise ValueError("dynamic event replay guards must exactly match history")
        if len(ids) > self.policy.history_limit:
            raise ValueError("dynamic event history exceeds configured bound")

    def _bounded_hash(self, *parts: object) -> int:
        payload = "|".join(map(str, (self.simulation_seed, *parts)))
        return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big")

    @staticmethod
    def _activation_for(location_growth, location_id: str):
        return next((record for record in location_growth.activation_records
                     if record.status == "activated"
                     and record.location_id == location_id), None)

    def eligible_dynamic_candidates(
        self, *, day: int, locations: list, location_growth, activity_records: list[dict],
        ignore_occurrence_id: str | None = None,
    ) -> list[tuple[DynamicEventTemplate, object, object]]:
        active = {item.id: item for item in locations}
        first_day = day - self.policy.recent_activity_window_days
        results = []
        for template in self.templates.values():
            activations = [record for record in location_growth.activation_records
                           if record.status == "activated"
                           and (template.location_template_id is None
                                or record.template_id == template.location_template_id)]
            for activation in activations:
                location = active.get(activation.location_id)
                if location is None:
                    continue
                location_template = location_growth.templates.get(activation.template_id)
                if location_template is None or location_template.location_id != location.id:
                    continue
                affinities = set(location.affinities or ())
                if not affinities.issubset(KNOWN_LOCATION_AFFINITIES):
                    continue
                if not set(template.required_affinities).issubset(affinities):
                    continue
                minimum_age = max(
                    self.policy.minimum_location_age_days,
                    template.minimum_location_age_days,
                )
                if activation.activation_day is None or day - activation.activation_day < minimum_age:
                    continue
                recent = [record for record in activity_records
                          if record.get("type") == "activity"
                          and record.get("location") == location.id
                          and first_day <= record.get("day", -1) < day]
                residents = {record.get("agent_id") for record in recent
                             if isinstance(record.get("agent_id"), str)}
                activity_days = {record.get("day") for record in recent}
                if len(residents) < max(
                    self.policy.minimum_distinct_residents,
                    template.minimum_distinct_residents,
                ) or len(activity_days) < max(
                    self.policy.minimum_activity_days,
                    template.minimum_activity_days,
                ):
                    continue
                prior = [record.day for record in self.occurrence_history
                         if record.template_id == template.id
                         and record.location_id == location.id
                         and record.occurrence_id != ignore_occurrence_id
                         and record.day < day]
                if prior and day - max(prior) < template.cooldown_days:
                    continue
                results.append((template, location, activation))
        return sorted(results, key=lambda item: (item[0].id, item[1].id))

    def select_daily_event(
        self, *, day: int, locations: list, location_growth, activity_records: list[dict],
    ) -> DailyEvent:
        candidates = self.eligible_dynamic_candidates(
            day=day, locations=locations, location_growth=location_growth,
            activity_records=activity_records,
        )
        choose_dynamic = bool(candidates) and (
            day % self.policy.dynamic_selection_interval_days == 0
        )
        if choose_dynamic:
            # Prefer the least-served location, then its least-used template.
            # Stable seeded hashing is only a final tie-break, so deterministic
            # selection cannot indefinitely starve a later configured branch.
            def fairness_key(candidate):
                template, location, _activation = candidate
                at_location = [
                    item for item in self.occurrence_history
                    if item.location_id == location.id
                ]
                for_template = [
                    item for item in at_location if item.template_id == template.id
                ]
                last_day = max((item.day for item in for_template), default=0)
                return (
                    len(at_location), len(for_template), last_day,
                    self._bounded_hash(
                        "dynamic-tie", template.id, location.id
                    ),
                    template.id, location.id,
                )

            template, location, _activation = min(candidates, key=fairness_key)
            occurrence_id = f"daily-event:{day}:{template.id}:{location.id}"
            if occurrence_id in self.processed_occurrence_ids:
                raise ValueError("dynamic event occurrence was already processed")
            record = DynamicEventOccurrenceRecord(
                occurrence_id, template.id, location.id, day,
            )
            self.occurrence_history.append(record)
            self.occurrence_history = self.occurrence_history[-self.policy.history_limit:]
            self.processed_occurrence_ids = {
                item.occurrence_id for item in self.occurrence_history
            }
            return DailyEvent(
                id=template.id, name=template.name,
                description=template.description, location_id=location.id,
                tags=list(template.tags), template_id=template.id,
                occurrence_id=occurrence_id, day=day, source_kind="dynamic",
            )
        base = EVENT_POOL[self._bounded_hash("base", day) % len(EVENT_POOL)]
        return instantiate_base_event(base, day)

    def validate_occurrence(
        self, event: DailyEvent | None, *, current_day: int, locations: list,
        location_growth, activity_records: list[dict], require_current_day: bool = True,
    ) -> None:
        if event is None:
            return
        if event.source_kind == "legacy":
            # Backward compatibility is intentionally restricted to the old
            # five-field shape, not accepted as dynamic authority.
            if event.day is not None or event.occurrence_id != event.id:
                raise ValueError("invalid legacy daily event")
            return
        if event.source_kind not in KNOWN_EVENT_SOURCES or event.schema_version != 1:
            raise ValueError("unknown daily event source or schema")
        expected_id = f"daily-event:{event.day}:{event.template_id}:{event.location_id}"
        if event.occurrence_id != expected_id or event.id != event.template_id:
            raise ValueError("daily event occurrence identity is invalid")
        if require_current_day and event.day != current_day:
            raise ValueError("current daily event belongs to another day")
        active = {item.id: item for item in locations}
        if event.location_id not in active:
            raise ValueError("daily event location is not active")
        if event.source_kind == "base":
            template = next((item for item in EVENT_POOL if item.id == event.template_id), None)
            if template is None or any((
                event.name != template.name, event.description != template.description,
                event.location_id != template.location_id,
                event.tags != template.tags,
            )):
                raise ValueError("base daily event contradicts its template")
            return
        template = self.templates.get(event.template_id)
        if template is None or any((
            event.name != template.name, event.description != template.description,
            tuple(event.tags) != template.tags,
        )):
            raise ValueError("dynamic daily event contradicts its template")
        matching = next((item for item in self.occurrence_history
                         if item.occurrence_id == event.occurrence_id), None)
        if matching is None or matching != DynamicEventOccurrenceRecord(
            event.occurrence_id, event.template_id, event.location_id, event.day
        ):
            raise ValueError("dynamic daily event lacks occurrence provenance")
        eligible = self.eligible_dynamic_candidates(
            day=event.day, locations=locations, location_growth=location_growth,
            activity_records=activity_records,
            ignore_occurrence_id=event.occurrence_id,
        )
        if not any(item[0].id == event.template_id and item[1].id == event.location_id
                   for item in eligible):
            raise ValueError("dynamic daily event was not eligible")

    def validate(self, *, locations: list, location_growth,
                 activity_records: list[dict]) -> dict[str, bool]:
        try:
            self._validate_state()
            for record in self.occurrence_history:
                template = self.templates[record.template_id]
                event = DailyEvent(
                    template.id, template.name, template.description,
                    record.location_id, list(template.tags), template.id,
                    record.occurrence_id, record.day, "dynamic",
                )
                self.validate_occurrence(
                    event, current_day=record.day, locations=locations,
                    location_growth=location_growth, activity_records=activity_records,
                )
        except (KeyError, TypeError, ValueError):
            valid = False
        else:
            valid = True
        return {
            "event_ecology_state_valid": valid,
            "dynamic_event_histories_bounded": (
                len(self.occurrence_history) <= self.policy.history_limit
                and len(self.processed_occurrence_ids) <= self.policy.history_limit
            ),
            "dynamic_event_occurrence_ids_unique": (
                len(self.occurrence_history)
                == len({item.occurrence_id for item in self.occurrence_history})
            ),
        }
