"""Authoritative, bounded social commitments and their lifecycle."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re

from src.systems.reputation import ReputationSystem
from src.systems.outcome_memory import KnowledgeRecipient


COMMITMENT_TYPES = {"help", "meet", "transfer"}
COMMITMENT_STATUSES = {
    "proposed", "accepted", "declined", "fulfilled", "cancelled", "failed", "expired",
}
ACTIVE_STATUSES = {"proposed", "accepted"}
LEGAL_TRANSITIONS = {
    "proposed": {"accepted", "declined", "cancelled", "expired"},
    "accepted": {"fulfilled", "cancelled", "failed", "expired"},
}

FEASIBILITY_STATES = {"feasible", "temporarily_infeasible", "impossible"}
REPAIR_WINDOW_DAYS = 2


@dataclass(frozen=True)
class CommitmentOpportunity:
    commitment_id: str
    agent_id: str
    counterpart_id: str
    commitment_type: str
    action_type: str
    target_location: str | None
    target_good_id: str | None
    quantity: int | None
    earliest_day: int
    earliest_tick: int | None
    due_day: int | None
    due_tick: int | None
    urgency: float
    feasibility: str
    infeasibility_reason: str
    provenance: str
    attempted_in_window: bool = False
    preparation_action_id: str | None = None
    preparation_location: str | None = None
    preparation_reason: str = ""

    def __post_init__(self) -> None:
        if self.feasibility not in FEASIBILITY_STATES:
            raise ValueError(f"invalid opportunity feasibility: {self.feasibility}")
        if not 0.0 <= self.urgency <= 1.0:
            raise ValueError("commitment urgency must be bounded from zero to one")


class CommitmentError(ValueError):
    """A deterministic rejection with no authoritative mutation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class SocialCommitment:
    id: str
    proposer_id: str
    counterpart_id: str
    commitment_type: str
    status: str
    created_day: int
    created_tick: int | None = None
    due_day: int | None = None
    due_tick: int | None = None
    source_session_id: str | None = None
    metadata: dict = field(default_factory=dict)
    resolution_day: int | None = None
    resolution_tick: int | None = None
    resolution_reason: str = ""
    evidence: list[dict] = field(default_factory=list)
    consequence_applied: bool = False
    repair_of_commitment_id: str | None = None

    def __post_init__(self) -> None:
        if self.commitment_type not in COMMITMENT_TYPES:
            raise ValueError(f"unsupported commitment type: {self.commitment_type}")
        if self.status not in COMMITMENT_STATUSES:
            raise ValueError(f"unsupported commitment status: {self.status}")
        if not self.id or self.proposer_id == self.counterpart_id:
            raise ValueError("commitment requires an id and two distinct agents")

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SocialCommitment":
        known = cls.__dataclass_fields__
        return cls(**{key: value for key, value in data.items() if key in known})


class CommitmentSystem:
    """Own commitment recognition, transitions, effects, and reconciliation."""

    GRACE_DAYS = 0
    FAR_DUE_DAYS = 4
    URGENCY_FAR = 0.10
    URGENCY_NEAR = 0.40
    URGENCY_TOMORROW = 0.70
    URGENCY_DUE = 1.00
    TERMINAL_EFFECTS = {
        "fulfilled": (1, 0.20),
        "failed": (-1, -0.20),
        "expired": (-1, -0.15),
        "cancelled": (0, -0.05),
        "declined": (0, 0.0),
    }

    def __init__(
        self, commitments: list[SocialCommitment] | None = None, *, next_number: int = 1,
        relationships=None, reputation_system: ReputationSystem | None = None,
        agents: list | None = None, materials=None, location_ids: list[str] | None = None,
        outcome_memory=None,
    ):
        self.commitments = list(commitments or [])
        self.next_number = max(1, int(next_number))
        self.relationships = relationships
        self.reputation_system = reputation_system
        self.agents = agents if agents is not None else []
        self.materials = materials
        self.location_ids = list(location_ids or [])
        self.outcome_memory = outcome_memory
        self.execution_records: list[dict] = []
        self.attempt_records: list[dict] = []
        self.duplicate_attempts = 0
        self.illegal_transition_attempts = 0
        self.processed_evidence_keys: set[str] = set()

    def to_dict(self) -> dict:
        return {
            "commitments": [item.to_dict() for item in self.commitments],
            "next_number": self.next_number,
            "processed_evidence_keys": sorted(self.processed_evidence_keys),
            "duplicate_attempts": self.duplicate_attempts,
            "illegal_transition_attempts": self.illegal_transition_attempts,
            "execution_records": list(self.execution_records),
            "attempt_records": list(self.attempt_records),
        }

    @classmethod
    def from_dict(cls, data: dict | None, **dependencies) -> "CommitmentSystem":
        data = data or {}
        system = cls(
            [SocialCommitment.from_dict(item) for item in data.get("commitments", [])],
            next_number=data.get("next_number", 1), **dependencies,
        )
        system.processed_evidence_keys = set(data.get("processed_evidence_keys", []))
        system.duplicate_attempts = int(data.get("duplicate_attempts", 0))
        system.illegal_transition_attempts = int(data.get("illegal_transition_attempts", 0))
        system.execution_records = list(data.get("execution_records", []))
        system.attempt_records = list(data.get("attempt_records", []))
        system.validate_invariants()
        return system

    def urgency(self, item: SocialCommitment, day: int, tick: int | None = None) -> float:
        del tick
        if item.due_day is None:
            return self.URGENCY_NEAR
        remaining = item.due_day - int(day)
        if remaining <= 0:
            return self.URGENCY_DUE
        if remaining == 1:
            return self.URGENCY_TOMORROW
        if remaining < self.FAR_DUE_DAYS:
            return self.URGENCY_NEAR
        return self.URGENCY_FAR

    def opportunities_for_agent(
        self, agent_id: str, *, day: int, tick: int | None = None,
    ) -> list[CommitmentOpportunity]:
        """Derive, never persist, executable candidates for the obligated agent."""
        agents = {agent.id: agent for agent in self.agents}
        actor = agents.get(agent_id)
        opportunities = []
        for item in self.commitments:
            if item.status != "accepted" or item.counterpart_id != agent_id:
                continue
            counterpart = agents.get(item.proposer_id)
            feasibility = "feasible"
            reason = ""
            location = item.metadata.get("location")
            good_id = item.metadata.get("good_id")
            quantity = item.metadata.get("quantity")
            preparation_action_id = None
            preparation_location = None
            preparation_reason = ""
            if actor is None or counterpart is None:
                feasibility, reason = "impossible", "missing_agent"
            elif day < item.created_day or (item.due_day is not None and day < item.created_day):
                feasibility, reason = "temporarily_infeasible", "before_eligible_day"
            elif item.commitment_type == "transfer":
                inventory_id = f"inventory:agent:{agent_id}"
                try:
                    available = self.materials.get_inventory(inventory_id).quantity(good_id)
                except (KeyError, ValueError, AttributeError):
                    feasibility, reason = "impossible", "invalid_inventory_or_good"
                else:
                    if available < int(quantity or 0):
                        feasibility, reason = "temporarily_infeasible", "resource_unavailable"
                        route = self._purchase_route(agent_id, good_id, int(quantity or 0))
                        if route:
                            preparation_action_id = "commitment_acquire_resource"
                            preparation_location = route["location_id"]
                            preparation_reason = "authorized_purchase_available"
                location = actor.location_id if actor else None
            elif item.commitment_type == "meet":
                if not location or location not in self.location_ids:
                    feasibility, reason = "impossible", "invalid_location"
                elif item.due_day is not None and day < item.due_day:
                    feasibility, reason = "temporarily_infeasible", "before_meeting_day"
                elif counterpart.location_id != location:
                    feasibility, reason = "temporarily_infeasible", "counterpart_unavailable"
            elif item.commitment_type == "help":
                if not str(item.metadata.get("task", "")).strip():
                    feasibility, reason = "impossible", "unrecognized_help_task"
                location = location or (counterpart.location_id if counterpart else None)
                if location not in self.location_ids:
                    feasibility, reason = "impossible", "invalid_location"
                elif item.due_day is not None and day < item.due_day:
                    feasibility, reason = "temporarily_infeasible", "before_help_day"
            opportunities.append(CommitmentOpportunity(
                commitment_id=item.id, agent_id=agent_id,
                counterpart_id=item.proposer_id, commitment_type=item.commitment_type,
                action_type=f"commitment_{item.commitment_type}", target_location=location,
                target_good_id=good_id, quantity=quantity,
                earliest_day=item.created_day, earliest_tick=item.created_tick,
                due_day=item.due_day, due_tick=item.due_tick,
                urgency=self.urgency(item, day, tick), feasibility=feasibility,
                infeasibility_reason=reason,
                provenance=f"commitment:{item.id}",
                attempted_in_window=any(
                    record.get("commitment_id") == item.id and record.get("day") == day
                    for record in self.attempt_records
                ),
                preparation_action_id=preparation_action_id,
                preparation_location=preparation_location,
                preparation_reason=preparation_reason,
            ))
        return opportunities

    def _purchase_route(self, agent_id: str, good_id: str | None, quantity: int) -> dict | None:
        """Return an existing legal seller route; never create stock or prices."""
        if not self.materials or not good_id or quantity <= 0:
            return None
        try:
            account = self.materials.economy.account_for_agent(agent_id)
            price = self.materials.price_for_good(good_id) * quantity
        except (KeyError, ValueError, AttributeError):
            return None
        for seller in sorted(self.materials.sellers.values(), key=lambda value: value.id):
            try:
                stock = self.materials.quantity(seller.inventory_id, good_id)
            except (KeyError, ValueError):
                continue
            if seller.active and stock >= quantity and account.balance >= price:
                return {"seller_id": seller.id, "location_id": seller.location_id,
                        "quantity": quantity, "good_id": good_id}
        return None

    def record_attempt(self, commitment_id: str, *, agent_id: str, day: int,
                       tick: int | None, kind: str, activity_id: str) -> dict:
        key = f"commitment-attempt:{commitment_id}:{kind}:{day}:{tick}"
        existing = next((item for item in self.attempt_records if item["event_key"] == key), None)
        if existing:
            self.duplicate_attempts += 1
            return existing
        record = {"event_key": key, "commitment_id": commitment_id,
                  "agent_id": agent_id, "day": day, "tick": tick,
                  "kind": kind, "activity_id": activity_id}
        self.attempt_records.append(record)
        return record

    def execute_preparation(self, *, commitment_id: str, agent_id: str, day: int,
                            tick: int | None, activity_record: dict) -> dict:
        item = self.get(commitment_id)
        if item.status != "accepted" or item.counterpart_id != agent_id:
            raise CommitmentError("not_executable", "commitment preparation is not active")
        route = self._purchase_route(agent_id, item.metadata.get("good_id"),
                                     int(item.metadata.get("quantity", 0)))
        if not route or activity_record.get("location") != route["location_id"]:
            raise CommitmentError("resource_unavailable", "no legal acquisition route is available")
        inventory = self.materials.inventory_for_agent(agent_id)
        account = self.materials.economy.account_for_agent(agent_id)
        exchange = self.materials.purchase(
            inventory.id, account.id, route["seller_id"], route["good_id"], route["quantity"],
            day=day, hour=tick, event_key=f"commitment:{commitment_id}:preparation",
        )
        attempt = self.record_attempt(commitment_id, agent_id=agent_id, day=day, tick=tick,
                                      kind="preparation", activity_id=activity_record["activity_id"])
        activity_record["execution_status"] = "prepared"
        activity_record["preparation_exchange_id"] = exchange.id
        attempt["exchange_id"] = exchange.id
        return attempt

    def execute_activity(
        self, *, commitment_id: str, agent_id: str, day: int,
        tick: int | None, activity_record: dict,
    ) -> dict:
        item = self.get(commitment_id)
        event_key = f"commitment-action:{commitment_id}"
        existing = next((record for record in self.execution_records
                         if record["event_key"] == event_key), None)
        if existing:
            self.duplicate_attempts += 1
            return existing
        if item.status != "accepted" or item.counterpart_id != agent_id:
            raise CommitmentError("not_executable", "commitment is not executable by this agent")
        self.record_attempt(commitment_id, agent_id=agent_id, day=day, tick=tick,
                            kind="execution", activity_id=activity_record["activity_id"])
        opportunity = next(
            (candidate for candidate in self.opportunities_for_agent(agent_id, day=day, tick=tick)
             if candidate.commitment_id == commitment_id), None,
        )
        if opportunity is None or opportunity.feasibility != "feasible":
            raise CommitmentError(
                "infeasible", opportunity.infeasibility_reason if opportunity else "no_opportunity",
            )
        evidence = {"activity_event_key": event_key,
                    "source_commitment_id": commitment_id}
        material_transfer_id = None
        if item.commitment_type == "transfer":
            transfer = self.fulfill_transfer(commitment_id, day=day, tick=tick)
            material_transfer_id = transfer.id
            evidence["material_transfer_id"] = material_transfer_id
        else:
            agents = {agent.id: agent for agent in self.agents}
            actor = agents[agent_id]
            counterpart = agents[item.proposer_id]
            if actor.location_id != opportunity.target_location or counterpart.location_id != opportunity.target_location:
                raise CommitmentError("counterpart_unavailable", "participants are not co-located")
            self.transition(
                item.id, "fulfilled", day=day, tick=tick,
                reason=f"authoritative_{item.commitment_type}_activity", evidence=evidence,
            )
        record = {
            "event_key": event_key, "commitment_id": item.id,
            "source_commitment_id": item.id, "agent_id": agent_id,
            "counterpart_id": item.proposer_id, "commitment_type": item.commitment_type,
            "day": day, "tick": tick, "activity_id": activity_record["activity_id"],
            "activity_event_key": event_key, "material_transfer_id": material_transfer_id,
            "status": "executed",
        }
        self.execution_records.append(record)
        activity_record["execution_status"] = "executed"
        return record

    def create(
        self, *, proposer_id: str, counterpart_id: str, commitment_type: str,
        day: int, tick: int | None = None, due_day: int | None = None,
        due_tick: int | None = None, source_session_id: str | None = None,
        metadata: dict | None = None, evidence: dict | None = None,
        status: str = "proposed", evidence_key: str | None = None,
        repair_of_commitment_id: str | None = None,
    ) -> SocialCommitment:
        if evidence_key and evidence_key in self.processed_evidence_keys:
            self.duplicate_attempts += 1
            existing = next((c for c in self.commitments if any(
                e.get("evidence_key") == evidence_key for e in c.evidence)), None)
            if existing:
                return existing
            raise CommitmentError("duplicate_evidence", "commitment evidence was already processed")
        commitment = SocialCommitment(
            id=f"commitment-{self.next_number:08d}", proposer_id=proposer_id,
            counterpart_id=counterpart_id, commitment_type=commitment_type,
            status=status, created_day=int(day), created_tick=tick, due_day=due_day,
            due_tick=due_tick, source_session_id=source_session_id,
            metadata=dict(metadata or {}), evidence=[],
            repair_of_commitment_id=repair_of_commitment_id,
        )
        proof = dict(evidence or {})
        if evidence_key:
            proof["evidence_key"] = evidence_key
            self.processed_evidence_keys.add(evidence_key)
        if proof:
            commitment.evidence.append(proof)
        self.commitments.append(commitment)
        self.next_number += 1
        return commitment

    def transition(
        self, commitment_id: str, status: str, *, day: int, tick: int | None = None,
        reason: str, evidence: dict | None = None,
    ) -> SocialCommitment:
        item = self.get(commitment_id)
        if status == item.status:
            self.duplicate_attempts += 1
            return item
        if status not in LEGAL_TRANSITIONS.get(item.status, set()):
            self.illegal_transition_attempts += 1
            raise CommitmentError(
                "illegal_transition", f"cannot transition {item.status} to {status}",
            )
        item.status = status
        if evidence:
            item.evidence.append(dict(evidence))
        if status not in ACTIVE_STATUSES:
            item.resolution_day = int(day)
            item.resolution_tick = tick
            item.resolution_reason = reason
            self._apply_consequence_once(item, day)
        self._project_transition(item, status, day, tick)
        return item

    def _project_transition(self, item, status, day, tick) -> None:
        if self.outcome_memory is None or status not in {
            "accepted", "fulfilled", "expired", "failed", "cancelled"
        }:
            return
        names = {agent.id: agent.name for agent in self.agents}
        actor = names.get(item.counterpart_id, "The responsible person")
        recipient = names.get(item.proposer_id, "the recipient")
        subject = item.metadata.get("good_id", item.metadata.get("task", item.commitment_type))
        if status == "accepted":
            text = f"{actor} agreed with {recipient} to {item.commitment_type} {subject}."
            sentiment = 1
        elif status == "fulfilled":
            text = f"{actor} fulfilled the promise to {recipient} concerning {subject}."
            sentiment = 2
        elif status in {"expired", "failed"}:
            text = f"{actor}'s promise to {recipient} concerning {subject} was not fulfilled."
            sentiment = -2
        else:
            text = f"{actor}'s promise to {recipient} concerning {subject} was cancelled."
            sentiment = -1
        self.outcome_memory.project(
            source_system="commitments", source_id=item.id,
            event_type=f"commitment_{status}", day=day, hour=tick,
            recipients=[
                KnowledgeRecipient(item.proposer_id, "participant", text,
                                   (item.counterpart_id,), sentiment),
                KnowledgeRecipient(item.counterpart_id, "participant", text,
                                   (item.proposer_id,), sentiment),
            ],
        )

    def get(self, commitment_id: str) -> SocialCommitment:
        matches = [item for item in self.commitments if item.id == commitment_id]
        if len(matches) != 1:
            raise CommitmentError("unknown_commitment", f"unknown commitment: {commitment_id}")
        return matches[0]

    def recognize_proposal(self, text: str, *, day: int, known_goods: dict[str, str] | None = None) -> dict | None:
        normalized = " ".join(text.lower().split())
        due_day = day + 1 if "tomorrow" in normalized else day if "today" in normalized else None
        bounded = bool(due_day is not None or re.search(r"\b(at|after|before) \w+", normalized))
        transfer_request = re.search(r"\b(?:can|could|would) you (?:give|bring|transfer|lend) me\b", normalized)
        transfer_offer = re.search(r"\bi (?:can|will|'ll) (?:bring|give|deliver|lend)(?: you)?\b", normalized)
        if transfer_request or transfer_offer:
            goods = known_goods or {}
            match = next(((good_id, name) for good_id, name in goods.items()
                          if any(alias in normalized for alias in {
                              good_id.replace("_", " "), name.lower(),
                              good_id.replace("_", " ").rstrip("s"), name.lower().rstrip("s"),
                          })), None)
            if not match or not bounded:
                return None
            quantity_match = re.search(r"\b(\d+|one|two|three)\b", normalized)
            quantity_values = {"one": 1, "two": 2, "three": 3}
            raw = quantity_match.group(1) if quantity_match else "1"
            quantity = quantity_values.get(raw, int(raw) if raw.isdigit() else 1)
            return {"commitment_type": "transfer", "due_day": due_day,
                    "metadata": {"good_id": match[0], "quantity": quantity},
                    "proposal_speaker_is_obligated": bool(transfer_offer)}
        meet = re.search(r"\b(?:can|could|shall|would) (?:we|you) meet\b|\blet(?:'s| us) meet\b", normalized)
        if meet and bounded:
            location = re.search(r"\b(?:at|in) (?:the )?([a-z_ ]+?)(?: tomorrow| today| at| after| before|[?.!,]|$)", normalized)
            return {"commitment_type": "meet", "due_day": due_day,
                    "metadata": {"location": location.group(1).strip() if location else ""}}
        help_request = re.search(r"\b(?:can|could|would) you help (?:me )?(?:to )?(.+)", normalized)
        if help_request and bounded:
            task = re.split(r"\b(?:tomorrow|today|after|before|at)\b", help_request.group(1))[0].strip(" ?.!,")
            if len(task) >= 3:
                return {"commitment_type": "help", "due_day": due_day,
                        "metadata": {"task": task[:120]}}
        return None

    def process_response(
        self, *, proposer_id: str, counterpart_id: str, proposal_text: str,
        response_text: str, outcome: str, day: int, tick: int | None,
        session_id: str, proposal_turn: int, response_turn: int,
        known_goods: dict[str, str] | None = None,
        repair_of_commitment_id: str | None = None,
    ) -> SocialCommitment | None:
        proposal = self.recognize_proposal(proposal_text, day=day, known_goods=known_goods)
        if proposal is None or outcome not in {"accepted", "declined"}:
            return None
        if proposal.get("proposal_speaker_is_obligated"):
            proposer_id, counterpart_id = counterpart_id, proposer_id
        if repair_of_commitment_id:
            parent = self.get(repair_of_commitment_id)
            if parent.status not in {"expired", "failed", "cancelled"}:
                raise CommitmentError("invalid_repair_parent", "repair parent must be terminal")
            if ({parent.proposer_id, parent.counterpart_id}
                    != {proposer_id, counterpart_id}):
                raise CommitmentError(
                    "invalid_repair_pair",
                    "repair parent must involve the same two participants",
                )
            if parent.commitment_type != proposal["commitment_type"]:
                raise CommitmentError(
                    "invalid_repair_type",
                    "repair successor must preserve the bounded commitment type",
                )
        evidence_key = f"{session_id}:{proposal_turn}:{response_turn}"
        item = self.create(
            proposer_id=proposer_id, counterpart_id=counterpart_id, day=day, tick=tick,
            due_day=proposal["due_day"], source_session_id=session_id,
            commitment_type=proposal["commitment_type"], metadata=proposal["metadata"],
            repair_of_commitment_id=repair_of_commitment_id,
            evidence={"proposal": proposal_text, "response": response_text,
                      "outcome": outcome, "proposal_turn": proposal_turn,
                      "response_turn": response_turn}, evidence_key=evidence_key,
        )
        if item.status == "proposed":
            self.transition(item.id, outcome, day=day, tick=tick,
                            reason=f"counterpart_{outcome}")
        return item

    def repair_opportunities(self, agent_id: str, counterpart_id: str, *, day: int) -> list[dict]:
        """Derive pair-private, short-lived accountability pressure."""
        result = []
        for item in self.commitments:
            if item.status not in {"expired", "failed", "cancelled"}:
                continue
            if item.counterpart_id != agent_id or item.proposer_id != counterpart_id:
                continue
            if item.resolution_day is None or not 0 <= day - item.resolution_day <= REPAIR_WINDOW_DAYS:
                continue
            successor = next((child for child in self.commitments
                              if child.repair_of_commitment_id == item.id), None)
            result.append({"commitment_id": item.id, "counterpart_id": counterpart_id,
                           "status": item.status, "age_days": day - item.resolution_day,
                           "pressure": max(0.35, 0.85 - 0.20 * (day - item.resolution_day)),
                           "successor_id": successor.id if successor else None})
        return result

    def cancel_from_dialogue(self, commitment_id: str, *, speaker_id: str,
                             counterpart_id: str, dialogue: str, day: int,
                             tick: int | None, session_id: str, turn_index: int) -> SocialCommitment | None:
        from src.simulation.social_semantics import classify_explicit_cancellation
        item = self.get(commitment_id)
        result = classify_explicit_cancellation(item.to_dict(), dialogue)
        if (item.status != "accepted" or item.counterpart_id != speaker_id
                or item.proposer_id != counterpart_id or not result["cancel"]):
            return None
        evidence_key = f"cancellation:{session_id}:{turn_index}:{commitment_id}"
        if evidence_key in self.processed_evidence_keys:
            self.duplicate_attempts += 1
            return item
        self.processed_evidence_keys.add(evidence_key)
        return self.transition(item.id, "cancelled", day=day, tick=tick,
                               reason="explicit_dialogue_cancellation",
                               evidence={"evidence_key": evidence_key, "session_id": session_id,
                                         "turn_index": turn_index, "dialogue": dialogue,
                                         "semantic_reason": result["reason"]})

    def expire_due(self, *, day: int, tick: int | None = None) -> list[SocialCommitment]:
        expired = []
        for item in self.commitments:
            if item.status == "accepted" and item.due_day is not None and day > item.due_day + self.GRACE_DAYS:
                expired.append(self.transition(item.id, "expired", day=day, tick=tick,
                                               reason="due_window_passed"))
        return expired

    def fulfill_transfer(self, commitment_id: str, *, day: int, tick: int | None = None):
        item = self.get(commitment_id)
        if item.status != "accepted" or item.commitment_type != "transfer":
            raise CommitmentError("not_fulfillable", "transfer commitment is not accepted")
        if self.materials is None:
            raise CommitmentError("materials_unavailable", "material system is unavailable")
        source = f"inventory:agent:{item.counterpart_id}"
        destination = f"inventory:agent:{item.proposer_id}"
        record = self.materials.transfer_good(
            source, destination, item.metadata["good_id"], int(item.metadata["quantity"]),
            day=day, hour=tick, reason="social_commitment", authorization_type="commitment",
            authorization_id=item.id, event_key=f"commitment:{item.id}:fulfillment",
        )
        self.transition(item.id, "fulfilled", day=day, tick=tick,
                        reason="authoritative_material_transfer",
                        evidence={"material_transfer_id": record.id})
        return record

    def relevant_context(self, agent_id: str, counterpart_id: str, current_day: int, limit: int = 3) -> list[str]:
        return [record["text"] for record in self.relevant_context_records(agent_id, counterpart_id, current_day, limit)]

    def relevant_context_records(self, agent_id: str, counterpart_id: str, current_day: int, limit: int = 3) -> list[dict]:
        relevant = [item for item in self.commitments if
                    {item.proposer_id, item.counterpart_id} == {agent_id, counterpart_id}
                    and (item.active or (item.resolution_day is not None and current_day - item.resolution_day <= 2))]
        relevant.sort(key=lambda item: (not item.active, -(item.due_day or 10**9), item.id))
        return [{"commitment_id": item.id, "status": item.status,
                 "text": self._format_context(item, agent_id)} for item in relevant[:limit]]

    def _format_context(self, item: SocialCommitment, agent_id: str) -> str:
        names = {agent.id: agent.name for agent in self.agents}
        if not names:
            subject = item.metadata.get("task") or item.metadata.get("good_id", "").replace("_", " ") or "meet"
            due = f" on day {item.due_day}" if item.due_day is not None else ""
            if item.status == "accepted":
                return f"you agreed to {item.commitment_type} {subject}{due}."
        proposer = "you" if item.proposer_id == agent_id else names.get(item.proposer_id, "the other person")
        actor = "You" if item.counterpart_id == agent_id else names.get(item.counterpart_id, "The other person")
        due = f" on day {item.due_day}" if item.due_day is not None else ""
        if item.commitment_type == "meet":
            location = item.metadata.get("location") or "the agreed place"
            active = f"{actor} agreed to meet {proposer} at {location}{due}."
            fulfilled = f"{actor} met {proposer} at {location} as agreed{due}."
        elif item.commitment_type == "transfer":
            quantity = int(item.metadata.get("quantity", 1))
            good = item.metadata.get("good_id", "item").replace("_", " ")
            active = f"{actor} agreed to give {proposer} {quantity} {good} by day {item.due_day}."
            fulfilled = f"{actor} delivered {quantity} {good} to {proposer} as agreed{due}."
        else:
            task = item.metadata.get("task") or "with the agreed task"
            active = f"{actor} agreed to help {proposer} {task}{due}."
            fulfilled = f"{actor} helped {proposer} {task} as agreed{due}."
        if item.status == "accepted":
            return active
        if item.status == "fulfilled":
            return fulfilled
        if item.status in {"expired", "failed"}:
            if item.commitment_type == "transfer":
                good = item.metadata.get("good_id", "item").replace("_", " ")
                return f"{actor} promised {proposer} {int(item.metadata.get('quantity', 1))} {good} by day {item.due_day}, but the promise expired unfulfilled."
            return active[:-1] + ", but that commitment expired without fulfillment."
        if item.status == "declined":
            return f"{actor} declined the proposed {item.commitment_type} commitment{due}."
        return active[:-1] + f", but it was {item.status}."

    def _apply_consequence_once(self, item: SocialCommitment, day: int) -> None:
        if item.consequence_applied:
            return
        relationship_delta, reputation_value = self.TERMINAL_EFFECTS.get(item.status, (0, 0.0))
        agents = {agent.id: agent for agent in self.agents}
        proposer = agents.get(item.proposer_id)
        counterpart = agents.get(item.counterpart_id)
        if relationship_delta and self.relationships and proposer and counterpart:
            self.relationships.change_score(proposer.name, counterpart.name, relationship_delta)
        if reputation_value and self.reputation_system and proposer and counterpart:
            self.reputation_system.record_observation(
                day=day, observer=proposer, target_agent=counterpart.name,
                dimension="trustworthiness", value=reputation_value,
                evidence_id=f"commitment:{item.id}:{item.status}", public=False,
            )
        item.consequence_applied = True

    def validate_invariants(self) -> dict[str, bool]:
        ids = [item.id for item in self.commitments]
        material_transfers = list(getattr(self.materials, "inventory_transfers", []))
        checks = {
            "unique_ids": len(ids) == len(set(ids)),
            "valid_types": all(item.commitment_type in COMMITMENT_TYPES for item in self.commitments),
            "valid_statuses": all(item.status in COMMITMENT_STATUSES for item in self.commitments),
            "terminal_not_active": all(not item.active for item in self.commitments
                                       if item.status in COMMITMENT_STATUSES - ACTIVE_STATUSES),
            "resolved_once": all((item.resolution_day is None) == item.active for item in self.commitments),
            "resolved_effect_once": all(item.consequence_applied for item in self.commitments if not item.active),
            "transfer_has_proof": all(
                item.status != "fulfilled" or item.commitment_type != "transfer" or
                any(e.get("material_transfer_id") for e in item.evidence)
                for item in self.commitments
            ),
            "fulfillment_has_execution_proof": all(
                item.status != "fulfilled" or any(
                    evidence.get("material_transfer_id") or evidence.get("activity_event_key")
                    for evidence in item.evidence
                ) for item in self.commitments
            ),
            "execution_references_commitment": all(
                record.get("commitment_id") in set(ids)
                and record.get("source_commitment_id") == record.get("commitment_id")
                for record in self.execution_records
            ),
            "execution_unique": len({record["event_key"] for record in self.execution_records})
            == len(self.execution_records),
            "transfer_execution_exact": all(
                item.status != "fulfilled" or item.commitment_type != "transfer" or
                len([
                    record for record in material_transfers
                    if record.authorization_type == "commitment"
                    and record.authorization_id == item.id
                    and any(evidence.get("material_transfer_id") == record.id
                            for evidence in item.evidence)
                ]) == 1
                for item in self.commitments
            ),
            "cancelled_has_evidence": all(
                item.status != "cancelled" or any(
                    evidence.get("session_id") and evidence.get("turn_index") is not None
                    for evidence in item.evidence
                ) for item in self.commitments
            ),
            "repair_parent_exists": all(
                not item.repair_of_commitment_id or item.repair_of_commitment_id in set(ids)
                for item in self.commitments
            ),
            "repair_not_self": all(item.repair_of_commitment_id != item.id for item in self.commitments),
            "repair_parent_terminal": all(
                not item.repair_of_commitment_id or self.get(item.repair_of_commitment_id).status
                in {"expired", "failed", "cancelled"} for item in self.commitments
            ),
            "repair_pair_preserved": all(
                not item.repair_of_commitment_id or
                {item.proposer_id, item.counterpart_id} == {
                    self.get(item.repair_of_commitment_id).proposer_id,
                    self.get(item.repair_of_commitment_id).counterpart_id,
                }
                for item in self.commitments
            ),
            "repair_type_preserved": all(
                not item.repair_of_commitment_id or
                item.commitment_type == self.get(item.repair_of_commitment_id).commitment_type
                for item in self.commitments
            ),
            "repair_acyclic": all(self._lineage_acyclic(item) for item in self.commitments),
            "attempts_unique": len({record["event_key"] for record in self.attempt_records})
            == len(self.attempt_records),
            "priority_bounded": all(
                0.0 <= value <= 1.0 for value in (
                    self.URGENCY_FAR, self.URGENCY_NEAR,
                    self.URGENCY_TOMORROW, self.URGENCY_DUE,
                )
            ),
        }
        if not all(checks.values()):
            raise ValueError(f"commitment invariants failed: {checks}")
        return checks

    def _lineage_acyclic(self, item: SocialCommitment) -> bool:
        seen = {item.id}
        parent_id = item.repair_of_commitment_id
        while parent_id:
            if parent_id in seen:
                return False
            seen.add(parent_id)
            parent = next((candidate for candidate in self.commitments
                           if candidate.id == parent_id), None)
            if parent is None:
                return False
            parent_id = parent.repair_of_commitment_id
        return True
