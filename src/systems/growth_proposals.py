"""Bounded, untrusted proposals for V5 growth templates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from copy import deepcopy
import hashlib
import json
import re
from typing import Protocol, TYPE_CHECKING

from src.systems.persistence_validation import require_record_fields

from src.systems.location_growth import KNOWN_LOCATION_AFFINITIES, LocationTemplate
from src.systems.event_ecology import (
    DynamicEventTemplate,
    EventEcologyPolicy,
    KNOWN_DYNAMIC_EVENT_TAGS,
)
from src.systems.institution_growth import (
    InstitutionGrowthPolicy,
    InstitutionRoleTemplate,
    InstitutionTemplate,
)
from src.systems.town_growth import ResidentTemplate
from src.systems.commerce_growth import CommerceTemplate, CommerceGrowthSystem

if TYPE_CHECKING:
    from src.systems.economy import EconomySystem
    from src.systems.materials import MaterialSystem
    from src.systems.institution_growth import InstitutionGrowthSystem
    from src.systems.location_growth import LocationGrowthSystem


PROPOSAL_ID_PATTERN = re.compile(r"growth-proposal:(\d{4,})")
RESIDENT_TEMPLATE_PATTERN = re.compile(r"generated_resident_template_(\d{4,})")
LOCATION_TEMPLATE_PATTERN = re.compile(r"generated_location_template_(\d{4,})")
LOCATION_ID_PATTERN = re.compile(r"generated_location_(\d{4,})")
EVENT_TEMPLATE_PATTERN = re.compile(r"generated_event_template_(\d{4,})")
INSTITUTION_TEMPLATE_PATTERN = re.compile(
    r"generated_institution_template_(\d{4,})"
)
COMMERCE_TEMPLATE_PATTERN = re.compile(r"generated_commerce_template_(\d{4,})")
KINDS = {"resident", "location", "event", "institution", "commerce"}
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

    def propose_event(self, context: dict) -> object | None: ...

    def propose_institution(self, context: dict) -> object | None: ...

    def propose_commerce(self, context: dict) -> object | None: ...


@dataclass(frozen=True)
class ProceduralGrowthPolicy:
    enabled: bool = False
    earliest_proposal_day: int = 1
    review_interval_days: int = 7
    proposal_cooldown_days: int = 0
    resident_proposal_capacity: int = 0
    location_proposal_capacity: int = 0
    event_proposal_capacity: int = 0
    event_templates_per_location: int = 1
    institution_proposal_capacity: int = 0
    institution_templates_per_location: int = 1
    generated_institution_wage: int = 18
    generated_institution_startup_grant: int = 300
    generated_institution_funding_source_account_id: str = (
        "account:employer:town_services"
    )
    commerce_proposal_capacity: int = 0
    commerce_archetypes: tuple[str, ...] = ("community_meals",)
    history_limit: int = 32

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("procedural growth enabled must be boolean")
        for name in ("earliest_proposal_day", "review_interval_days", "history_limit"):
            _positive(getattr(self, name), name)
        for name in (
            "proposal_cooldown_days", "resident_proposal_capacity",
            "location_proposal_capacity", "event_proposal_capacity",
            "institution_proposal_capacity", "commerce_proposal_capacity",
        ):
            _positive(getattr(self, name), name, allow_zero=True)
        if self.history_limit < (
            self.resident_proposal_capacity + self.location_proposal_capacity
            + self.event_proposal_capacity
            + self.institution_proposal_capacity + self.commerce_proposal_capacity
        ):
            raise ValueError("proposal history must hold every bounded attempt")
        if (
            not isinstance(self.commerce_archetypes, (tuple, list))
            or tuple(self.commerce_archetypes) != ("community_meals",)
        ):
            raise ValueError("unsupported bounded commerce archetypes")
        _positive(self.event_templates_per_location, "event templates per location")
        _positive(
            self.institution_templates_per_location,
            "institution templates per location",
        )
        _positive(self.generated_institution_wage, "generated institution wage")
        _positive(
            self.generated_institution_startup_grant,
            "generated institution startup grant",
        )
        if self.generated_institution_wage > 1_000:
            raise ValueError("generated institution wage exceeds bound")
        if self.generated_institution_startup_grant > 1_000_000:
            raise ValueError("generated institution startup grant exceeds bound")
        if (
            not isinstance(
                self.generated_institution_funding_source_account_id, str
            )
            or not self.generated_institution_funding_source_account_id.strip()
        ):
            raise ValueError("generated institution funding source is invalid")


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
    target_location_template_id: str | None = None
    target_institution_template_id: str | None = None

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
            _positive(self.admission_day, "admission day")
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
        if self.kind in {"event", "institution", "commerce"}:
            if (
                not isinstance(self.target_location_template_id, str)
                or LOCATION_TEMPLATE_PATTERN.fullmatch(
                    self.target_location_template_id
                ) is None
            ):
                raise ValueError("targeted proposal lacks a generated-location target")
        elif self.target_location_template_id is not None:
            raise ValueError("untargeted proposal cannot claim a location target")

        if self.kind == "commerce":
            if INSTITUTION_TEMPLATE_PATTERN.fullmatch(
                self.target_institution_template_id or ""
            ) is None:
                raise ValueError("commerce lacks generated institution target")
        elif self.target_institution_template_id is not None:
            raise ValueError("noncommerce proposal claims institution target")

    @classmethod
    def from_dict(cls, data: dict) -> "GrowthProposalRecord":
        fields = set(cls.__dataclass_fields__)
        if not isinstance(data, dict) or set(data) != fields:
            raise ValueError("growth proposal record has an invalid schema")
        return cls(**data)


class GrowthProposalSystem:
    """Own proposal attempts and admitted generated-template provenance only."""

    SCHEMA_VERSION = 4

    def __init__(
        self,
        policy: ProceduralGrowthPolicy,
        *,
        provider: GrowthProposalProvider | None = None,
        records: list[GrowthProposalRecord] | None = None,
        resident_templates: list[ResidentTemplate] | None = None,
        location_templates: list[LocationTemplate] | None = None,
        event_templates: list[DynamicEventTemplate] | None = None,
        institution_templates: list[InstitutionTemplate] | None = None,
        commerce_templates: list[CommerceTemplate] | None = None,
        next_commerce_template_sequence: int = 1,
        next_proposal_sequence: int = 1,
        next_resident_template_sequence: int = 1,
        next_location_template_sequence: int = 1,
        next_event_template_sequence: int = 1,
        next_institution_template_sequence: int = 1,
        last_attempt_day: int | None = None,
        configured_resident_template_ids: set[str] | None = None,
        configured_location_template_ids: set[str] | None = None,
        configured_event_template_ids: set[str] | None = None,
        configured_institution_template_ids: set[str] | None = None,
        configured_institution_keys: set[str] | None = None,
        configured_institution_names: set[str] | None = None,
        configured_role_template_ids: set[str] | None = None,
        configured_work_activity_ids: set[str] | None = None,
        base_resident_names: set[str] | None = None,
        base_location_ids: set[str] | None = None,
        base_location_names: set[str] | None = None,
        event_policy: EventEcologyPolicy | None = None,
        institution_policy: InstitutionGrowthPolicy | None = None,
    ):
        resident_template_list = list(resident_templates or ())
        location_template_list = list(location_templates or ())
        event_template_list = list(event_templates or ())
        institution_template_list = list(institution_templates or ())
        if len({item.id for item in resident_template_list}) != len(resident_template_list):
            raise ValueError("generated resident template ids must be unique")
        if len({item.id for item in location_template_list}) != len(location_template_list):
            raise ValueError("generated location template ids must be unique")
        if len({item.id for item in event_template_list}) != len(event_template_list):
            raise ValueError("generated event template ids must be unique")
        if len({item.id for item in institution_template_list}) != len(
            institution_template_list
        ):
            raise ValueError("generated institution template ids must be unique")
        commerce_list = list(commerce_templates or ())
        if len({item.id for item in commerce_list}) != len(commerce_list):
            raise ValueError("generated commerce template ids must be unique")
        self.commerce_templates = {item.id: item for item in commerce_list}
        self.next_commerce_template_sequence = _positive(
            next_commerce_template_sequence, "next commerce template sequence"
        )
        self.policy = policy
        self.provider = provider
        self.records = list(records or ())
        self.resident_templates = {item.id: item for item in resident_template_list}
        self.location_templates = {item.id: item for item in location_template_list}
        self.event_templates = {item.id: item for item in event_template_list}
        self.institution_templates = {
            item.id: item for item in institution_template_list
        }
        self.next_proposal_sequence = _positive(
            next_proposal_sequence, "next proposal sequence"
        )
        self.next_resident_template_sequence = _positive(
            next_resident_template_sequence, "next resident template sequence"
        )
        self.next_location_template_sequence = _positive(
            next_location_template_sequence, "next location template sequence"
        )
        self.next_event_template_sequence = _positive(
            next_event_template_sequence, "next event template sequence"
        )
        self.next_institution_template_sequence = _positive(
            next_institution_template_sequence,
            "next institution template sequence",
        )
        self.last_attempt_day = last_attempt_day
        self.configured_resident_template_ids = set(configured_resident_template_ids or ())
        self.configured_location_template_ids = set(configured_location_template_ids or ())
        self.configured_event_template_ids = set(configured_event_template_ids or ())
        self.configured_institution_template_ids = set(
            configured_institution_template_ids or ()
        )
        self.configured_institution_keys = set(configured_institution_keys or ())
        self.configured_institution_names = set(configured_institution_names or ())
        self.configured_role_template_ids = set(configured_role_template_ids or ())
        self.configured_work_activity_ids = set(configured_work_activity_ids or ())
        self.base_resident_names = set(base_resident_names or ())
        self.base_location_ids = set(base_location_ids or ())
        self.base_location_names = set(base_location_names or ())
        self.event_policy = event_policy
        self.institution_policy = institution_policy
        self._validate_state()

    @classmethod
    def from_config(
        cls, config: dict, *, agents: list, locations: list,
        state: dict | None = None, provider: GrowthProposalProvider | None = None,
    ) -> "GrowthProposalSystem":
        resident_data = config.get("templates", [])
        location_section = config.get("location_growth", {})
        location_data = location_section.get("templates", [])
        event_data = config.get("event_ecology", {}).get("templates", [])
        event_policy_data = config.get("event_ecology", {}).get("policy")
        institution_section = config.get("institution_growth", {})
        institution_data = institution_section.get("templates", [])
        institution_policy_data = institution_section.get("policy")
        event_policy = (
            EventEcologyPolicy(**event_policy_data)
            if isinstance(event_policy_data, dict)
            else EventEcologyPolicy(1, 7, 1, 1, 1, 1)
        )
        institution_policy = (
            InstitutionGrowthPolicy(**institution_policy_data)
            if isinstance(institution_policy_data, dict)
            else None
        )
        procedural = config.get("procedural_growth")
        if procedural is None:
            policy = ProceduralGrowthPolicy()
        elif not isinstance(procedural, dict) or set(procedural) != {"policy"}:
            raise ValueError("procedural growth config has an invalid schema")
        else:
            if not isinstance(procedural["policy"], dict):
                raise ValueError("procedural growth policy must be an object")
            policy = ProceduralGrowthPolicy(**procedural["policy"])
        if policy.event_proposal_capacity and not isinstance(event_policy_data, dict):
            raise ValueError("event ecology policy is required for event proposals")
        if (
            policy.institution_proposal_capacity
            and institution_policy is None
        ):
            raise ValueError(
                "institution growth policy is required for institution proposals"
            )
        if policy.commerce_proposal_capacity and (
            institution_policy is None
            or not isinstance(config.get("commerce_growth", {}).get("policy"), dict)
        ):
            raise ValueError("commerce proposals require institution and commerce policy")
        configured_resident_ids = {item.get("id") for item in resident_data}
        configured_location_ids = {item.get("id") for item in location_data}
        configured_event_ids = {item.get("id") for item in event_data}
        configured_institution_ids = {item.get("id") for item in institution_data}
        configured_institution_keys = {
            item.get("institution_key") for item in institution_data
        }
        configured_institution_names = {item.get("name") for item in institution_data}
        configured_role_ids = {
            item.get("role", {}).get("role_template_id")
            for item in institution_data if isinstance(item, dict)
        }
        configured_activity_ids = {
            item.get("role", {}).get("work_activity_id")
            for item in institution_data if isinstance(item, dict)
        }
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
        ) or any(
            isinstance(item, str) and EVENT_TEMPLATE_PATTERN.fullmatch(item)
            for item in configured_event_ids
        ) or any(
            isinstance(item, str) and INSTITUTION_TEMPLATE_PATTERN.fullmatch(item)
            for item in configured_institution_ids
        ):
            raise ValueError("checked-in configuration uses a generated namespace")
        common = dict(
            provider=provider,
            configured_resident_template_ids=configured_resident_ids,
            configured_location_template_ids=configured_location_ids,
            configured_event_template_ids=configured_event_ids,
            configured_institution_template_ids=configured_institution_ids,
            configured_institution_keys=configured_institution_keys,
            configured_institution_names=configured_institution_names,
            configured_role_template_ids=configured_role_ids,
            configured_work_activity_ids=configured_activity_ids,
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
            event_policy=event_policy,
            institution_policy=institution_policy,
        )
        if state is None:
            return cls(policy, **common)
        if procedural is None:
            raise ValueError("save contains procedural authority without configuration")
        if not isinstance(state, dict):
            raise ValueError("procedural growth state has an invalid schema")
        version = state.get("schema_version")
        _positive(version, "procedural growth schema version")
        if version in {1, 2, 3}:
            # Historical schemas are fixed contracts. Deriving them from the
            # current dataclass could accidentally admit a future authority field.
            legacy_fields = {
                "id", "kind", "proposal_day", "status", "reason",
                "canonical_payload", "canonical_payload_hash",
                "generated_template_id", "provider_kind", "admission_day",
            }
            if version > 1:
                legacy_fields.add("target_location_template_id")
            legacy_kinds = {
                1: {"resident", "location"},
                2: {"resident", "location", "event"},
                3: {"resident", "location", "event", "institution"},
            }[version]
            if not isinstance(state.get("records"), list) or any(
                not isinstance(item, dict) or set(item) != legacy_fields
                or item.get("kind") not in legacy_kinds
                for item in state["records"]
            ):
                raise ValueError("legacy proposal record has an invalid schema")
        if version == 1:
            legacy_allowed = {
                "schema_version", "records", "resident_templates", "location_templates",
                "next_proposal_sequence", "next_resident_template_sequence",
                "next_location_template_sequence", "last_attempt_day",
            }
            if set(state) != legacy_allowed:
                raise ValueError("procedural growth v1 state has an invalid schema")
            state = dict(state)
            state["schema_version"] = 2
            state["records"] = [dict(item, target_location_template_id=None)
                                for item in state["records"]]
            state["event_templates"] = []
            state["next_event_template_sequence"] = 1
            version = 2
        if version == 2:
            phase_two_allowed = {
                "schema_version", "records", "resident_templates",
                "location_templates", "event_templates",
                "next_proposal_sequence", "next_resident_template_sequence",
                "next_location_template_sequence", "next_event_template_sequence",
                "last_attempt_day",
            }
            if set(state) != phase_two_allowed:
                raise ValueError("procedural growth v2 state has an invalid schema")
            state = dict(state)
            state["schema_version"] = 3
            state["institution_templates"] = []
            state["next_institution_template_sequence"] = 1
            version = 3
        if version == 3:
            phase_three_allowed = {
                "schema_version", "records", "resident_templates",
                "location_templates", "event_templates", "institution_templates",
                "next_proposal_sequence", "next_resident_template_sequence",
                "next_location_template_sequence", "next_event_template_sequence",
                "next_institution_template_sequence", "last_attempt_day",
            }
            if set(state) != phase_three_allowed:
                raise ValueError("procedural growth v3 state has invalid schema")
            state = dict(state)
            state["schema_version"] = 4
            state["records"] = [dict(item, target_institution_template_id=None)
                                for item in state["records"]]
            state["commerce_templates"] = []
            state["next_commerce_template_sequence"] = 1
        allowed = {
            "commerce_templates", "next_commerce_template_sequence",
            "schema_version", "records", "resident_templates", "location_templates",
            "event_templates",
            "institution_templates",
            "next_proposal_sequence", "next_resident_template_sequence",
            "next_location_template_sequence", "next_event_template_sequence",
            "next_institution_template_sequence",
            "last_attempt_day",
        }
        if not isinstance(state, dict) or set(state) != allowed:
            raise ValueError("procedural growth state has an invalid schema")
        if state.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("unsupported procedural growth schema version")
        if any(not isinstance(state.get(name), list) for name in (
            "records", "resident_templates", "location_templates", "event_templates",
            "institution_templates", "commerce_templates",
        )):
            raise ValueError("procedural growth collections must be lists")
        for collection, record_type in (
            ("resident_templates", ResidentTemplate),
            ("location_templates", LocationTemplate),
            ("event_templates", DynamicEventTemplate),
            ("institution_templates", InstitutionTemplate),
            ("commerce_templates", CommerceTemplate),
        ):
            for item in state[collection]:
                require_record_fields(item, record_type)
        return cls(
            policy,
            commerce_templates=[CommerceTemplate.from_dict(x)
                                for x in state["commerce_templates"]],
            next_commerce_template_sequence=state["next_commerce_template_sequence"],
            records=[GrowthProposalRecord.from_dict(x) for x in state["records"]],
            resident_templates=[ResidentTemplate.from_dict(x) for x in state["resident_templates"]],
            location_templates=[LocationTemplate.from_dict(x) for x in state["location_templates"]],
            event_templates=[DynamicEventTemplate.from_dict(x) for x in state["event_templates"]],
            institution_templates=[
                InstitutionTemplate.from_dict(x)
                for x in state["institution_templates"]
            ],
            next_proposal_sequence=state["next_proposal_sequence"],
            next_resident_template_sequence=state["next_resident_template_sequence"],
            next_location_template_sequence=state["next_location_template_sequence"],
            next_event_template_sequence=state["next_event_template_sequence"],
            next_institution_template_sequence=state[
                "next_institution_template_sequence"
            ],
            last_attempt_day=state["last_attempt_day"],
            **common,
        )

    def to_dict(self) -> dict:
        return {
            "commerce_templates": [asdict(self.commerce_templates[key])
                                   for key in sorted(self.commerce_templates)],
            "next_commerce_template_sequence": self.next_commerce_template_sequence,
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
            "event_templates": [
                asdict(self.event_templates[key]) | {
                    "tags": list(self.event_templates[key].tags),
                    "required_affinities": list(
                        self.event_templates[key].required_affinities
                    ),
                }
                for key in sorted(self.event_templates)
            ],
            "institution_templates": [
                asdict(self.institution_templates[key]) | {
                    "relevant_dynamic_event_template_ids": list(
                        self.institution_templates[
                            key
                        ].relevant_dynamic_event_template_ids
                    ),
                    "role": asdict(self.institution_templates[key].role),
                }
                for key in sorted(self.institution_templates)
            ],
            "next_proposal_sequence": self.next_proposal_sequence,
            "next_resident_template_sequence": self.next_resident_template_sequence,
            "next_location_template_sequence": self.next_location_template_sequence,
            "next_event_template_sequence": self.next_event_template_sequence,
            "next_institution_template_sequence": (
                self.next_institution_template_sequence
            ),
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

    def _event_payload(self, candidate: object, target: LocationTemplate) -> dict:
        data = self._parse_candidate(candidate)
        if set(data) != {"name", "description", "tags", "required_affinities"}:
            raise ValueError("event proposal has an invalid schema")
        tags = data["tags"]
        affinities = data["required_affinities"]
        if (
            not isinstance(tags, list) or not 1 <= len(tags) <= 6
            or any(not isinstance(item, str) for item in tags)
            or len(tags) != len(set(tags))
            or not set(tags).issubset(KNOWN_DYNAMIC_EVENT_TAGS)
        ):
            raise ValueError("event tags are invalid")
        if (
            not isinstance(affinities, list) or not affinities
            or any(not isinstance(item, str) for item in affinities)
            or len(affinities) != len(set(affinities))
            or not set(affinities).issubset(KNOWN_LOCATION_AFFINITIES)
            or not set(affinities).issubset(target.affinities)
        ):
            raise ValueError("event affinity requirements are invalid")
        payload = {
            "name": self._clean_text(data["name"], "event name", 80),
            "description": self._clean_text(
                data["description"], "event description", 500
            ),
            "tags": sorted(tags),
            "required_affinities": sorted(affinities),
        }
        existing_names = {
            item.name.casefold() for item in self.event_templates.values()
            if item.location_template_id == target.id
        }
        if payload["name"].casefold() in existing_names:
            raise ValueError("event name already exists at target")
        return payload

    def _institution_payload(self, candidate: object) -> dict:
        data = self._parse_candidate(candidate)
        if set(data) != {"name", "role_title", "work_activity_name"}:
            raise ValueError("institution proposal has an invalid schema")
        payload = {
            "name": self._clean_text(data["name"], "institution name", 80),
            "role_title": self._clean_text(
                data["role_title"], "institution role title", 80
            ),
            "work_activity_name": self._clean_text(
                data["work_activity_name"], "institution work activity", 120
            ),
        }
        names = self.configured_institution_names | {
            item.name for item in self.institution_templates.values()
        }
        if payload["name"].casefold() in {
            item.casefold() for item in names if isinstance(item, str)
        }:
            raise ValueError("institution name already exists")
        return payload

    def _commerce_payload(self, candidate: object) -> dict:
        data = self._parse_candidate(candidate)
        if set(data) != {"offer"} or data["offer"] not in self.policy.commerce_archetypes:
            raise ValueError("commerce proposal must select a permitted offer only")
        return {"offer": data["offer"]}

    def derive_commerce_template(
        self, template_id: str, institution_id: str, location_id: str,
    ) -> CommerceTemplate:
        match = COMMERCE_TEMPLATE_PATTERN.fullmatch(template_id or "")
        institution = self.institution_templates.get(institution_id)
        if (match is None or institution is None
                or institution.location_template_id != location_id
                or location_id not in self.location_templates):
            raise ValueError("commerce lacks exact generated target authority")
        sequence = int(match.group(1))
        return CommerceTemplate(
            template_id, institution_id, location_id, "seller:market_stall",
            "meal_ingredients", 2, "prepared_meal", 4,
            f"generated_purchase_activity_{sequence:04d}",
            institution.role.work_activity_id,
            f"generated_meals_{sequence:04d}", 8,
        )

    def select_commerce_target(
        self, *, day: int, commerce_growth: CommerceGrowthSystem,
        institution_growth: InstitutionGrowthSystem, location_growth: LocationGrowthSystem,
        economy: EconomySystem, materials: MaterialSystem, agents: list, locations: list,
        activity_records: list[dict], prior_records: list | None = None,
    ) -> dict | None:
        prior = self.records if prior_records is None else prior_records
        used = {item.target_institution_template_id for item in prior
                if item.kind == "commerce" and item.status == "admitted"}
        candidates = []
        for target_id in sorted(self.institution_templates):
            if target_id in used:
                continue
            institution = self.institution_templates[target_id]
            if institution_growth.templates.get(target_id) != institution:
                continue
            template = self.derive_commerce_template(
                "generated_commerce_template_0001", target_id,
                institution.location_template_id,
            )
            reason, formation = commerce_growth.readiness_reason(
                template, day=day + 1, agents=agents, locations=locations,
                institution_growth=institution_growth, location_growth=location_growth,
                economy=economy, materials=materials, activity_records=activity_records,
                historical=True,
            )
            if reason != "eligible" or formation.activation_day > day:
                continue
            candidates.append((formation.activation_day, target_id, {
                "institution_template_id": target_id,
                "location_template_id": institution.location_template_id,
                "name": institution.name,
                "place": self.location_templates[institution.location_template_id].name,
            }))
        return min(candidates, key=lambda item: item[:2])[2] if candidates else None

    def validate_commerce_bindings(
        self, commerce_growth: CommerceGrowthSystem, *,
        institution_growth: InstitutionGrowthSystem, location_growth: LocationGrowthSystem,
        economy: EconomySystem, materials: MaterialSystem, agents: list, locations: list,
        activity_records: list[dict],
    ) -> None:
        self._validate_state()
        generated = {key: value for key, value in commerce_growth.templates.items()
                     if key.startswith("generated_")}
        if generated != self.commerce_templates:
            raise ValueError("generated commerce lacks admitted authority")
        prior = []
        for record in self.records:
            if record.kind == "commerce":
                target = self.select_commerce_target(
                    day=record.proposal_day, commerce_growth=commerce_growth,
                    institution_growth=institution_growth, location_growth=location_growth,
                    economy=economy, materials=materials, agents=agents,
                    locations=locations, activity_records=activity_records,
                    prior_records=prior,
                )
                if (target is None
                        or target["institution_template_id"] != record.target_institution_template_id
                        or target["location_template_id"] != record.target_location_template_id):
                    raise ValueError("commerce proposal target selection is invalid")
            prior.append(record)
        admissions = {item.generated_template_id: item.admission_day
                      for item in self.records if item.kind == "commerce"
                      and item.status == "admitted"}
        if commerce_growth.generated_admission_days != admissions:
            raise ValueError("commerce admission days contradict proposals")
        for activation in commerce_growth.activation_records:
            if activation.template_id.startswith("generated_") and (
                activation.template_id not in admissions
                or activation.review_day <= admissions[activation.template_id]
            ):
                raise ValueError("commerce activation predates admitted authority")

    def _attempt_count(self, kind: str) -> int:
        return sum(item.kind == kind for item in self.records)

    def remaining_capacity(self, kind: str) -> int:
        capacity = {
            "resident": self.policy.resident_proposal_capacity,
            "location": self.policy.location_proposal_capacity,
            "event": self.policy.event_proposal_capacity,
            "institution": self.policy.institution_proposal_capacity,
            "commerce": self.policy.commerce_proposal_capacity,
        }[kind]
        return max(0, capacity - self._attempt_count(kind))

    def _next_kind(
        self, *, event_available: bool = False,
        institution_available: bool = False, commerce_available: bool = False,
    ) -> str | None:
        available = [
            kind for kind in ("resident", "location", "event", "institution", "commerce")
            if self.remaining_capacity(kind)
            and (kind != "event" or event_available)
            and (kind != "institution" or institution_available)
            and (kind != "commerce" or commerce_available)
        ]
        if not available:
            return None
        previous = self.records[-1].kind if self.records else None
        return next((kind for kind in available if kind != previous), available[0])

    def build_context(
        self, *, completed_day: int, agents: list, locations: list,
        activity_records: list[dict], town_history: list[dict],
        location_history: list[dict],
        location_growth=None,
        event_ecology=None,
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
        target = self.select_event_target(
            completed_day=completed_day, locations=locations,
            activity_records=activity_records, location_growth=location_growth,
        )
        institution_target = self.select_institution_target(
            completed_day=completed_day, locations=locations,
            activity_records=activity_records, location_growth=location_growth,
            event_ecology=event_ecology,
        )
        result = {
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
            "remaining_event_capacity": self.remaining_capacity("event"),
            "remaining_institution_capacity": self.remaining_capacity(
                "institution"
            ),
            "recent_growth_history": history,
        }
        if target is not None:
            template, location, activation, recent = target
            result["event_target"] = {
                "location_template_id": template.id,
                "location_id": location.id,
                "name": location.name,
                "description": location.description,
                "affinities": list(template.affinities),
                "activation_day": activation.activation_day,
                "recent_use": recent,
                "permitted_tags": sorted(KNOWN_DYNAMIC_EVENT_TAGS),
                "permitted_affinities": sorted(template.affinities),
                "remaining_location_event_capacity": (
                    self.policy.event_templates_per_location
                    - sum(item.location_template_id == template.id
                          for item in self.event_templates.values())
                ),
                "admitted_event_names": sorted(
                    item.name for item in self.event_templates.values()
                    if item.location_template_id == template.id
                ),
            }
        if institution_target is not None:
            template, location, activation, recent, event_ids, first_event_day = (
                institution_target
            )
            result["institution_target"] = {
                "location_template_id": template.id,
                "location_id": location.id,
                "name": location.name,
                "description": location.description,
                "affinities": list(template.affinities),
                "activation_day": activation.activation_day,
                "recent_use": recent,
                "observed_generated_events": [
                    {
                        "name": self.event_templates[event_id].name,
                        "description": self.event_templates[event_id].description,
                    }
                    for event_id in event_ids
                ],
                "relevant_dynamic_event_template_ids": list(event_ids),
                "oldest_generated_event_day": first_event_day,
                "remaining_location_institution_capacity": (
                    self.policy.institution_templates_per_location
                    - sum(
                        item.location_template_id == template.id
                        for item in self.institution_templates.values()
                    )
                ),
            }
        return result

    def select_institution_target(
        self, *, completed_day: int, locations: list,
        activity_records: list[dict], location_growth, event_ecology,
    ):
        """Choose a generated place from authoritative use and occurrence history."""
        if (
            location_growth is None or event_ecology is None
            or self.institution_policy is None
        ):
            return None
        active = {item.id: item for item in locations}
        first_day = (
            completed_day - self.institution_policy.recent_activity_window_days + 1
        )
        candidates = []
        for template in self.location_templates.values():
            activation = next((
                item for item in location_growth.activation_records
                if item.status == "activated" and item.template_id == template.id
                and item.location_id == template.location_id
                and item.activation_day is not None
                and item.activation_day <= completed_day
            ), None)
            location = active.get(template.location_id)
            if activation is None or location is None or (
                location.name != template.name
                or location.description != template.description
                or tuple(location.affinities or ()) != template.affinities
            ):
                continue
            admitted_count = sum(
                item.location_template_id == template.id
                for item in self.institution_templates.values()
            )
            if admitted_count >= self.policy.institution_templates_per_location:
                continue
            generated_event_ids = {
                item.id for item in self.event_templates.values()
                if item.location_template_id == template.id
                and event_ecology.templates.get(item.id) == item
            }
            occurrences = [
                item for item in event_ecology.occurrence_history
                if item.template_id in generated_event_ids
                and item.location_id == template.location_id
                and item.day <= completed_day
            ]
            event_ids = tuple(sorted({item.template_id for item in occurrences}))
            if (
                not event_ids
                or len(occurrences)
                < self.institution_policy.minimum_dynamic_event_occurrences
            ):
                continue
            recent_rows = [
                row for row in activity_records
                if row.get("type") == "activity"
                and row.get("location") == location.id
                and first_day <= row.get("day", -1) <= completed_day
            ]
            residents = {
                row.get("agent_id") for row in recent_rows
                if isinstance(row.get("agent_id"), str)
            }
            days = {row.get("day") for row in recent_rows}
            if (
                len(residents) < self.institution_policy.minimum_distinct_residents
                or len(days) < self.institution_policy.minimum_activity_days
            ):
                continue
            last_target_day = max((
                item.proposal_day for item in self.records
                if item.kind == "institution"
                and item.target_location_template_id == template.id
            ), default=0)
            first_event_day = min(item.day for item in occurrences)
            recent = {
                "activity_count": len(recent_rows),
                "distinct_resident_count": len(residents),
                "activity_day_count": len(days),
                "generated_event_occurrence_count": len(occurrences),
            }
            candidates.append((
                admitted_count, activation.activation_day, first_event_day,
                last_target_day, template.id, template, location, activation,
                recent, event_ids,
            ))
        if not candidates:
            return None
        selected = min(candidates, key=lambda item: item[:5])
        return (
            selected[5], selected[6], selected[7], selected[8], selected[9],
            selected[2],
        )

    def select_event_target(
        self, *, completed_day: int, locations: list, activity_records: list[dict],
        location_growth,
    ):
        if location_growth is None or self.event_policy is None:
            return None
        active = {item.id: item for item in locations}
        first_day = completed_day - self.event_policy.recent_activity_window_days + 1
        candidates = []
        for template in self.location_templates.values():
            activation = next((
                item for item in location_growth.activation_records
                if item.status == "activated" and item.template_id == template.id
                and item.location_id == template.location_id
            ), None)
            location = active.get(template.location_id)
            if activation is None or location is None:
                continue
            if (
                location.name != template.name
                or location.description != template.description
                or tuple(location.affinities or ()) != template.affinities
            ):
                continue
            admitted_count = sum(
                item.location_template_id == template.id
                for item in self.event_templates.values()
            )
            if admitted_count >= self.policy.event_templates_per_location:
                continue
            recent_rows = [
                row for row in activity_records
                if row.get("type") == "activity"
                and row.get("location") == location.id
                and first_day <= row.get("day", -1) <= completed_day
            ]
            residents = sorted({
                row.get("agent_id") for row in recent_rows
                if isinstance(row.get("agent_id"), str)
            })
            days = sorted({row.get("day") for row in recent_rows})
            if (
                activation.activation_day is None
                or completed_day - activation.activation_day
                < self.event_policy.minimum_location_age_days
                or len(residents) < self.event_policy.minimum_distinct_residents
                or len(days) < self.event_policy.minimum_activity_days
            ):
                continue
            last_target_day = max((
                item.proposal_day for item in self.records
                if item.kind == "event"
                and item.target_location_template_id == template.id
            ), default=0)
            recent = {
                "activity_count": len(recent_rows),
                "distinct_resident_count": len(residents),
                "activity_day_count": len(days),
            }
            candidates.append((
                admitted_count, activation.activation_day, last_target_day,
                template.id, template, location, activation, recent,
            ))
        if not candidates:
            return None
        selected = min(candidates, key=lambda item: item[:4])
        return selected[4], selected[5], selected[6], selected[7]

    def review(self, *, day: int, context: dict) -> GrowthProposalRecord | None:
        _positive(day, "proposal review day")
        if not self.policy.enabled or self.provider is None:
            return None
        event_context = context.get("event_target")
        event_target_id = (
            event_context.get("location_template_id")
            if isinstance(event_context, dict) else None
        )
        institution_context = context.get("institution_target")
        institution_target_id = (
            institution_context.get("location_template_id")
            if isinstance(institution_context, dict) else None
        )
        commerce_context = context.get("commerce_target")
        commerce_target_id = (commerce_context.get("institution_template_id")
                              if isinstance(commerce_context, dict) else None)
        commerce_location_id = (commerce_context.get("location_template_id")
                                if isinstance(commerce_context, dict) else None)
        kind = self._next_kind(
            commerce_available=commerce_target_id in self.institution_templates,
            event_available=event_target_id in self.location_templates,
            institution_available=(
                institution_target_id in self.location_templates
            ),
        )
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
            if kind == "resident":
                candidate = self.provider.propose_resident(deepcopy(context))
            elif kind == "location":
                candidate = self.provider.propose_location(deepcopy(context))
            elif kind == "event":
                candidate = self.provider.propose_event(deepcopy({
                    "completed_day": context.get("completed_day"),
                    "target_location": event_context,
                    "remaining_event_capacity": self.remaining_capacity("event"),
                }))
            elif kind == "commerce":
                candidate = self.provider.propose_commerce(deepcopy({
                    "target_institution": commerce_context["name"],
                    "target_place": commerce_context["place"],
                    "observed_evidence": "sustained work, local use and meal purchases",
                    "permitted_offers": list(self.policy.commerce_archetypes),
                }))
            else:
                semantic_target = {
                    key: value for key, value in institution_context.items()
                    if key not in {
                        "location_template_id",
                        "relevant_dynamic_event_template_ids",
                    }
                }
                candidate = self.provider.propose_institution(deepcopy({
                    "completed_day": context.get("completed_day"),
                    "target_location": semantic_target,
                    "remaining_institution_capacity": self.remaining_capacity(
                        "institution"
                    ),
                }))
        except Exception as error:
            rejection_reason = f"provider_exception:{type(error).__name__}"
            record = GrowthProposalRecord(
                proposal_id, kind, day, "rejected", rejection_reason,
                None, None, None, provider_kind, None,
                (
                    event_target_id if kind == "event"
                    else institution_target_id if kind == "institution"
                    else commerce_location_id if kind == "commerce"
                    else None
                ),
                commerce_target_id if kind == "commerce" else None,
            )
        else:
            try:
                if candidate is None:
                    raise ValueError("provider returned no candidate")
                if kind == "resident":
                    payload = self._resident_payload(candidate)
                elif kind == "location":
                    payload = self._location_payload(candidate)
                elif kind == "event":
                    target = self.location_templates.get(event_target_id)
                    if target is None:
                        raise ValueError("event target lacks generated-location authority")
                    payload = self._event_payload(candidate, target)
                elif kind == "commerce":
                    payload = self._commerce_payload(candidate)
                else:
                    if institution_target_id not in self.location_templates:
                        raise ValueError(
                            "institution target lacks generated-location authority"
                        )
                    payload = self._institution_payload(candidate)
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
                elif kind == "location":
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
                elif kind == "event":
                    sequence = self.next_event_template_sequence
                    template_id = f"generated_event_template_{sequence:04d}"
                    if template_id in self.configured_event_template_ids:
                        raise ValueError("generated event template collides with configuration")
                    template = DynamicEventTemplate(
                        id=template_id,
                        name=payload["name"],
                        description=payload["description"],
                        tags=tuple(payload["tags"]),
                        required_affinities=tuple(payload["required_affinities"]),
                        location_template_id=event_target_id,
                        minimum_location_age_days=self.event_policy.minimum_location_age_days,
                        minimum_distinct_residents=self.event_policy.minimum_distinct_residents,
                        minimum_activity_days=self.event_policy.minimum_activity_days,
                        cooldown_days=max(
                            14, self.event_policy.dynamic_selection_interval_days
                        ),
                    )
                elif kind == "commerce":
                    sequence = self.next_commerce_template_sequence
                    template_id = f"generated_commerce_template_{sequence:04d}"
                    template = self.derive_commerce_template(
                        template_id, commerce_target_id, commerce_location_id
                    )
                else:
                    sequence = self.next_institution_template_sequence
                    template_id = (
                        f"generated_institution_template_{sequence:04d}"
                    )
                    institution_key = f"generated_institution_key_{sequence:04d}"
                    role_id = f"generated_role_template_{sequence:04d}"
                    activity_id = f"generated_work_activity_{sequence:04d}"
                    if (
                        template_id in self.configured_institution_template_ids
                        or institution_key in self.configured_institution_keys
                        or role_id in self.configured_role_template_ids
                        or activity_id in self.configured_work_activity_ids
                    ):
                        raise ValueError(
                            "generated institution identity collides with configuration"
                        )
                    event_ids = tuple(
                        institution_context.get(
                            "relevant_dynamic_event_template_ids", ()
                        )
                    )
                    if not event_ids:
                        raise ValueError(
                            "institution target lacks generated-event authority"
                        )
                    template = InstitutionTemplate(
                        id=template_id,
                        institution_key=institution_key,
                        name=payload["name"],
                        location_template_id=institution_target_id,
                        startup_funding_source_account_id=(
                            self.policy.
                            generated_institution_funding_source_account_id
                        ),
                        startup_grant=(
                            self.policy.generated_institution_startup_grant
                        ),
                        relevant_dynamic_event_template_ids=event_ids,
                        role=InstitutionRoleTemplate(
                            role_template_id=role_id,
                            title=payload["role_title"],
                            wage=self.policy.generated_institution_wage,
                            work_activity_id=activity_id,
                            work_activity_name=payload["work_activity_name"],
                        ),
                    )
            except Exception as error:
                reason = f"invalid_candidate:{type(error).__name__}: {error}"[:200]
                record = GrowthProposalRecord(
                    proposal_id, kind, day, "rejected", reason, None, None, None,
                    provider_kind, None,
                    (
                        event_target_id if kind == "event"
                        else institution_target_id if kind == "institution"
                        else commerce_location_id if kind == "commerce"
                        else None
                    ),
                    commerce_target_id if kind == "commerce" else None,
                )
            else:
                record = GrowthProposalRecord(
                    proposal_id, kind, day, "admitted", "admitted", payload,
                    payload_digest(payload), template_id, provider_kind, day,
                    (
                        event_target_id if kind == "event"
                        else institution_target_id if kind == "institution"
                        else commerce_location_id if kind == "commerce"
                        else None
                    ),
                    commerce_target_id if kind == "commerce" else None,
                )
                if kind == "resident":
                    self.resident_templates[template_id] = template
                    self.next_resident_template_sequence += 1
                elif kind == "location":
                    self.location_templates[template_id] = template
                    self.next_location_template_sequence += 1
                elif kind == "event":
                    self.event_templates[template_id] = template
                    self.next_event_template_sequence += 1
                elif kind == "commerce":
                    self.commerce_templates[template_id] = template
                    self.next_commerce_template_sequence += 1
                else:
                    self.institution_templates[template_id] = template
                    self.next_institution_template_sequence += 1
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
        if self._attempt_count("event") > self.policy.event_proposal_capacity:
            raise ValueError("event proposal capacity exceeded")
        if (
            self._attempt_count("institution")
            > self.policy.institution_proposal_capacity
        ):
            raise ValueError("institution proposal capacity exceeded")
        if self._attempt_count("commerce") > self.policy.commerce_proposal_capacity:
            raise ValueError("commerce proposal capacity exceeded")
        admitted = [item for item in self.records if item.status == "admitted"]
        admitted_ids = [item.generated_template_id for item in admitted]
        if len(admitted_ids) != len(set(admitted_ids)):
            raise ValueError("generated template ids must be unique")
        if {item.generated_template_id for item in admitted
            if item.kind == "commerce"} != set(self.commerce_templates):
            raise ValueError("admitted commerce proposals and templates disagree")
        for template_id, template in self.commerce_templates.items():
            record = next(item for item in admitted
                          if item.generated_template_id == template_id)
            if (self._commerce_payload(record.canonical_payload)
                    != record.canonical_payload
                    or template != self.derive_commerce_template(
                        template_id, record.target_institution_template_id,
                        record.target_location_template_id)):
                raise ValueError("commerce template contradicts proposal")
        if [item.generated_template_id for item in admitted if item.kind == "commerce"] != [
            f"generated_commerce_template_{sequence:04d}"
            for sequence in range(1, len(self.commerce_templates) + 1)
        ]:
            raise ValueError("commerce admission identities are not monotonic")
        commerce_sequences = sorted(int(COMMERCE_TEMPLATE_PATTERN.fullmatch(key).group(1))
                                    for key in self.commerce_templates)
        if (commerce_sequences != list(range(1, len(commerce_sequences) + 1))
                or self.next_commerce_template_sequence != len(commerce_sequences) + 1):
            raise ValueError("commerce template sequence is inconsistent")
        if len({item.institution_template_id for item in self.commerce_templates.values()}) != len(self.commerce_templates):
            raise ValueError("duplicate commerce institution target")
        expected_resident = {item.generated_template_id for item in admitted if item.kind == "resident"}
        expected_location = {item.generated_template_id for item in admitted if item.kind == "location"}
        expected_event = {item.generated_template_id for item in admitted if item.kind == "event"}
        expected_institution = {
            item.generated_template_id for item in admitted
            if item.kind == "institution"
        }
        if (
            expected_resident != set(self.resident_templates)
            or expected_location != set(self.location_templates)
            or expected_event != set(self.event_templates)
            or expected_institution != set(self.institution_templates)
        ):
            raise ValueError("admitted proposals and generated templates disagree")
        if set(self.resident_templates) & self.configured_resident_template_ids:
            raise ValueError("generated resident template collides with configuration")
        if set(self.location_templates) & self.configured_location_template_ids:
            raise ValueError("generated location template collides with configuration")
        if set(self.event_templates) & self.configured_event_template_ids:
            raise ValueError("generated event template collides with configuration")
        if (
            set(self.institution_templates)
            & self.configured_institution_template_ids
        ):
            raise ValueError(
                "generated institution template collides with configuration"
            )
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
        event_names_by_location: dict[str, set[str]] = {}
        for template_id, template in self.event_templates.items():
            record = records.get(template_id)
            payload = record.canonical_payload if record else None
            match = EVENT_TEMPLATE_PATTERN.fullmatch(template_id)
            target = self.location_templates.get(template.location_template_id)
            if (
                match is None or payload is None or target is None
                or record.target_location_template_id != template.location_template_id
                or set(payload) != {
                    "name", "description", "tags", "required_affinities"
                }
                or payload != {
                    "name": self._clean_text(payload.get("name"), "event name", 80),
                    "description": self._clean_text(
                        payload.get("description"), "event description", 500
                    ),
                    "tags": sorted(payload.get("tags", [])),
                    "required_affinities": sorted(
                        payload.get("required_affinities", [])
                    ),
                }
                or not 1 <= len(payload["tags"]) <= 6
                or len(payload["tags"]) != len(set(payload["tags"]))
                or not set(payload["tags"]).issubset(KNOWN_DYNAMIC_EVENT_TAGS)
                or not payload["required_affinities"]
                or len(payload["required_affinities"])
                != len(set(payload["required_affinities"]))
                or not set(payload["required_affinities"]).issubset(target.affinities)
                or template != DynamicEventTemplate(
                    id=template_id, name=payload["name"],
                    description=payload["description"], tags=tuple(payload["tags"]),
                    required_affinities=tuple(payload["required_affinities"]),
                    location_template_id=target.id,
                    minimum_location_age_days=self.event_policy.minimum_location_age_days,
                    minimum_distinct_residents=self.event_policy.minimum_distinct_residents,
                    minimum_activity_days=self.event_policy.minimum_activity_days,
                    cooldown_days=max(
                        14, self.event_policy.dynamic_selection_interval_days
                    ),
                )
            ):
                raise ValueError("event template contradicts its proposal")
            names = event_names_by_location.setdefault(target.id, set())
            if template.name.casefold() in names:
                raise ValueError("generated event names must be unique per location")
            names.add(template.name.casefold())
        if any(
            sum(item.location_template_id == target_id
                for item in self.event_templates.values())
            > self.policy.event_templates_per_location
            for target_id in self.location_templates
        ):
            raise ValueError("generated event per-location capacity exceeded")
        institution_names = {
            item.casefold() for item in self.configured_institution_names
            if isinstance(item, str)
        }
        institution_keys = set(self.configured_institution_keys)
        role_ids = set(self.configured_role_template_ids)
        activity_ids = set(self.configured_work_activity_ids)
        for template_id, template in self.institution_templates.items():
            record = records.get(template_id)
            payload = record.canonical_payload if record else None
            match = INSTITUTION_TEMPLATE_PATTERN.fullmatch(template_id)
            sequence = int(match.group(1)) if match else 0
            target = self.location_templates.get(template.location_template_id)
            event_ids = template.relevant_dynamic_event_template_ids
            if (
                match is None or payload is None or target is None
                or record.target_location_template_id != target.id
                or set(payload) != {
                    "name", "role_title", "work_activity_name"
                }
                or payload != {
                    "name": self._clean_text(
                        payload.get("name"), "institution name", 80
                    ),
                    "role_title": self._clean_text(
                        payload.get("role_title"),
                        "institution role title", 80,
                    ),
                    "work_activity_name": self._clean_text(
                        payload.get("work_activity_name"),
                        "institution work activity", 120,
                    ),
                }
                or not event_ids
                or tuple(sorted(event_ids)) != event_ids
                or any(
                    event_id not in self.event_templates
                    or self.event_templates[event_id].location_template_id
                    != target.id
                    for event_id in event_ids
                )
                or template != InstitutionTemplate(
                    id=template_id,
                    institution_key=(
                        f"generated_institution_key_{sequence:04d}"
                    ),
                    name=payload["name"],
                    location_template_id=target.id,
                    startup_funding_source_account_id=(
                        self.policy.
                        generated_institution_funding_source_account_id
                    ),
                    startup_grant=(
                        self.policy.generated_institution_startup_grant
                    ),
                    relevant_dynamic_event_template_ids=event_ids,
                    role=InstitutionRoleTemplate(
                        role_template_id=(
                            f"generated_role_template_{sequence:04d}"
                        ),
                        title=payload["role_title"],
                        wage=self.policy.generated_institution_wage,
                        work_activity_id=(
                            f"generated_work_activity_{sequence:04d}"
                        ),
                        work_activity_name=payload["work_activity_name"],
                    ),
                )
                or template.name.casefold() in institution_names
                or template.institution_key in institution_keys
                or template.role.role_template_id in role_ids
                or template.role.work_activity_id in activity_ids
            ):
                raise ValueError(
                    "institution template contradicts its proposal"
                )
            institution_names.add(template.name.casefold())
            institution_keys.add(template.institution_key)
            role_ids.add(template.role.role_template_id)
            activity_ids.add(template.role.work_activity_id)
        if any(
            sum(item.location_template_id == target_id
                for item in self.institution_templates.values())
            > self.policy.institution_templates_per_location
            for target_id in self.location_templates
        ):
            raise ValueError(
                "generated institution per-location capacity exceeded"
            )
        proposal_sequences = [int(PROPOSAL_ID_PATTERN.fullmatch(item.id).group(1)) for item in self.records]
        resident_sequences = [int(RESIDENT_TEMPLATE_PATTERN.fullmatch(item).group(1)) for item in self.resident_templates]
        location_sequences = [int(LOCATION_TEMPLATE_PATTERN.fullmatch(item).group(1)) for item in self.location_templates]
        event_sequences = [int(EVENT_TEMPLATE_PATTERN.fullmatch(item).group(1)) for item in self.event_templates]
        institution_sequences = [
            int(INSTITUTION_TEMPLATE_PATTERN.fullmatch(item).group(1))
            for item in self.institution_templates
        ]
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
        if self.next_event_template_sequence <= max(event_sequences, default=0):
            raise ValueError("next event template sequence was rewound")
        if sorted(event_sequences) != list(range(1, len(event_sequences) + 1)):
            raise ValueError("event template sequence is not contiguous")
        if self.next_event_template_sequence != len(event_sequences) + 1:
            raise ValueError("next event template sequence is inconsistent")
        if self.next_institution_template_sequence <= max(
            institution_sequences, default=0
        ):
            raise ValueError("next institution template sequence was rewound")
        if sorted(institution_sequences) != list(
            range(1, len(institution_sequences) + 1)
        ):
            raise ValueError("institution template sequence is not contiguous")
        if self.next_institution_template_sequence != len(
            institution_sequences
        ) + 1:
            raise ValueError(
                "next institution template sequence is inconsistent"
            )
        if self.last_attempt_day != (max((item.proposal_day for item in self.records), default=None)):
            raise ValueError("last proposal attempt day is inconsistent")

    def validate_bindings(
        self, town_growth, location_growth, event_ecology=None,
        institution_growth=None,
        *, locations: list | None = None, activity_records: list[dict] | None = None,
    ) -> None:
        admissions = {item.generated_template_id: item.admission_day
                      for item in self.records if item.status == "admitted"}
        for records, day_field in (
            (town_growth.migration_records, "review_day"),
            (location_growth.activation_records, "review_day"),
            (event_ecology.occurrence_history if event_ecology else (), "day"),
            (institution_growth.formation_records if institution_growth else (), "review_day"),
        ):
            for record in records:
                if record.template_id.startswith("generated_") and (
                    record.template_id not in admissions
                    or getattr(record, day_field) <= admissions[record.template_id]
                ):
                    raise ValueError("generated authority predates template admission")
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
        if event_ecology is not None:
            if locations is not None and activity_records is not None:
                active = {item.id: item for item in locations}
                location_admissions = {
                    item.generated_template_id: item.admission_day
                    for item in self.records
                    if item.kind == "location" and item.status == "admitted"
                }
                prior_event_records: list[GrowthProposalRecord] = []
                for event_record in (
                    item for item in self.records if item.kind == "event"
                ):
                    first_day = (
                        event_record.proposal_day
                        - self.event_policy.recent_activity_window_days + 1
                    )
                    candidates = []
                    for location_template in self.location_templates.values():
                        if (
                            location_admissions.get(location_template.id, 10**18)
                            > event_record.proposal_day
                        ):
                            continue
                        activation = next((
                            item for item in location_growth.activation_records
                            if item.status == "activated"
                            and item.template_id == location_template.id
                            and item.location_id == location_template.location_id
                            and item.activation_day <= event_record.proposal_day
                        ), None)
                        location = active.get(location_template.location_id)
                        if activation is None or location is None or (
                            location.name != location_template.name
                            or location.description != location_template.description
                            or tuple(location.affinities or ())
                            != location_template.affinities
                        ):
                            continue
                        prior_admitted = [
                            item for item in prior_event_records
                            if item.status == "admitted"
                            and item.target_location_template_id
                            == location_template.id
                        ]
                        if len(prior_admitted) >= self.policy.event_templates_per_location:
                            continue
                        recent = [
                            row for row in activity_records
                            if row.get("type") == "activity"
                            and row.get("location") == location_template.location_id
                            and first_day <= row.get("day", -1)
                            <= event_record.proposal_day
                        ]
                        if (
                            event_record.proposal_day - activation.activation_day
                            < self.event_policy.minimum_location_age_days
                            or len({row.get("agent_id") for row in recent
                                    if isinstance(row.get("agent_id"), str)})
                            < self.event_policy.minimum_distinct_residents
                            or len({row.get("day") for row in recent})
                            < self.event_policy.minimum_activity_days
                        ):
                            continue
                        last_target_day = max((
                            item.proposal_day for item in prior_event_records
                            if item.target_location_template_id == location_template.id
                        ), default=0)
                        candidates.append((
                            len(prior_admitted), activation.activation_day,
                            last_target_day, location_template.id,
                        ))
                    expected_target = min(candidates)[3] if candidates else None
                    if event_record.target_location_template_id != expected_target:
                        raise ValueError("event proposal target selection is invalid")
                    prior_event_records.append(event_record)
            for template_id, template in self.event_templates.items():
                if event_ecology.templates.get(template_id) != template:
                    raise ValueError("generated event lacks admitted proposal authority")
                activation = next((
                    item for item in location_growth.activation_records
                    if item.status == "activated"
                    and item.template_id == template.location_template_id
                ), None)
                record = next(item for item in self.records
                              if item.generated_template_id == template_id)
                if (
                    activation is None
                    or activation.activation_day > record.admission_day
                    or record.admission_day - activation.activation_day
                    < self.event_policy.minimum_location_age_days
                ):
                    raise ValueError("generated event predates target activation")
                if locations is not None:
                    target = self.location_templates[
                        template.location_template_id
                    ]
                    location = next((item for item in locations
                                     if item.id == target.location_id), None)
                    if location is None or (
                        location.name != target.name
                        or location.description != target.description
                        or tuple(location.affinities or ()) != target.affinities
                    ):
                        raise ValueError(
                            "generated event target contradicts authority"
                        )
                if activity_records is not None:
                    first_day = (
                        record.admission_day
                        - self.event_policy.recent_activity_window_days + 1
                    )
                    recent = [
                        row for row in activity_records
                        if row.get("type") == "activity"
                        and row.get("location")
                        == self.location_templates[
                            template.location_template_id
                        ].location_id
                        and first_day <= row.get("day", -1)
                        <= record.admission_day
                    ]
                    if (
                        len({row.get("agent_id") for row in recent
                             if isinstance(row.get("agent_id"), str)})
                        < self.event_policy.minimum_distinct_residents
                        or len({row.get("day") for row in recent})
                        < self.event_policy.minimum_activity_days
                    ):
                        raise ValueError(
                            "generated event lacks sustained target use"
                        )
        if institution_growth is not None:
            if (
                locations is not None and activity_records is not None
                and event_ecology is not None
                and self.institution_policy is not None
            ):
                active = {item.id: item for item in locations}
                prior_institution_records: list[GrowthProposalRecord] = []
                event_admissions = {
                    item.generated_template_id: item.admission_day
                    for item in self.records
                    if item.kind == "event" and item.status == "admitted"
                }
                for institution_record in (
                    item for item in self.records
                    if item.kind == "institution"
                ):
                    first_day = (
                        institution_record.proposal_day
                        - self.institution_policy.recent_activity_window_days
                        + 1
                    )
                    candidates = []
                    for location_template in self.location_templates.values():
                        activation = next((
                            item for item in location_growth.activation_records
                            if item.status == "activated"
                            and item.template_id == location_template.id
                            and item.location_id == location_template.location_id
                            and item.activation_day
                            <= institution_record.proposal_day
                        ), None)
                        location = active.get(location_template.location_id)
                        if activation is None or location is None or (
                            location.name != location_template.name
                            or location.description
                            != location_template.description
                            or tuple(location.affinities or ())
                            != location_template.affinities
                        ):
                            continue
                        prior_admitted = [
                            item for item in prior_institution_records
                            if item.status == "admitted"
                            and item.target_location_template_id
                            == location_template.id
                        ]
                        if len(prior_admitted) >= (
                            self.policy.institution_templates_per_location
                        ):
                            continue
                        generated_event_ids = {
                            item.id for item in self.event_templates.values()
                            if item.location_template_id == location_template.id
                            and event_admissions.get(item.id, 10**18)
                            <= institution_record.proposal_day
                            and event_ecology.templates.get(item.id) == item
                        }
                        occurrences = [
                            item for item in event_ecology.occurrence_history
                            if item.template_id in generated_event_ids
                            and item.location_id == location_template.location_id
                            and item.day <= institution_record.proposal_day
                        ]
                        if (
                            not occurrences
                            or len(occurrences) < (
                                self.institution_policy.
                                minimum_dynamic_event_occurrences
                            )
                        ):
                            continue
                        recent = [
                            row for row in activity_records
                            if row.get("type") == "activity"
                            and row.get("location")
                            == location_template.location_id
                            and first_day <= row.get("day", -1)
                            <= institution_record.proposal_day
                        ]
                        if (
                            len({row.get("agent_id") for row in recent
                                 if isinstance(row.get("agent_id"), str)})
                            < self.institution_policy.minimum_distinct_residents
                            or len({row.get("day") for row in recent})
                            < self.institution_policy.minimum_activity_days
                        ):
                            continue
                        last_target_day = max((
                            item.proposal_day
                            for item in prior_institution_records
                            if item.target_location_template_id
                            == location_template.id
                        ), default=0)
                        candidates.append((
                            len(prior_admitted), activation.activation_day,
                            min(item.day for item in occurrences),
                            last_target_day, location_template.id,
                        ))
                    expected_target = min(candidates)[4] if candidates else None
                    if (
                        institution_record.target_location_template_id
                        != expected_target
                    ):
                        raise ValueError(
                            "institution proposal target selection is invalid"
                        )
                    prior_institution_records.append(institution_record)
            for template_id, template in self.institution_templates.items():
                if institution_growth.templates.get(template_id) != template:
                    raise ValueError(
                        "generated institution lacks admitted proposal authority"
                    )
                record = next(
                    item for item in self.records
                    if item.generated_template_id == template_id
                )
                binding = self.location_templates.get(
                    template.location_template_id
                )
                if binding is None:
                    raise ValueError(
                        "generated institution lacks generated-location authority"
                    )
                expected_event_ids = tuple(sorted({
                    occurrence.template_id
                    for occurrence in event_ecology.occurrence_history
                    if occurrence.location_id == binding.location_id
                    and occurrence.day <= record.proposal_day
                    and occurrence.template_id in self.event_templates
                    and self.event_templates[
                        occurrence.template_id
                    ].location_template_id == binding.id
                })) if event_ecology is not None else ()
                if (
                    template.relevant_dynamic_event_template_ids
                    != expected_event_ids
                ):
                    raise ValueError(
                        "generated institution event allowlist is not exact"
                    )
                for event_id in template.relevant_dynamic_event_template_ids:
                    event_template = self.event_templates.get(event_id)
                    if (
                        event_template is None
                        or event_ecology is None
                        or event_ecology.templates.get(event_id) != event_template
                        or event_template.location_template_id != binding.id
                        or not any(
                            occurrence.template_id == event_id
                            and occurrence.location_id == binding.location_id
                            and occurrence.day <= record.proposal_day
                            for occurrence in event_ecology.occurrence_history
                        )
                    ):
                        raise ValueError(
                            "generated institution has invalid event provenance"
                        )
                activation = next((
                    item for item in location_growth.activation_records
                    if item.status == "activated"
                    and item.template_id == binding.id
                    and item.location_id == binding.location_id
                    and item.activation_day <= record.proposal_day
                ), None)
                if activation is None:
                    raise ValueError(
                        "generated institution predates target activation"
                    )
                if activity_records is not None:
                    first_day = (
                        record.proposal_day
                        - self.institution_policy.recent_activity_window_days + 1
                    )
                    recent = [
                        row for row in activity_records
                        if row.get("type") == "activity"
                        and row.get("location") == binding.location_id
                        and first_day <= row.get("day", -1)
                        <= record.proposal_day
                    ]
                    if (
                        len({row.get("agent_id") for row in recent
                             if isinstance(row.get("agent_id"), str)})
                        < self.institution_policy.minimum_distinct_residents
                        or len({row.get("day") for row in recent})
                        < self.institution_policy.minimum_activity_days
                    ):
                        raise ValueError(
                            "generated institution lacks sustained target use"
                        )
            for formation in institution_growth.formation_records:
                if (
                    formation.template_id.startswith("generated_")
                    and formation.template_id not in self.institution_templates
                ):
                    raise ValueError(
                        "formation references unauthorized generated institution"
                    )


class LLMGrowthProposalProvider:
    """Optional adapter over the repository's existing LLM client."""

    provider_kind = "existing_llm_client"

    def __init__(self, llm_client):
        self.llm_client = llm_client

    def propose_resident(self, context: dict) -> object:
        return self.llm_client.generate_growth_proposal("resident", context)

    def propose_location(self, context: dict) -> object:
        return self.llm_client.generate_growth_proposal("location", context)

    def propose_event(self, context: dict) -> object:
        return self.llm_client.generate_growth_proposal("event", context)

    def propose_institution(self, context: dict) -> object:
        return self.llm_client.generate_growth_proposal("institution", context)

    def propose_commerce(self, context: dict) -> object:
        return self.llm_client.generate_growth_proposal("commerce", context)
