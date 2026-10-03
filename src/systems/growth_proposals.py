"""Bounded, untrusted proposals for V5 resident and location templates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Protocol

from src.systems.location_growth import KNOWN_LOCATION_AFFINITIES, LocationTemplate
from src.systems.town_growth import ResidentTemplate


PROPOSAL_ID_PATTERN = re.compile(r"growth-proposal:(\d{4,})")
RESIDENT_TEMPLATE_PATTERN = re.compile(r"generated_resident_template_(\d{4,})")
LOCATION_TEMPLATE_PATTERN = re.compile(r"generated_location_template_(\d{4,})")
LOCATION_ID_PATTERN = re.compile(r"generated_location_(\d{4,})")
KINDS = {"resident", "location"}
STATUSES = {"admitted", "rejected"}


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_digest(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _positive(value: object, name: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be a bounded integer")
    return value


class GrowthProposalProvider(Protocol):
    """A provider sees only a copied context and returns untrusted data."""

    provider_kind: str

    def propose_resident(self, context: dict) -> object | None: ...

    def propose_location(self, context: dict) -> object | None: ...


@dataclass(frozen=True)
class ProceduralGrowthPolicy:
    enabled: bool = False
    earliest_proposal_day: int = 1
    review_interval_days: int = 7
    proposal_cooldown_days: int = 0
    resident_proposal_capacity: int = 0
    location_proposal_capacity: int = 0
    history_limit: int = 32

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("procedural growth enabled must be boolean")
        for name in ("earliest_proposal_day", "review_interval_days", "history_limit"):
            _positive(getattr(self, name), name)
        for name in (
            "proposal_cooldown_days", "resident_proposal_capacity",
            "location_proposal_capacity",
        ):
            _positive(getattr(self, name), name, allow_zero=True)
        if self.history_limit < (
            self.resident_proposal_capacity + self.location_proposal_capacity
        ):
            raise ValueError("proposal history must hold every bounded attempt")


@dataclass(frozen=True)
class GrowthProposalRecord:
    id: str
    kind: str
    proposal_day: int
    status: str
    reason: str
    canonical_payload: dict | None
    canonical_payload_hash: str | None
    generated_template_id: str | None
    provider_kind: str
    admission_day: int | None

    def __post_init__(self) -> None:
        if (
            PROPOSAL_ID_PATTERN.fullmatch(self.id or "") is None
            or self.kind not in KINDS
            or self.status not in STATUSES
            or not isinstance(self.reason, str) or not self.reason
            or not isinstance(self.provider_kind, str) or not self.provider_kind
            or len(self.provider_kind) > 80
        ):
            raise ValueError("invalid growth proposal record")
        _positive(self.proposal_day, "proposal day")
        if self.status == "admitted":
            if (
                not isinstance(self.canonical_payload, dict)
                or payload_digest(self.canonical_payload) != self.canonical_payload_hash
                or not isinstance(self.generated_template_id, str)
                or not self.generated_template_id
                or self.admission_day != self.proposal_day
            ):
                raise ValueError("admitted proposal lacks canonical binding")
        elif any(value is not None for value in (
            self.canonical_payload, self.canonical_payload_hash,
            self.generated_template_id, self.admission_day,
        )):
            raise ValueError("rejected proposal cannot claim admitted authority")

    @classmethod
    def from_dict(cls, data: dict) -> "GrowthProposalRecord":
        fields = set(cls.__dataclass_fields__)
        if not isinstance(data, dict) or set(data) != fields:
            raise ValueError("growth proposal record has an invalid schema")
        return cls(**data)


class GrowthProposalSystem:
    """Own proposal attempts and admitted generated-template provenance only."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        policy: ProceduralGrowthPolicy,
        *,
        provider: GrowthProposalProvider | None = None,
        records: list[GrowthProposalRecord] | None = None,
        resident_templates: list[ResidentTemplate] | None = None,
        location_templates: list[LocationTemplate] | None = None,
        next_proposal_sequence: int = 1,
        next_resident_template_sequence: int = 1,
        next_location_template_sequence: int = 1,
        last_attempt_day: int | None = None,
        configured_resident_template_ids: set[str] | None = None,
        configured_location_template_ids: set[str] | None = None,
        base_resident_names: set[str] | None = None,
        base_location_ids: set[str] | None = None,
        base_location_names: set[str] | None = None,
    ):
        resident_template_list = list(resident_templates or ())
        location_template_list = list(location_templates or ())
        if len({item.id for item in resident_template_list}) != len(resident_template_list):
            raise ValueError("generated resident template ids must be unique")
        if len({item.id for item in location_template_list}) != len(location_template_list):
            raise ValueError("generated location template ids must be unique")
        self.policy = policy
        self.provider = provider
        self.records = list(records or ())
        self.resident_templates = {item.id: item for item in resident_template_list}
        self.location_templates = {item.id: item for item in location_template_list}
        self.next_proposal_sequence = _positive(
            next_proposal_sequence, "next proposal sequence"
        )
        self.next_resident_template_sequence = _positive(
            next_resident_template_sequence, "next resident template sequence"
        )
        self.next_location_template_sequence = _positive(
            next_location_template_sequence, "next location template sequence"
        )
        self.last_attempt_day = last_attempt_day
        self.configured_resident_template_ids = set(configured_resident_template_ids or ())
        self.configured_location_template_ids = set(configured_location_template_ids or ())
        self.base_resident_names = set(base_resident_names or ())
        self.base_location_ids = set(base_location_ids or ())
        self.base_location_names = set(base_location_names or ())
        self._validate_state()

    @classmethod
    def from_config(
        cls, config: dict, *, agents: list, locations: list,
        state: dict | None = None, provider: GrowthProposalProvider | None = None,
    ) -> "GrowthProposalSystem":
        resident_data = config.get("templates", [])
        location_section = config.get("location_growth", {})
        location_data = location_section.get("templates", [])
        procedural = config.get("procedural_growth")
        if procedural is None:
            policy = ProceduralGrowthPolicy()
        elif not isinstance(procedural, dict) or set(procedural) != {"policy"}:
            raise ValueError("procedural growth config has an invalid schema")
        else:
            if not isinstance(procedural["policy"], dict):
                raise ValueError("procedural growth policy must be an object")
            policy = ProceduralGrowthPolicy(**procedural["policy"])
        configured_resident_ids = {item.get("id") for item in resident_data}
        configured_location_ids = {item.get("id") for item in location_data}
        configured_location_entity_ids = {
            item.get("location_id") for item in location_data
            if isinstance(item, dict)
        }
        if any(
            isinstance(item, str) and RESIDENT_TEMPLATE_PATTERN.fullmatch(item)
            for item in configured_resident_ids
        ) or any(
            isinstance(item, str) and LOCATION_TEMPLATE_PATTERN.fullmatch(item)
            for item in configured_location_ids
        ) or any(
            isinstance(item, str) and LOCATION_ID_PATTERN.fullmatch(item)
            for item in configured_location_entity_ids
        ):
            raise ValueError("checked-in configuration uses a generated namespace")
        common = dict(
            provider=provider,
            configured_resident_template_ids=configured_resident_ids,
            configured_location_template_ids=configured_location_ids,
            base_resident_names=(
                ({item.name for item in agents} - {
                    item.get("name") for item in (state or {}).get("resident_templates", [])
                    if isinstance(item, dict)
                })
                | {item.get("name") for item in resident_data if isinstance(item, dict)}
            ),
            base_location_ids=(
                {item.id for item in locations}
                | {item.get("location_id") for item in location_data if isinstance(item, dict)}
            ),
            base_location_names=(
                {item.name for item in locations}
                | {item.get("name") for item in location_data if isinstance(item, dict)}
            ),
        )
        if state is None:
            return cls(policy, **common)
        if procedural is None:
            raise ValueError("save contains procedural authority without configuration")
        allowed = {
            "schema_version", "records", "resident_templates", "location_templates",
            "next_proposal_sequence", "next_resident_template_sequence",
            "next_location_template_sequence", "last_attempt_day",
        }
        if not isinstance(state, dict) or set(state) != allowed:
            raise ValueError("procedural growth state has an invalid schema")
        if state.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("unsupported procedural growth schema version")
        if any(not isinstance(state.get(name), list) for name in (
            "records", "resident_templates", "location_templates",
        )):
            raise ValueError("procedural growth collections must be lists")
        return cls(
            policy,
            records=[GrowthProposalRecord.from_dict(x) for x in state["records"]],
            resident_templates=[ResidentTemplate.from_dict(x) for x in state["resident_templates"]],
            location_templates=[LocationTemplate.from_dict(x) for x in state["location_templates"]],
            next_proposal_sequence=state["next_proposal_sequence"],
            next_resident_template_sequence=state["next_resident_template_sequence"],
            next_location_template_sequence=state["next_location_template_sequence"],
            last_attempt_day=state["last_attempt_day"],
            **common,
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "records": [asdict(item) for item in self.records],
            "resident_templates": [
                self.resident_templates[key].to_dict()
                for key in sorted(self.resident_templates)
            ],
            "location_templates": [
                asdict(self.location_templates[key]) | {
                    "affinities": list(self.location_templates[key].affinities)
                }
                for key in sorted(self.location_templates)
            ],
            "next_proposal_sequence": self.next_proposal_sequence,
            "next_resident_template_sequence": self.next_resident_template_sequence,
            "next_location_template_sequence": self.next_location_template_sequence,
            "last_attempt_day": self.last_attempt_day,
        }

    @staticmethod
    def _clean_text(value: object, name: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be text")
        value = " ".join(value.split())
        if not value or len(value) > maximum:
            raise ValueError(f"{name} has an invalid length")
        return value

    def _parse_candidate(self, candidate: object) -> dict:
        if isinstance(candidate, str):
            if len(candidate) > 4096:
                raise ValueError("provider output is too large")
            candidate = json.loads(candidate)
        if not isinstance(candidate, dict):
            raise ValueError("provider output must be a JSON object")
        return candidate

    def _resident_payload(self, candidate: object) -> dict:
        data = self._parse_candidate(candidate)
        if set(data) != {"name", "personality", "goals"}:
            raise ValueError("resident proposal has an invalid schema")
        goals = data["goals"]
        if not isinstance(goals, list) or not 1 <= len(goals) <= 3:
            raise ValueError("resident goals must be a bounded list")
        payload = {
            "name": self._clean_text(data["name"], "resident name", 80),
            "personality": self._clean_text(data["personality"], "personality", 300),
            "goals": [self._clean_text(item, "goal", 160) for item in goals],
        }
        names = self.base_resident_names | {
            item.name for item in self.resident_templates.values()
        }
        if payload["name"].casefold() in {item.casefold() for item in names}:
            raise ValueError("resident name already exists")
        return payload

    def _location_payload(self, candidate: object) -> dict:
        data = self._parse_candidate(candidate)
        if set(data) != {"name", "description", "affinities"}:
            raise ValueError("location proposal has an invalid schema")
        affinities = data["affinities"]
        if (
            not isinstance(affinities, list)
            or not 1 <= len(affinities) <= len(KNOWN_LOCATION_AFFINITIES)
            or any(not isinstance(item, str) for item in affinities)
            or len(affinities) != len(set(affinities))
            or not set(affinities).issubset(KNOWN_LOCATION_AFFINITIES)
        ):
            raise ValueError("location affinities are invalid")
        payload = {
            "name": self._clean_text(data["name"], "location name", 80),
            "description": self._clean_text(data["description"], "description", 500),
            "affinities": sorted(affinities),
        }
        names = self.base_location_names | {
            item.name for item in self.location_templates.values()
        }
        if payload["name"].casefold() in {item.casefold() for item in names}:
            raise ValueError("location name already exists")
        return payload

    def _attempt_count(self, kind: str) -> int:
        return sum(item.kind == kind for item in self.records)

    def remaining_capacity(self, kind: str) -> int:
        capacity = (
            self.policy.resident_proposal_capacity if kind == "resident"
            else self.policy.location_proposal_capacity
        )
        return max(0, capacity - self._attempt_count(kind))

    def _next_kind(self) -> str | None:
        available = [kind for kind in ("resident", "location") if self.remaining_capacity(kind)]
        if not available:
            return None
        previous = self.records[-1].kind if self.records else None
        return next((kind for kind in available if kind != previous), available[0])

    def build_context(
        self, *, completed_day: int, agents: list, locations: list,
        activity_records: list[dict], town_history: list[dict],
        location_history: list[dict],
    ) -> dict:
        first_day = max(1, completed_day - 6)
        aggregates = []
        for day in range(first_day, completed_day + 1):
            rows = [x for x in activity_records if x.get("type") == "activity" and x.get("day") == day]
            aggregates.append({
                "day": day,
                "activity_count": len(rows),
                "active_resident_count": len({x.get("agent_id") for x in rows}),
            })
        history = [
            {key: row.get(key) for key in ("event_key", "day", "location_id", "template_id") if key in row}
            for row in (town_history[-5:] + location_history[-5:])
        ][-10:]
        return {
            "completed_day": completed_day,
            "population_count": len(agents),
            "resident_names": sorted(item.name for item in agents)[:100],
            "active_locations": [
                {"id": item.id, "name": item.name} for item in sorted(locations, key=lambda x: x.id)[:100]
            ],
            "recent_aggregate_activity": aggregates,
            "available_location_affinities": sorted(KNOWN_LOCATION_AFFINITIES),
            "admitted_generated_resident_templates": len(self.resident_templates),
            "admitted_generated_location_templates": len(self.location_templates),
            "remaining_resident_capacity": self.remaining_capacity("resident"),
            "remaining_location_capacity": self.remaining_capacity("location"),
            "recent_growth_history": history,
        }

    def review(self, *, day: int, context: dict) -> GrowthProposalRecord | None:
        _positive(day, "proposal review day")
        if not self.policy.enabled or self.provider is None:
            return None
        kind = self._next_kind()
        if kind is None or day < self.policy.earliest_proposal_day:
            return None
        if (day - self.policy.earliest_proposal_day) % self.policy.review_interval_days:
            return None
        if self.last_attempt_day is not None and (
            day - self.last_attempt_day < self.policy.proposal_cooldown_days
        ):
            return None
        proposal_id = f"growth-proposal:{self.next_proposal_sequence:04d}"
        provider_metadata = getattr(self.provider, "provider_kind", None)
        provider_kind = (
            provider_metadata.strip()[:80]
            if isinstance(provider_metadata, str) and provider_metadata.strip()
            else type(self.provider).__name__[:80]
        )
        try:
            candidate = (
                self.provider.propose_resident(dict(context))
                if kind == "resident" else self.provider.propose_location(dict(context))
            )
        except Exception as error:
            rejection_reason = f"provider_exception:{type(error).__name__}"
            record = GrowthProposalRecord(
                proposal_id, kind, day, "rejected", rejection_reason,
                None, None, None, provider_kind, None,
            )
        else:
            try:
                if candidate is None:
                    raise ValueError("provider returned no candidate")
                payload = (
                    self._resident_payload(candidate) if kind == "resident"
                    else self._location_payload(candidate)
                )
                if kind == "resident":
                    sequence = self.next_resident_template_sequence
                    template_id = f"generated_resident_template_{sequence:04d}"
                    if template_id in self.configured_resident_template_ids:
                        raise ValueError("generated resident template collides with configuration")
                    template = ResidentTemplate(
                        id=template_id, name=payload["name"],
                        personality=payload["personality"], goals=tuple(payload["goals"]),
                        initial_needs=(("knowledge", 50), ("social", 50), ("wealth", 50)),
                    )
                else:
                    sequence = self.next_location_template_sequence
                    template_id = f"generated_location_template_{sequence:04d}"
                    location_id = f"generated_location_{sequence:04d}"
                    if (
                        template_id in self.configured_location_template_ids
                        or location_id in self.base_location_ids
                        or location_id in {item.location_id for item in self.location_templates.values()}
                    ):
                        raise ValueError("generated location identity collides")
                    template = LocationTemplate(
                        id=template_id, location_id=location_id, name=payload["name"],
                        description=payload["description"], affinities=tuple(payload["affinities"]),
                    )
            except Exception as error:
                reason = f"invalid_candidate:{type(error).__name__}: {error}"[:200]
                record = GrowthProposalRecord(
                    proposal_id, kind, day, "rejected", reason, None, None, None,
                    provider_kind, None,
                )
            else:
                record = GrowthProposalRecord(
                    proposal_id, kind, day, "admitted", "admitted", payload,
                    payload_digest(payload), template_id, provider_kind, day,
                )
                if kind == "resident":
                    self.resident_templates[template_id] = template
                    self.next_resident_template_sequence += 1
                else:
                    self.location_templates[template_id] = template
                    self.next_location_template_sequence += 1
        self.records.append(record)
        self.records = self.records[-self.policy.history_limit:]
        self.next_proposal_sequence += 1
        self.last_attempt_day = day
        self._validate_state()
        return record

    def _validate_state(self) -> None:
        if len(self.records) > self.policy.history_limit:
            raise ValueError("proposal history exceeds configured bound")
        ids = [item.id for item in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("proposal ids must be unique")
        if self._attempt_count("resident") > self.policy.resident_proposal_capacity:
            raise ValueError("resident proposal capacity exceeded")
        if self._attempt_count("location") > self.policy.location_proposal_capacity:
            raise ValueError("location proposal capacity exceeded")
        admitted = [item for item in self.records if item.status == "admitted"]
        admitted_ids = [item.generated_template_id for item in admitted]
        if len(admitted_ids) != len(set(admitted_ids)):
            raise ValueError("generated template ids must be unique")
        expected_resident = {item.generated_template_id for item in admitted if item.kind == "resident"}
        expected_location = {item.generated_template_id for item in admitted if item.kind == "location"}
        if expected_resident != set(self.resident_templates) or expected_location != set(self.location_templates):
            raise ValueError("admitted proposals and generated templates disagree")
        if set(self.resident_templates) & self.configured_resident_template_ids:
            raise ValueError("generated resident template collides with configuration")
        if set(self.location_templates) & self.configured_location_template_ids:
            raise ValueError("generated location template collides with configuration")
        records = {item.generated_template_id: item for item in admitted}
        for template_id, template in self.resident_templates.items():
            record = records.get(template_id)
            payload = record.canonical_payload if record else None
            if (
                RESIDENT_TEMPLATE_PATTERN.fullmatch(template_id) is None
                or payload is None
                or set(payload) != {"name", "personality", "goals"}
                or payload != {
                    "name": self._clean_text(payload.get("name"), "resident name", 80),
                    "personality": self._clean_text(
                        payload.get("personality"), "personality", 300
                    ),
                    "goals": [
                        self._clean_text(item, "goal", 160)
                        for item in payload.get("goals", [])
                    ],
                }
                or not 1 <= len(payload["goals"]) <= 3
                or template != ResidentTemplate(
                    id=template_id, name=payload["name"], personality=payload["personality"],
                    goals=tuple(payload["goals"]),
                    initial_needs=(("knowledge", 50), ("social", 50), ("wealth", 50)),
                )
            ):
                raise ValueError("resident template contradicts its proposal")
        generated_location_ids = []
        for template_id, template in self.location_templates.items():
            record = records.get(template_id)
            payload = record.canonical_payload if record else None
            match = LOCATION_TEMPLATE_PATTERN.fullmatch(template_id)
            expected_location_id = f"generated_location_{int(match.group(1)):04d}" if match else ""
            if (
                match is None or payload is None
                or set(payload) != {"name", "description", "affinities"}
                or payload != {
                    "name": self._clean_text(payload.get("name"), "location name", 80),
                    "description": self._clean_text(
                        payload.get("description"), "description", 500
                    ),
                    "affinities": sorted(payload.get("affinities", [])),
                }
                or not 1 <= len(payload["affinities"]) <= len(KNOWN_LOCATION_AFFINITIES)
                or len(payload["affinities"]) != len(set(payload["affinities"]))
                or not set(payload["affinities"]).issubset(KNOWN_LOCATION_AFFINITIES)
                or template != LocationTemplate(
                    id=template_id, location_id=expected_location_id,
                    name=payload["name"], description=payload["description"],
                    affinities=tuple(payload["affinities"]),
                )
            ):
                raise ValueError("location template contradicts its proposal")
            generated_location_ids.append(template.location_id)
        if (
            len(generated_location_ids) != len(set(generated_location_ids))
            or set(generated_location_ids) & self.base_location_ids
            or len({item.name.casefold() for item in self.resident_templates.values()}
                   | {item.casefold() for item in self.base_resident_names})
            != len(self.resident_templates) + len({item.casefold() for item in self.base_resident_names})
            or len({item.name.casefold() for item in self.location_templates.values()}
                   | {item.casefold() for item in self.base_location_names})
            != len(self.location_templates) + len({item.casefold() for item in self.base_location_names})
        ):
            raise ValueError("generated template identity conflicts with the world")
        proposal_sequences = [int(PROPOSAL_ID_PATTERN.fullmatch(item.id).group(1)) for item in self.records]
        resident_sequences = [int(RESIDENT_TEMPLATE_PATTERN.fullmatch(item).group(1)) for item in self.resident_templates]
        location_sequences = [int(LOCATION_TEMPLATE_PATTERN.fullmatch(item).group(1)) for item in self.location_templates]
        if self.next_proposal_sequence <= max(proposal_sequences, default=0):
            raise ValueError("next proposal sequence was rewound")
        if proposal_sequences != list(range(1, len(self.records) + 1)):
            raise ValueError("proposal sequence is not contiguous")
        if self.next_proposal_sequence != len(self.records) + 1:
            raise ValueError("next proposal sequence contradicts bounded history")
        if self.next_resident_template_sequence <= max(resident_sequences, default=0):
            raise ValueError("next resident template sequence was rewound")
        if sorted(resident_sequences) != list(range(1, len(resident_sequences) + 1)):
            raise ValueError("resident template sequence is not contiguous")
        if self.next_resident_template_sequence != len(resident_sequences) + 1:
            raise ValueError("next resident template sequence is inconsistent")
        if self.next_location_template_sequence <= max(location_sequences, default=0):
            raise ValueError("next location template sequence was rewound")
        if sorted(location_sequences) != list(range(1, len(location_sequences) + 1)):
            raise ValueError("location template sequence is not contiguous")
        if self.next_location_template_sequence != len(location_sequences) + 1:
            raise ValueError("next location template sequence is inconsistent")
        if self.last_attempt_day != (max((item.proposal_day for item in self.records), default=None)):
            raise ValueError("last proposal attempt day is inconsistent")

    def validate_bindings(self, town_growth, location_growth) -> None:
        for template_id, template in self.resident_templates.items():
            if town_growth.templates.get(template_id) != template:
                raise ValueError("generated resident lacks admitted proposal authority")
        for template_id, template in self.location_templates.items():
            if location_growth.templates.get(template_id) != template:
                raise ValueError("generated location lacks admitted proposal authority")
        for record in town_growth.migration_records:
            if record.template_id.startswith("generated_") and record.template_id not in self.resident_templates:
                raise ValueError("migration references an unauthorized generated template")
        for record in location_growth.activation_records:
            if record.template_id.startswith("generated_") and record.template_id not in self.location_templates:
                raise ValueError("location activation references an unauthorized generated template")


class LLMGrowthProposalProvider:
    """Optional adapter over the repository's existing LLM client."""

    provider_kind = "existing_llm_client"

    def __init__(self, llm_client):
        self.llm_client = llm_client

    def propose_resident(self, context: dict) -> object:
        return self.llm_client.generate_growth_proposal("resident", context)

    def propose_location(self, context: dict) -> object:
        return self.llm_client.generate_growth_proposal("location", context)
