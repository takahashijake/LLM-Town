"""Deterministic investigation, adjudication, and theft restitution authority."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from src.systems.materials import MaterialError


class JusticeError(ValueError):
    """A rejected justice operation which made no authoritative mutation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AdmittedEvidence:
    id: str
    case_id: str
    evidence_id: str
    submitted_by_agent_id: str | None
    evidence_type: str
    provenance_type: str
    claims_actor: bool
    admitted_day: int
    admitted_hour: int


@dataclass(frozen=True)
class JusticeCase:
    id: str
    incident_id: str
    opened_by_agent_id: str
    investigator_agent_id: str
    trigger_evidence_id: str
    admitted_evidence_ids: tuple[str, ...]
    status: str
    opened_day: int
    opened_hour: int
    event_key: str
    adjudication_id: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["admitted_evidence_ids"] = list(self.admitted_evidence_ids)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "JusticeCase":
        values = dict(data)
        values["admitted_evidence_ids"] = tuple(values.get("admitted_evidence_ids", ()))
        return cls(**values)


@dataclass(frozen=True)
class Adjudication:
    id: str
    case_id: str
    incident_id: str
    result: str
    responsible_actor_id: str | None
    evidence_ids: tuple[str, ...]
    theft_evidence_ids: tuple[str, ...]
    actor_identifying_evidence_ids: tuple[str, ...]
    rule_version: str
    day: int
    hour: int
    event_key: str

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("evidence_ids", "theft_evidence_ids", "actor_identifying_evidence_ids"):
            data[key] = list(data[key])
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Adjudication":
        values = dict(data)
        for key in ("evidence_ids", "theft_evidence_ids", "actor_identifying_evidence_ids"):
            values[key] = tuple(values.get(key, ()))
        return cls(**values)


@dataclass(frozen=True)
class RestitutionRecord:
    id: str
    adjudication_id: str
    incident_id: str
    responsible_actor_id: str
    victim_id: str
    good_id: str
    requested_quantity: int
    returned_quantity: int
    status: str
    material_transfer_id: str | None
    day: int
    hour: int
    event_key: str


@dataclass(frozen=True)
class ConsequenceRecord:
    id: str
    adjudication_id: str
    responsible_actor_id: str
    consequence_type: str
    reputation_value: float
    affected_agent_ids: tuple[str, ...]
    restitution_id: str
    day: int
    hour: int
    event_key: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["affected_agent_ids"] = list(self.affected_agent_ids)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ConsequenceRecord":
        values = dict(data)
        values["affected_agent_ids"] = tuple(values.get("affected_agent_ids", ()))
        return cls(**values)


class JusticeSystem:
    """Own the narrow, auditable justice pipeline for existing theft incidents."""

    SCHEMA_VERSION = 1
    CASE_STATUSES = {"open", "investigating", "ready_for_review", "adjudicated"}

    def __init__(
        self, *, crime, materials, agents: list, reputation_system=None,
        investigator_agent_ids: tuple[str, ...], rule_version: str,
        qualifying_actor_evidence: tuple[tuple[str, str], ...],
        consequence_reputation_value: float = -0.65,
        public_adjudications: bool = True, restitution_enabled: bool = True,
        cases: list[JusticeCase] | None = None,
        admitted_evidence: list[AdmittedEvidence] | None = None,
        adjudications: list[Adjudication] | None = None,
        restitutions: list[RestitutionRecord] | None = None,
        consequences: list[ConsequenceRecord] | None = None,
        applied_event_keys: set[str] | None = None,
        rejected_attempts: list[dict] | None = None,
        next_case_number: int = 1, next_admission_number: int = 1,
        next_adjudication_number: int = 1, next_restitution_number: int = 1,
        next_consequence_number: int = 1,
    ):
        self.crime, self.materials = crime, materials
        self.agents = {agent.id: agent for agent in agents}
        self.reputation_system = reputation_system
        self.investigator_agent_ids = tuple(investigator_agent_ids)
        self.rule_version = str(rule_version)
        self.qualifying_actor_evidence = tuple(qualifying_actor_evidence)
        self.consequence_reputation_value = float(consequence_reputation_value)
        self.public_adjudications = bool(public_adjudications)
        self.restitution_enabled = bool(restitution_enabled)
        self.cases = list(cases or [])
        self.admitted_evidence = list(admitted_evidence or [])
        self.adjudications = list(adjudications or [])
        self.restitutions = list(restitutions or [])
        self.consequences = list(consequences or [])
        self.applied_event_keys = set(applied_event_keys or ())
        self.rejected_attempts = list(rejected_attempts or [])
        self.next_case_number = int(next_case_number)
        self.next_admission_number = int(next_admission_number)
        self.next_adjudication_number = int(next_adjudication_number)
        self.next_restitution_number = int(next_restitution_number)
        self.next_consequence_number = int(next_consequence_number)
        self._validate_config()
        self._validate_history()

    def _validate_config(self):
        if self.rule_version != "theft-direct-eyewitness-v1" or not self.investigator_agent_ids:
            raise ValueError("justice rule version and investigators are required")
        if any(item not in self.agents for item in self.investigator_agent_ids):
            raise ValueError("justice configuration references unknown investigator")
        # This version is deliberately not configurable into a weaker standard:
        # in particular, a malformed file must never make hearsay qualifying.
        if self.qualifying_actor_evidence != (("eyewitness", "direct_observation"),):
            raise ValueError(
                "theft-direct-eyewitness-v1 requires exactly direct eyewitness evidence"
            )
        if not -1.0 <= self.consequence_reputation_value < 0:
            raise ValueError("justice reputation consequence must be in [-1, 0)")

    def _validate_history(self):
        groups = (self.cases, self.admitted_evidence, self.adjudications,
                  self.restitutions, self.consequences)
        if any(len([x.id for x in group]) != len({x.id for x in group}) for group in groups):
            raise ValueError("justice record ids must be unique")
        if len({case.incident_id for case in self.cases}) != len(self.cases):
            raise ValueError("one crime incident may have at most one justice case")
        incident_ids = {item.id for item in self.crime.incidents}
        evidence = {item.id: item for item in self.crime.evidence}
        cases = {item.id: item for item in self.cases}
        adjudications = {item.id: item for item in self.adjudications}
        if any(case.incident_id not in incident_ids or case.status not in self.CASE_STATUSES for case in self.cases):
            raise ValueError("justice case references invalid crime state")
        if any(item.case_id not in cases or item.evidence_id not in evidence for item in self.admitted_evidence):
            raise ValueError("admission references invalid case or evidence")
        if any(item.case_id not in cases for item in self.adjudications):
            raise ValueError("adjudication references invalid case")
        if any(item.adjudication_id not in adjudications for item in (*self.restitutions, *self.consequences)):
            raise ValueError("justice outcome references invalid adjudication")
        successful_keys = {
            x.event_key
            for group in (self.cases, self.adjudications, self.restitutions, self.consequences)
            for x in group
        }
        if not successful_keys.issubset(self.applied_event_keys):
            raise ValueError("justice history is missing replay guards")

    def _reject(self, code, message, **attempt):
        self.rejected_attempts.append({"code": code, **attempt})
        raise JusticeError(code, message)

    def _incident(self, incident_id):
        item = next((x for x in self.crime.incidents if x.id == incident_id), None)
        if item is None:
            self._reject("unknown_incident", "crime incident does not exist", incident_id=incident_id)
        return item

    def _evidence(self, evidence_id):
        item = next((x for x in self.crime.evidence if x.id == evidence_id), None)
        if item is None:
            self._reject("unknown_evidence", "crime evidence does not exist", evidence_id=evidence_id)
        return item

    def _admit(self, case, evidence, submitter_id, day, hour):
        existing = next((x for x in self.admitted_evidence if x.case_id == case.id and x.evidence_id == evidence.id), None)
        if existing:
            return existing
        record = AdmittedEvidence(
            id=f"justice-evidence-{self.next_admission_number:08d}", case_id=case.id,
            evidence_id=evidence.id, submitted_by_agent_id=submitter_id,
            evidence_type=evidence.evidence_type, provenance_type=evidence.provenance_type,
            claims_actor=evidence.claims_actor, admitted_day=int(day), admitted_hour=int(hour),
        )
        self.next_admission_number += 1
        self.admitted_evidence.append(record)
        index = self.cases.index(case)
        self.cases[index] = replace(case, admitted_evidence_ids=(*case.admitted_evidence_ids, record.id), status="investigating")
        return record

    def open_case(self, *, incident_id: str, opened_by_agent_id: str,
                  investigator_agent_id: str, trigger_evidence_id: str,
                  day: int, hour: int, event_key: str) -> JusticeCase:
        if event_key in self.applied_event_keys:
            self._reject("duplicate_event", "case event already applied", event_key=event_key)
        if any(x.incident_id == incident_id for x in self.cases):
            self._reject("duplicate_case", "incident already has a case", incident_id=incident_id)
        incident = self._incident(incident_id)
        if investigator_agent_id not in self.investigator_agent_ids:
            self._reject("ineligible_investigator", "agent cannot investigate", investigator_agent_id=investigator_agent_id)
        trigger = self._evidence(trigger_evidence_id)
        legitimate = (
            trigger.incident_id == incident.id and trigger.holder_agent_id == opened_by_agent_id
            and ((trigger.evidence_type == "ownership_loss" and opened_by_agent_id == incident.victim_id)
                 or (trigger.evidence_type == "eyewitness" and trigger.provenance_type == "direct_observation"))
        )
        if not legitimate:
            self._reject("invalid_case_trigger", "case requires victim discovery or direct eyewitness evidence")
        case = JusticeCase(
            id=f"justice-case-{self.next_case_number:08d}", incident_id=incident.id,
            opened_by_agent_id=opened_by_agent_id, investigator_agent_id=investigator_agent_id,
            trigger_evidence_id=trigger.id, admitted_evidence_ids=(), status="open",
            opened_day=int(day), opened_hour=int(hour), event_key=event_key,
        )
        self.next_case_number += 1
        self.cases.append(case)
        system_record = next(x for x in self.crime.evidence if x.incident_id == incident.id and x.evidence_type == "unauthorized_transfer")
        self._admit(case, system_record, None, day, hour)
        case = self.cases[-1]
        self._admit(case, trigger, opened_by_agent_id, day, hour)
        self.applied_event_keys.add(event_key)
        return self.cases[-1]

    def submit_evidence(self, *, case_id: str, submitter_agent_id: str,
                        evidence_id: str, day: int, hour: int, event_key: str) -> AdmittedEvidence:
        if event_key in self.applied_event_keys:
            self._reject("duplicate_event", "evidence submission already applied", event_key=event_key)
        case = next((x for x in self.cases if x.id == case_id), None)
        if case is None:
            self._reject("unknown_case", "justice case does not exist", case_id=case_id)
        if case.status == "adjudicated":
            self._reject("case_closed", "cannot add evidence after adjudication", case_id=case_id)
        evidence = self._evidence(evidence_id)
        if evidence.incident_id != case.incident_id or evidence.holder_agent_id != submitter_agent_id:
            self._reject("evidence_not_possessed", "submitter does not possess relevant evidence")
        record = self._admit(case, evidence, submitter_agent_id, day, hour)
        self.applied_event_keys.add(event_key)
        return record

    def adjudicate(self, *, case_id: str, reviewer_agent_id: str,
                   day: int, hour: int, event_key: str) -> Adjudication:
        if event_key in self.applied_event_keys:
            self._reject("duplicate_event", "adjudication already applied", event_key=event_key)
        case = next((x for x in self.cases if x.id == case_id), None)
        if case is None:
            self._reject("unknown_case", "justice case does not exist", case_id=case_id)
        if reviewer_agent_id not in self.investigator_agent_ids:
            self._reject("ineligible_reviewer", "agent cannot adjudicate")
        if case.adjudication_id is not None:
            self._reject("already_adjudicated", "case already adjudicated", case_id=case_id)
        admissions = [x for x in self.admitted_evidence if x.case_id == case.id]
        evidence_by_id = {x.id: x for x in self.crime.evidence}
        evidence = [evidence_by_id[x.evidence_id] for x in admissions]
        theft = [x for x in evidence if x.evidence_type == "unauthorized_transfer" and x.provenance_type == "system_record"]
        qualifying = [x for x in evidence if x.claims_actor and (x.evidence_type, x.provenance_type) in self.qualifying_actor_evidence]
        candidates = {x.actor_id for x in qualifying}
        responsible = next(iter(candidates)) if theft and len(candidates) == 1 else None
        result = "responsible" if responsible else "insufficient_evidence"
        record = Adjudication(
            id=f"adjudication-{self.next_adjudication_number:08d}", case_id=case.id,
            incident_id=case.incident_id, result=result, responsible_actor_id=responsible,
            evidence_ids=tuple(x.id for x in evidence), theft_evidence_ids=tuple(x.id for x in theft),
            actor_identifying_evidence_ids=tuple(x.id for x in qualifying),
            rule_version=self.rule_version, day=int(day), hour=int(hour), event_key=event_key,
        )
        self.next_adjudication_number += 1
        self.adjudications.append(record)
        self.cases[self.cases.index(case)] = replace(case, status="adjudicated", adjudication_id=record.id)
        self.applied_event_keys.add(event_key)
        return record

    def apply_consequence(self, *, adjudication_id: str, day: int, hour: int,
                          event_key: str) -> ConsequenceRecord:
        if event_key in self.applied_event_keys:
            self._reject("duplicate_event", "consequence already applied", event_key=event_key)
        adjudication = next((x for x in self.adjudications if x.id == adjudication_id), None)
        if adjudication is None:
            self._reject("unknown_adjudication", "adjudication does not exist")
        if adjudication.result != "responsible" or adjudication.responsible_actor_id is None:
            self._reject("no_responsible_actor", "insufficient evidence cannot produce consequences")
        if any(x.adjudication_id == adjudication.id for x in self.consequences):
            self._reject("consequence_exists", "consequence already exists")
        incident = self._incident(adjudication.incident_id)
        actor_id = adjudication.responsible_actor_id
        returned, transfer_id = 0, None
        if self.restitution_enabled:
            source = self.materials.inventory_for_agent(actor_id)
            available = source.quantity(incident.good_id)
            returned = min(available, incident.quantity)
            if returned:
                transfer = self.materials.transfer_good(
                    source.id, incident.source_inventory_id, incident.good_id, returned,
                    day=day, hour=hour, reason=f"Restitution for {adjudication.id}",
                    authorization_type="justice_restitution", authorization_id=adjudication.id,
                    event_key=f"justice-restitution:{adjudication.id}",
                )
                transfer_id = transfer.id
        status = "full" if returned == incident.quantity else ("partial" if returned else "unresolved")
        restitution = RestitutionRecord(
            id=f"restitution-{self.next_restitution_number:08d}", adjudication_id=adjudication.id,
            incident_id=incident.id, responsible_actor_id=actor_id, victim_id=incident.victim_id,
            good_id=incident.good_id, requested_quantity=incident.quantity,
            returned_quantity=returned, status=status, material_transfer_id=transfer_id,
            day=int(day), hour=int(hour), event_key=f"restitution-record:{event_key}",
        )
        self.next_restitution_number += 1
        self.restitutions.append(restitution)
        affected = []
        actor = self.agents[actor_id]
        if self.public_adjudications and self.reputation_system is not None:
            for observer_id in sorted(self.agents):
                if observer_id == actor_id:
                    continue
                update = self.reputation_system.record_observation(
                    day=day, observer=self.agents[observer_id], target_agent=actor.name,
                    dimension="trustworthiness", value=self.consequence_reputation_value,
                    evidence_id=f"justice:{adjudication.id}", public=True,
                )
                if update is not None:
                    affected.append(observer_id)
        consequence = ConsequenceRecord(
            id=f"consequence-{self.next_consequence_number:08d}", adjudication_id=adjudication.id,
            responsible_actor_id=actor_id, consequence_type="public_trust_penalty",
            reputation_value=self.consequence_reputation_value,
            affected_agent_ids=tuple(affected), restitution_id=restitution.id,
            day=int(day), hour=int(hour), event_key=event_key,
        )
        self.next_consequence_number += 1
        self.consequences.append(consequence)
        self.applied_event_keys.update({event_key, restitution.event_key})
        return consequence

    def knowledge_for_agent(self, agent_id: str) -> dict:
        private_cases = [x for x in self.cases if agent_id in {x.opened_by_agent_id, x.investigator_agent_id}]
        public_ids = {x.case_id for x in self.adjudications} if self.public_adjudications else set()
        known_cases = [x for x in self.cases if x in private_cases or x.id in public_ids]
        known_case_ids = {x.id for x in known_cases}
        return {
            "cases": known_cases,
            "adjudications": [x for x in self.adjudications if x.case_id in known_case_ids],
            "consequences": [x for x in self.consequences if any(a.id == x.adjudication_id and a.case_id in known_case_ids for a in self.adjudications)],
        }

    def diagnostics(self) -> dict:
        return {
            "case_count": len(self.cases), "adjudication_count": len(self.adjudications),
            "responsible_count": sum(x.result == "responsible" for x in self.adjudications),
            "insufficient_evidence_count": sum(x.result == "insufficient_evidence" for x in self.adjudications),
            "restitution_count": len(self.restitutions), "consequence_count": len(self.consequences),
            "rule_version": self.rule_version,
        }

    def to_dict(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "configuration": {
                "investigator_agent_ids": list(self.investigator_agent_ids),
                "rule_version": self.rule_version,
                "qualifying_actor_evidence": [list(x) for x in self.qualifying_actor_evidence],
                "consequence_reputation_value": self.consequence_reputation_value,
                "public_adjudications": self.public_adjudications,
                "restitution_enabled": self.restitution_enabled,
            },
            "cases": [x.to_dict() for x in self.cases],
            "admitted_evidence": [asdict(x) for x in self.admitted_evidence],
            "adjudications": [x.to_dict() for x in self.adjudications],
            "restitutions": [asdict(x) for x in self.restitutions],
            "consequences": [x.to_dict() for x in self.consequences],
            "applied_event_keys": sorted(self.applied_event_keys),
            "rejected_attempts": self.rejected_attempts,
            "next_case_number": self.next_case_number,
            "next_admission_number": self.next_admission_number,
            "next_adjudication_number": self.next_adjudication_number,
            "next_restitution_number": self.next_restitution_number,
            "next_consequence_number": self.next_consequence_number,
        }

    @classmethod
    def from_dict(cls, data: dict, *, crime, materials, agents, reputation_system=None):
        if data.get("schema_version", 1) != cls.SCHEMA_VERSION:
            raise ValueError("unsupported justice schema version")
        config = data["configuration"]
        return cls(
            crime=crime, materials=materials, agents=agents, reputation_system=reputation_system,
            investigator_agent_ids=tuple(config["investigator_agent_ids"]),
            rule_version=config["rule_version"],
            qualifying_actor_evidence=tuple(tuple(x) for x in config["qualifying_actor_evidence"]),
            consequence_reputation_value=config.get("consequence_reputation_value", -0.65),
            public_adjudications=config.get("public_adjudications", True),
            restitution_enabled=config.get("restitution_enabled", True),
            cases=[JusticeCase.from_dict(x) for x in data.get("cases", [])],
            admitted_evidence=[AdmittedEvidence(**x) for x in data.get("admitted_evidence", [])],
            adjudications=[Adjudication.from_dict(x) for x in data.get("adjudications", [])],
            restitutions=[RestitutionRecord(**x) for x in data.get("restitutions", [])],
            consequences=[ConsequenceRecord.from_dict(x) for x in data.get("consequences", [])],
            applied_event_keys=set(data.get("applied_event_keys", [])),
            rejected_attempts=data.get("rejected_attempts", []),
            **{key: data.get(key, 1) for key in (
                "next_case_number", "next_admission_number", "next_adjudication_number",
                "next_restitution_number", "next_consequence_number")},
        )

    @classmethod
    def from_config(cls, path: str | Path, *, crime, materials, agents, reputation_system=None):
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            crime=crime, materials=materials, agents=agents, reputation_system=reputation_system,
            investigator_agent_ids=tuple(config["investigator_agent_ids"]),
            rule_version=config["adjudication_rule_version"],
            qualifying_actor_evidence=tuple(
                (x["evidence_type"], x["provenance_type"])
                for x in config["qualifying_actor_evidence"]
            ),
            consequence_reputation_value=config.get("consequence_reputation_value", -0.65),
            public_adjudications=config.get("public_adjudications", True),
            restitution_enabled=config.get("restitution_enabled", True),
        )
