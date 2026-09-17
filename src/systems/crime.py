"""Deterministic theft incidents, witness opportunity, and evidence provenance."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from src.systems.materials import MaterialError, MaterialSystem


class CrimeError(ValueError):
    """A rejected crime/evidence operation with no crime-state mutation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TheftActivityRule:
    activity_id: str
    eligible_actor_ids: tuple[str, ...]
    source_inventory_id: str
    good_id: str
    quantity: int
    location_id: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["eligible_actor_ids"] = list(self.eligible_actor_ids)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "TheftActivityRule":
        values = dict(data)
        values["eligible_actor_ids"] = tuple(values.get("eligible_actor_ids", ()))
        return cls(**values)


@dataclass(frozen=True)
class WitnessOpportunity:
    id: str
    incident_id: str
    witness_id: str
    day: int
    hour: int
    location_id: str
    present: bool
    observed: bool
    observation_rule: str = "stable_hash_one_in_three"


@dataclass(frozen=True)
class CrimeEvidence:
    id: str
    incident_id: str
    evidence_type: str
    provenance_type: str
    holder_agent_id: str | None
    actor_id: str
    victim_id: str
    day: int
    hour: int
    location_id: str
    claims_actor: bool
    source_evidence_id: str | None = None
    originating_observer_id: str | None = None
    source_agent_id: str | None = None
    transmission_chain: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["transmission_chain"] = list(self.transmission_chain)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "CrimeEvidence":
        values = dict(data)
        values["transmission_chain"] = tuple(values.get("transmission_chain", ()))
        return cls(**values)


@dataclass(frozen=True)
class CrimeIncident:
    id: str
    crime_type: str
    actor_id: str
    victim_id: str
    source_inventory_id: str
    destination_inventory_id: str
    good_id: str
    quantity: int
    unit_value: int
    total_value: int
    day: int
    hour: int
    location_id: str
    actor_location_id: str
    source_location_id: str
    unauthorized_transfer_id: str
    source_quantity_before: int
    destination_quantity_before: int
    potential_witness_ids: tuple[str, ...]
    eyewitness_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    discovery_status: str
    discovered_by: tuple[str, ...]
    status: str
    event_key: str

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in (
            "potential_witness_ids",
            "eyewitness_ids",
            "evidence_ids",
            "discovered_by",
        ):
            data[key] = list(data[key])
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "CrimeIncident":
        values = dict(data)
        for key in (
            "potential_witness_ids",
            "eyewitness_ids",
            "evidence_ids",
            "discovered_by",
        ):
            values[key] = tuple(values.get(key, ()))
        return cls(**values)


class CrimeSystem:
    """Create theft state only through validated unauthorized material transfers."""

    SCHEMA_VERSION = 1
    EVIDENCE_TYPES = {
        "unauthorized_transfer",
        "actor_knowledge",
        "eyewitness",
        "ownership_loss",
        "hearsay",
    }
    PROVENANCE_TYPES = {
        "system_record",
        "direct_participation",
        "direct_observation",
        "direct_discovery",
        "hearsay",
    }

    def __init__(
        self,
        *,
        materials: MaterialSystem,
        agents: list,
        reputation_system=None,
        theft_activity_rules: list[TheftActivityRule] | None = None,
        incidents: list[CrimeIncident] | None = None,
        witness_opportunities: list[WitnessOpportunity] | None = None,
        evidence: list[CrimeEvidence] | None = None,
        applied_event_keys: set[str] | None = None,
        rejected_attempts: list[dict] | None = None,
        next_incident_number: int = 1,
        next_opportunity_number: int = 1,
        next_evidence_number: int = 1,
    ):
        self.materials = materials
        self.agents = {agent.id: agent for agent in agents}
        self.reputation_system = reputation_system
        rules = theft_activity_rules or []
        if len({rule.activity_id for rule in rules}) != len(rules):
            raise ValueError("theft activity ids must be unique")
        self.theft_activity_rules = {rule.activity_id: rule for rule in rules}
        self.incidents = list(incidents or [])
        self.witness_opportunities = list(witness_opportunities or [])
        self.evidence = list(evidence or [])
        self.applied_event_keys = set(applied_event_keys or ())
        self.rejected_attempts = list(rejected_attempts or [])
        self.next_incident_number = int(next_incident_number)
        self.next_opportunity_number = int(next_opportunity_number)
        self.next_evidence_number = int(next_evidence_number)
        self._validate_model()
        self._validate_history()

    def _validate_model(self) -> None:
        for rule in self.theft_activity_rules.values():
            if not rule.eligible_actor_ids:
                raise ValueError("theft activity requires eligible actors")
            if any(actor_id not in self.agents for actor_id in rule.eligible_actor_ids):
                raise ValueError("theft activity references unknown actor")
            self.materials.get_inventory(rule.source_inventory_id)
            self.materials.get_good(rule.good_id)
            if isinstance(rule.quantity, bool) or not isinstance(rule.quantity, int) or rule.quantity <= 0:
                raise ValueError("theft activity quantity must be a positive integer")

    @staticmethod
    def witness_observes(event_key: str, witness_id: str) -> bool:
        digest = hashlib.sha256(f"{event_key}|{witness_id}".encode("utf-8")).digest()
        return digest[0] % 3 == 0

    def _validate_history(self) -> None:
        groups = (
            (self.incidents, "incident"),
            (self.witness_opportunities, "witness opportunity"),
            (self.evidence, "crime evidence"),
        )
        for records, label in groups:
            ids = [record.id for record in records]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label} ids must be unique")
        if not set(incident.event_key for incident in self.incidents).issubset(
            self.applied_event_keys
        ):
            raise ValueError("crime incidents are missing idempotency guards")
        if not self.incidents_reconcile_with_materials():
            raise ValueError("crime incidents do not reconcile with material transfers")
        if not self.evidence_is_valid():
            raise ValueError("crime evidence history is invalid")

    def _attempt(self, operation: str, **values) -> dict:
        return {"operation": operation, **values}

    def _reject(self, code: str, message: str, attempt: dict) -> None:
        self.rejected_attempts.append({"code": code, **attempt})
        raise CrimeError(code, message)

    def _next_evidence(
        self,
        *,
        incident_id: str,
        evidence_type: str,
        provenance_type: str,
        holder_agent_id: str | None,
        actor_id: str,
        victim_id: str,
        day: int,
        hour: int,
        location_id: str,
        claims_actor: bool,
        source_evidence_id: str | None = None,
        originating_observer_id: str | None = None,
        source_agent_id: str | None = None,
        transmission_chain: tuple[str, ...] = (),
    ) -> CrimeEvidence:
        record = CrimeEvidence(
            id=f"crime-evidence-{self.next_evidence_number:08d}",
            incident_id=incident_id,
            evidence_type=evidence_type,
            provenance_type=provenance_type,
            holder_agent_id=holder_agent_id,
            actor_id=actor_id,
            victim_id=victim_id,
            day=day,
            hour=hour,
            location_id=location_id,
            claims_actor=claims_actor,
            source_evidence_id=source_evidence_id,
            originating_observer_id=originating_observer_id,
            source_agent_id=source_agent_id,
            transmission_chain=transmission_chain,
        )
        self.next_evidence_number += 1
        return record

    def _source_location(self, source_inventory, agents: dict[str, object]) -> str:
        if source_inventory.owner_type == "agent":
            owner = agents.get(source_inventory.owner_id)
            if owner is None:
                raise CrimeError("unknown_victim", "source owner is not an active agent")
            return owner.location_id
        if source_inventory.owner_type == "business":
            seller = self.materials.sellers.get(source_inventory.owner_id)
            if seller is None:
                raise CrimeError("unknown_source_location", "business location is unknown")
            return seller.location_id
        raise CrimeError("unknown_source_location", "source location is unknown")

    def attempt_theft(
        self,
        *,
        actor_id: str,
        source_inventory_id: str,
        good_id: str,
        quantity: int,
        day: int,
        hour: int,
        location_id: str,
        event_key: str,
        agents: list | None = None,
    ) -> CrimeIncident:
        active_agents = {
            agent.id: agent for agent in (agents if agents is not None else self.agents.values())
        }
        attempt = self._attempt(
            "theft",
            actor_id=actor_id,
            source_inventory_id=source_inventory_id,
            good_id=good_id,
            quantity=quantity,
            day=day,
            hour=hour,
            location_id=location_id,
            event_key=event_key,
        )
        if event_key in self.applied_event_keys:
            self._reject("duplicate_event", "crime event was already applied", attempt)
        actor = active_agents.get(actor_id)
        if actor is None:
            self._reject("unknown_actor", "actor does not exist", attempt)
        try:
            source = self.materials.get_inventory(source_inventory_id)
            destination = self.materials.inventory_for_agent(actor_id)
            good = self.materials.get_good(good_id)
        except MaterialError as error:
            self._reject(error.code, str(error), attempt)
        if source.owner_id == actor_id:
            self._reject("self_theft", "actor already owns the source inventory", attempt)
        if destination.owner_id != actor_id or destination.owner_type != "agent":
            self._reject("destination_not_controlled", "actor does not control destination", attempt)
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            self._reject("invalid_quantity", "quantity must be a positive integer", attempt)
        if source.quantity(good_id) < quantity:
            self._reject("insufficient_stock", "source has insufficient stock", attempt)
        if actor.location_id != location_id:
            self._reject("actor_not_present", "actor is not at incident location", attempt)
        try:
            source_location = self._source_location(source, active_agents)
        except CrimeError as error:
            self._reject(error.code, str(error), attempt)
        if source_location != location_id:
            self._reject("source_not_present", "source property is not at incident location", attempt)
        if event_key in {exchange.event_key for exchange in self.materials.exchanges}:
            self._reject("authorized_exchange", "event already has a legitimate exchange", attempt)

        incident_id = f"crime-{self.next_incident_number:08d}"
        source_before = source.quantity(good_id)
        destination_before = destination.quantity(good_id)
        currency_before = self.materials.economy.total_currency()
        ledger_before = len(self.materials.economy.ledger)
        exchanges_before = len(self.materials.exchanges)
        try:
            transfer = self.materials.transfer_good(
                source.id,
                destination.id,
                good_id,
                quantity,
                day=day,
                hour=hour,
                reason=f"Unauthorized taking recorded by {incident_id}",
                authorization_type="unauthorized_theft",
                authorization_id=incident_id,
                event_key=f"crime-transfer:{event_key}",
            )
        except MaterialError as error:
            self._reject(error.code, str(error), attempt)
        if (
            self.materials.economy.total_currency() != currency_before
            or len(self.materials.economy.ledger) != ledger_before
            or len(self.materials.exchanges) != exchanges_before
        ):
            raise RuntimeError("unauthorized transfer mutated monetary/exchange state")

        potential_ids = tuple(sorted(
            agent.id for agent in active_agents.values()
            if agent.id != actor_id and agent.location_id == location_id
        ))
        observed_ids = tuple(
            witness_id for witness_id in potential_ids
            if self.witness_observes(event_key, witness_id)
        )
        opportunities = []
        for witness_id in potential_ids:
            opportunities.append(WitnessOpportunity(
                id=f"witness-opportunity-{self.next_opportunity_number:08d}",
                incident_id=incident_id,
                witness_id=witness_id,
                day=day,
                hour=hour,
                location_id=location_id,
                present=True,
                observed=witness_id in observed_ids,
            ))
            self.next_opportunity_number += 1

        new_evidence = [
            self._next_evidence(
                incident_id=incident_id,
                evidence_type="unauthorized_transfer",
                provenance_type="system_record",
                holder_agent_id=None,
                actor_id=actor_id,
                victim_id=source.owner_id,
                day=day,
                hour=hour,
                location_id=location_id,
                claims_actor=True,
            ),
            self._next_evidence(
                incident_id=incident_id,
                evidence_type="actor_knowledge",
                provenance_type="direct_participation",
                holder_agent_id=actor_id,
                actor_id=actor_id,
                victim_id=source.owner_id,
                day=day,
                hour=hour,
                location_id=location_id,
                claims_actor=True,
                originating_observer_id=actor_id,
                transmission_chain=(actor_id,),
            ),
        ]
        for witness_id in observed_ids:
            new_evidence.append(self._next_evidence(
                incident_id=incident_id,
                evidence_type="eyewitness",
                provenance_type="direct_observation",
                holder_agent_id=witness_id,
                actor_id=actor_id,
                victim_id=source.owner_id,
                day=day,
                hour=hour,
                location_id=location_id,
                claims_actor=True,
                originating_observer_id=witness_id,
                transmission_chain=(witness_id,),
            ))
        evidence_ids = tuple(record.id for record in new_evidence)
        victim_observed = source.owner_id in observed_ids
        incident = CrimeIncident(
            id=incident_id,
            crime_type="theft",
            actor_id=actor_id,
            victim_id=source.owner_id,
            source_inventory_id=source.id,
            destination_inventory_id=destination.id,
            good_id=good_id,
            quantity=quantity,
            unit_value=good.unit_price,
            total_value=good.unit_price * quantity,
            day=day,
            hour=hour,
            location_id=location_id,
            actor_location_id=actor.location_id,
            source_location_id=source_location,
            unauthorized_transfer_id=transfer.id,
            source_quantity_before=source_before,
            destination_quantity_before=destination_before,
            potential_witness_ids=potential_ids,
            eyewitness_ids=observed_ids,
            evidence_ids=evidence_ids,
            discovery_status="victim_observed" if victim_observed else "undiscovered",
            discovered_by=(source.owner_id,) if victim_observed else (),
            status="open",
            event_key=event_key,
        )
        self.incidents.append(incident)
        self.witness_opportunities.extend(opportunities)
        self.evidence.extend(new_evidence)
        self.applied_event_keys.add(event_key)
        self.next_incident_number += 1
        self._apply_direct_reputation(incident, new_evidence)
        return incident

    def _apply_direct_reputation(
        self,
        incident: CrimeIncident,
        evidence: list[CrimeEvidence],
    ) -> None:
        if self.reputation_system is None:
            return
        actor = self.agents.get(incident.actor_id)
        if actor is None:
            return
        for record in evidence:
            if record.evidence_type != "eyewitness" or record.holder_agent_id not in self.agents:
                continue
            observer = self.agents[record.holder_agent_id]
            self.reputation_system.record_observation(
                day=incident.day,
                observer=observer,
                target_agent=actor.name,
                dimension="trustworthiness",
                value=-1.0,
                evidence_id=f"crime:{record.id}",
            )

    def discover_loss(
        self,
        *,
        incident_id: str,
        victim_id: str,
        day: int,
        hour: int,
        event_key: str,
    ) -> CrimeEvidence:
        attempt = self._attempt(
            "discover_loss",
            incident_id=incident_id,
            victim_id=victim_id,
            event_key=event_key,
        )
        if event_key in self.applied_event_keys:
            self._reject("duplicate_event", "discovery was already applied", attempt)
        incident = next((item for item in self.incidents if item.id == incident_id), None)
        if incident is None:
            self._reject("unknown_incident", "incident does not exist", attempt)
        if victim_id != incident.victim_id or victim_id not in self.agents:
            self._reject("not_victim", "agent is not the incident victim", attempt)
        if victim_id in incident.discovered_by:
            self._reject("already_discovered", "victim already knows of the loss", attempt)
        evidence = self._next_evidence(
            incident_id=incident.id,
            evidence_type="ownership_loss",
            provenance_type="direct_discovery",
            holder_agent_id=victim_id,
            actor_id=incident.actor_id,
            victim_id=victim_id,
            day=day,
            hour=hour,
            location_id=incident.location_id,
            claims_actor=False,
            originating_observer_id=victim_id,
            transmission_chain=(victim_id,),
        )
        self.evidence.append(evidence)
        self.incidents[self.incidents.index(incident)] = replace(
            incident,
            evidence_ids=(*incident.evidence_ids, evidence.id),
            discovery_status="victim_discovered_loss",
            discovered_by=(*incident.discovered_by, victim_id),
        )
        self.applied_event_keys.add(event_key)
        return evidence

    def share_evidence(
        self,
        *,
        speaker_id: str,
        listener_id: str,
        evidence_id: str,
        day: int,
        hour: int,
        event_key: str,
    ) -> CrimeEvidence:
        attempt = self._attempt(
            "share_evidence",
            speaker_id=speaker_id,
            listener_id=listener_id,
            evidence_id=evidence_id,
            event_key=event_key,
        )
        if event_key in self.applied_event_keys:
            self._reject("duplicate_event", "evidence transmission already applied", attempt)
        if speaker_id not in self.agents or listener_id not in self.agents:
            self._reject("unknown_agent", "speaker or listener does not exist", attempt)
        source = next((item for item in self.evidence if item.id == evidence_id), None)
        if source is None or source.holder_agent_id != speaker_id:
            self._reject("evidence_not_known", "speaker does not know this evidence", attempt)
        if listener_id == speaker_id or listener_id in source.transmission_chain:
            self._reject("invalid_listener", "evidence cannot loop to this listener", attempt)
        if len(source.transmission_chain) >= 3:
            self._reject("provenance_depth", "hearsay chain is at its limit", attempt)
        evidence = self._next_evidence(
            incident_id=source.incident_id,
            evidence_type="hearsay",
            provenance_type="hearsay",
            holder_agent_id=listener_id,
            actor_id=source.actor_id,
            victim_id=source.victim_id,
            day=day,
            hour=hour,
            location_id=source.location_id,
            claims_actor=source.claims_actor,
            source_evidence_id=source.id,
            originating_observer_id=source.originating_observer_id,
            source_agent_id=speaker_id,
            transmission_chain=(*source.transmission_chain, listener_id),
        )
        self.evidence.append(evidence)
        incident = next(item for item in self.incidents if item.id == source.incident_id)
        self.incidents[self.incidents.index(incident)] = replace(
            incident, evidence_ids=(*incident.evidence_ids, evidence.id)
        )
        self.applied_event_keys.add(event_key)
        self._apply_hearsay_reputation(source, speaker_id, listener_id, day)
        return evidence

    def _apply_hearsay_reputation(
        self,
        source: CrimeEvidence,
        speaker_id: str,
        listener_id: str,
        day: int,
    ) -> None:
        if self.reputation_system is None or not source.claims_actor:
            return
        speaker = self.agents[speaker_id]
        listener = self.agents[listener_id]
        actor = self.agents.get(source.actor_id)
        if actor is None:
            return
        belief = speaker.get_reputation_belief(actor.name, "trustworthiness")
        if belief is None:
            return
        reputation_evidence_id = f"crime:{source.id}"
        owned = next(
            (item for item in belief.evidence if item.evidence_id == reputation_evidence_id),
            None,
        )
        if owned is None and source.source_evidence_id:
            origin_id = source.source_evidence_id
            owned = next(
                (item for item in belief.evidence if item.evidence_id == f"crime:{origin_id}"),
                None,
            )
        if owned is None:
            return
        claim = {
            "subject_agent": actor.name,
            "dimension": "trustworthiness",
            "evidence_id": owned.evidence_id,
        }
        self.reputation_system.transmit_rumor(
            day=day,
            speaker=speaker,
            listener=listener,
            claim=claim,
        )

    def knowledge_for_agent(self, agent_id: str) -> list[CrimeEvidence]:
        return [record for record in self.evidence if record.holder_agent_id == agent_id]

    def process_activity(self, agent, activity, *, agents: list, day: int, hour: int):
        rule = self.theft_activity_rules.get(activity.id)
        if rule is None or "unauthorized_take" not in activity.tags:
            return None
        if agent.id not in rule.eligible_actor_ids or activity.location_id != rule.location_id:
            return None
        try:
            return self.attempt_theft(
                actor_id=agent.id,
                source_inventory_id=rule.source_inventory_id,
                good_id=rule.good_id,
                quantity=rule.quantity,
                day=day,
                hour=hour,
                location_id=rule.location_id,
                event_key=f"theft:{agent.id}:{activity.id}:{day}",
                agents=agents,
            )
        except CrimeError:
            return None

    def incidents_reconcile_with_materials(self) -> bool:
        transfers = {record.id: record for record in self.materials.inventory_transfers}
        exchanges = {exchange.inventory_transfer_id for exchange in self.materials.exchanges}
        unauthorized = [
            record for record in self.materials.inventory_transfers
            if record.authorization_type == "unauthorized_theft"
        ]
        if {record.authorization_id for record in unauthorized} != {
            incident.id for incident in self.incidents
        }:
            return False
        for incident in self.incidents:
            transfer = transfers.get(incident.unauthorized_transfer_id)
            source = self.materials.inventories.get(incident.source_inventory_id)
            destination = self.materials.inventories.get(incident.destination_inventory_id)
            good = self.materials.goods.get(incident.good_id)
            if transfer is None or source is None or destination is None or good is None:
                return False
            if not (
                incident.crime_type == "theft"
                and transfer.authorization_type == "unauthorized_theft"
                and transfer.authorization_id == incident.id
                and transfer.id not in exchanges
                and transfer.source_inventory_id == incident.source_inventory_id
                and transfer.destination_inventory_id == incident.destination_inventory_id
                and transfer.good_id == incident.good_id
                and transfer.quantity == incident.quantity
                and transfer.day == incident.day
                and transfer.hour == incident.hour
                and source.owner_id == incident.victim_id
                and destination.owner_type == "agent"
                and destination.owner_id == incident.actor_id
                and incident.unit_value == good.unit_price
                and incident.total_value == good.unit_price * incident.quantity
                and incident.actor_location_id == incident.location_id
                and incident.source_location_id == incident.location_id
                and incident.source_quantity_before >= incident.quantity
            ):
                return False
        return self.materials.material_conservation_holds()

    def evidence_is_valid(self) -> bool:
        incidents = {incident.id: incident for incident in self.incidents}
        opportunities = {
            (record.incident_id, record.witness_id): record
            for record in self.witness_opportunities
        }
        evidence_by_id = {record.id: record for record in self.evidence}
        semantic_evidence_keys = [
            (
                record.incident_id,
                record.evidence_type,
                record.holder_agent_id,
                record.source_evidence_id,
            )
            for record in self.evidence
        ]
        if len(semantic_evidence_keys) != len(set(semantic_evidence_keys)):
            return False
        opportunity_ids = [record.id for record in self.witness_opportunities]
        if len(opportunity_ids) != len(set(opportunity_ids)):
            return False
        for incident in self.incidents:
            incident_opportunities = [
                record for record in self.witness_opportunities
                if record.incident_id == incident.id
            ]
            if (
                tuple(sorted(record.witness_id for record in incident_opportunities))
                != incident.potential_witness_ids
                or tuple(sorted(
                    record.witness_id for record in incident_opportunities
                    if record.observed
                )) != incident.eyewitness_ids
                or any(
                    record.observed
                    != self.witness_observes(incident.event_key, record.witness_id)
                    for record in incident_opportunities
                )
                or set(incident.evidence_ids)
                != {
                    record.id for record in self.evidence
                    if record.incident_id == incident.id
                }
            ):
                return False
        for record in self.evidence:
            incident = incidents.get(record.incident_id)
            if (
                incident is None
                or record.evidence_type not in self.EVIDENCE_TYPES
                or record.provenance_type not in self.PROVENANCE_TYPES
                or record.actor_id != incident.actor_id
                or record.victim_id != incident.victim_id
            ):
                return False
            if record.evidence_type == "eyewitness":
                opportunity = opportunities.get((incident.id, record.holder_agent_id))
                if (
                    record.provenance_type != "direct_observation"
                    or record.holder_agent_id == incident.actor_id
                    or opportunity is None
                    or not opportunity.present
                    or not opportunity.observed
                    or opportunity.location_id != incident.location_id
                    or opportunity.day != incident.day
                    or opportunity.hour != incident.hour
                    or record.location_id != opportunity.location_id
                    or record.day != opportunity.day
                    or record.hour != opportunity.hour
                    or record.originating_observer_id != record.holder_agent_id
                    or record.transmission_chain != (record.holder_agent_id,)
                ):
                    return False
            if record.evidence_type == "actor_knowledge" and not (
                record.provenance_type == "direct_participation"
                and record.holder_agent_id == incident.actor_id
                and record.originating_observer_id == incident.actor_id
            ):
                return False
            if record.evidence_type == "unauthorized_transfer" and not (
                record.provenance_type == "system_record"
                and record.holder_agent_id is None
                and record.day == incident.day
                and record.hour == incident.hour
                and record.location_id == incident.location_id
            ):
                return False
            if record.evidence_type == "ownership_loss" and not (
                record.provenance_type == "direct_discovery"
                and record.holder_agent_id == incident.victim_id
                and not record.claims_actor
            ):
                return False
            if record.evidence_type == "hearsay":
                source = evidence_by_id.get(record.source_evidence_id)
                if (
                    record.provenance_type != "hearsay"
                    or source is None
                    or source.incident_id != record.incident_id
                    or record.source_agent_id != source.holder_agent_id
                    or record.originating_observer_id != source.originating_observer_id
                    or record.transmission_chain
                    != (*source.transmission_chain, record.holder_agent_id)
                ):
                    return False
        return all(
            evidence_id in evidence_by_id
            for incident in self.incidents
            for evidence_id in incident.evidence_ids
        )

    def diagnostics(self) -> dict:
        direct = [item for item in self.evidence if item.evidence_type == "eyewitness"]
        hearsay = [item for item in self.evidence if item.evidence_type == "hearsay"]
        return {
            "incident_count": len(self.incidents),
            "unauthorized_transfer_count": sum(
                record.authorization_type == "unauthorized_theft"
                for record in self.materials.inventory_transfers
            ),
            "total_stolen_value": sum(incident.total_value for incident in self.incidents),
            "potential_witness_count": len(self.witness_opportunities),
            "actual_witness_count": sum(
                record.observed for record in self.witness_opportunities
            ),
            "direct_evidence_count": len(direct),
            "hearsay_evidence_count": len(hearsay),
            "evidence_count": len(self.evidence),
            "rejected_attempt_count": len(self.rejected_attempts),
            "rejections_by_code": dict(sorted(Counter(
                record["code"] for record in self.rejected_attempts
            ).items())),
            "idempotency_rejections": sum(
                record["code"] == "duplicate_event" for record in self.rejected_attempts
            ),
            "incidents_reconcile_with_materials": self.incidents_reconcile_with_materials(),
            "evidence_valid": self.evidence_is_valid(),
            "material_conserved": self.materials.material_conservation_holds(),
            "currency_conserved": self.materials.economy.conservation_holds(),
        }

    def to_dict(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "theft_activity_rules": [
                rule.to_dict() for rule in self.theft_activity_rules.values()
            ],
            "incidents": [incident.to_dict() for incident in self.incidents],
            "witness_opportunities": [
                asdict(record) for record in self.witness_opportunities
            ],
            "evidence": [record.to_dict() for record in self.evidence],
            "applied_event_keys": sorted(self.applied_event_keys),
            "rejected_attempts": self.rejected_attempts,
            "next_incident_number": self.next_incident_number,
            "next_opportunity_number": self.next_opportunity_number,
            "next_evidence_number": self.next_evidence_number,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        *,
        materials: MaterialSystem,
        agents: list,
        reputation_system=None,
    ) -> "CrimeSystem":
        if data.get("schema_version", 1) != cls.SCHEMA_VERSION:
            raise ValueError("unsupported crime schema version")
        return cls(
            materials=materials,
            agents=agents,
            reputation_system=reputation_system,
            theft_activity_rules=[
                TheftActivityRule.from_dict(item)
                for item in data.get("theft_activity_rules", [])
            ],
            incidents=[
                CrimeIncident.from_dict(item) for item in data.get("incidents", [])
            ],
            witness_opportunities=[
                WitnessOpportunity(**item)
                for item in data.get("witness_opportunities", [])
            ],
            evidence=[CrimeEvidence.from_dict(item) for item in data.get("evidence", [])],
            applied_event_keys=set(data.get("applied_event_keys", [])),
            rejected_attempts=data.get("rejected_attempts", []),
            next_incident_number=data.get("next_incident_number", 1),
            next_opportunity_number=data.get("next_opportunity_number", 1),
            next_evidence_number=data.get("next_evidence_number", 1),
        )

    @classmethod
    def from_config(
        cls,
        path: str | Path,
        *,
        materials: MaterialSystem,
        agents: list,
        reputation_system=None,
    ) -> "CrimeSystem":
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        agent_ids = {agent.id for agent in agents}
        rules = []
        for item in config.get("theft_activity_rules", []):
            eligible = tuple(
                actor_id for actor_id in item.get("eligible_actor_ids", [])
                if actor_id in agent_ids
            )
            if not eligible or item.get("source_inventory_id") not in materials.inventories:
                continue
            rules.append(TheftActivityRule.from_dict({**item, "eligible_actor_ids": eligible}))
        return cls(
            materials=materials,
            agents=agents,
            reputation_system=reputation_system,
            theft_activity_rules=rules,
        )
