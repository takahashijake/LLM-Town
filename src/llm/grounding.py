"""Speaker-scoped grounding packets and deterministic response validation.

Grounding metadata is evidence about what a model was shown, never authority to
change the simulation. Packet references are local to one prompt and contain
no authoritative record IDs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re

MAX_GROUNDING_FACTS = 3
MAX_GROUNDING_FACT_CHARS = 240
GROUNDING_PREFIXES = {"memory", "relationship_event", "public_event", "reputation_claim", "journal", "town_arc", "g"}
POLARITY_BY_EVENT = {
    "commitment_accepted": "accepted", "commitment_fulfilled": "fulfilled",
    "commitment_failed": "failed", "commitment_expired": "failed",
    "commitment_cancelled": "cancelled", "commitment_canceled": "cancelled",
    "plan_failed": "failed_private", "restitution_received": "completed",
    "plan_completed": "completed_private",
    "restitution_completed": "completed", "adjudicated_responsible": "adjudicated",
    "theft_committed": "witnessed",
    "loss_discovered": "unknown_culprit",
}
ALLOWED_FOLLOW_THROUGH = {"none", "acknowledge", "appreciate", "request_explanation", "apologize", "propose_repair", "decline_similar", "cooperate"}


@dataclass(frozen=True)
class GroundingFact:
    ref: str
    fact: str
    source_type: str
    knowledge_basis: str
    counterpart: str = ""
    event_day: int = 0
    age_days: int = 0
    outcome_polarity: str = "neutral"
    owner_id: str = ""
    counterpart_ids: tuple[str, ...] = ()

    def prompt_dict(self) -> dict:
        return {key: value for key, value in asdict(self).items() if key not in {"owner_id", "counterpart_ids"}}


@dataclass(frozen=True)
class GroundingResult:
    valid: bool
    reason: str = ""
    candidate_type: str = ""
    invalid_refs: list[str] = field(default_factory=list)
    valid_refs: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    follow_through: dict = field(default_factory=dict)


def _clean(value: object, limit: int = MAX_GROUNDING_FACT_CHARS) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def build_grounding_packet(memories, *, speaker, listener, current_day: int, limit: int = MAX_GROUNDING_FACTS) -> list[GroundingFact]:
    """Project only selected, provenance-backed private memories for a prompt."""
    packet = []
    for memory in memories:
        if len(packet) >= max(0, min(MAX_GROUNDING_FACTS, int(limit))):
            break
        if not memory.causal or not memory.has_authoritative_provenance or memory.owner_id != speaker.id:
            continue
        packet.append(GroundingFact(
            ref=f"g{len(packet) + 1}", fact=_clean(memory.description),
            source_type=memory.event_type or memory.type,
            knowledge_basis=memory.knowledge_basis or "",
            counterpart=listener.name if listener.id in memory.counterpart_ids else "",
            event_day=int(memory.day), age_days=max(0, int(current_day) - int(memory.day)),
            outcome_polarity=POLARITY_BY_EVENT.get(memory.event_type or memory.type, "neutral"),
            owner_id=memory.owner_id or "", counterpart_ids=tuple(memory.counterpart_ids),
        ))
    return packet


def grounding_packet_for_prompt(packet) -> list[dict]:
    return [item.prompt_dict() if isinstance(item, GroundingFact) else {
        key: value for key, value in dict(item).items() if key not in {"owner_id", "counterpart_ids"}
    } for item in list(packet)[:MAX_GROUNDING_FACTS]]


def build_grounding_sources(context: dict) -> dict[str, str]:
    """Compatibility map plus canonical packet references."""
    sources = {str(item["ref"]): str(item["fact"]) for item in context.get("grounding_packet", []) if isinstance(item, dict) and item.get("ref") and item.get("fact")}
    def add(prefix, values):
        for index, value in enumerate(values or [], 1):
            text = _clean(value)
            if text:
                sources.setdefault(f"{prefix}:{index}", text)
    add("relationship_event", context.get("relationship_history", []))
    add("memory", context.get("social_memories", []))
    add("memory", context.get("relevant_memories", []))
    add("reputation_claim", context.get("reputation_context", []))
    add("journal", context.get("recent_journals", []))
    event = context.get("daily_event")
    if event:
        sources[f"public_event:{event.get('id', 'today')}"] = _clean(f"{event.get('name', '')}: {event.get('description', '')}")
    for arc in context.get("town_arcs", []):
        sources[f"town_arc:{arc.get('id', len(sources) + 1)}"] = _clean(f"{arc.get('name', '')}: {arc.get('description', '')}")
    return sources


class GroundingValidator:
    """Validate prompt-local references and narrow causal semantics."""
    SHARED_HISTORY = re.compile(r"\b(?:remember when|last time we|when we (?:last |used to )?|we (?:played|visited|worked|met|went|used to))\b", re.I)
    UNCERTAIN = re.compile(r"\b(?:maybe|perhaps|might|could be|i wonder|i'm not sure|i am not sure|do you know|have you seen|is there|are there)\b", re.I)
    FULFILLED = re.compile(r"\b(?:fulfilled|kept (?:the |your )?promise|came through|completed)\b", re.I)
    FAILED = re.compile(r"\b(?:failed|missed|broke (?:the |your )?promise|didn't|did not)\b", re.I)
    ACCEPTED_COMMITMENT = re.compile(r"\b(?:accepted|agreed to) (?:the |your )?(?:commitment|promise)\b", re.I)
    CULPRIT = re.compile(r"\b(?:you|he|she|[A-Z][a-z]+) (?:stole|took|robbed)\b")
    PRIVATE_REASON = re.compile(r"\b(?:because (?:you|he|she) (?:planned|decided|chose)|private plan|plan failed because)\b", re.I)
    AUTHORITATIVE_ASSERTION = re.compile(r"\b(?:the (?:money|coins|materials|goods) (?:has|have) (?:been )?transferred|restitution (?:is|was) complete|you (?:are|were) convicted|the promise (?:is|was) fulfilled)\b", re.I)
    LOCAL_ENTITY = re.compile(r"\b(?:the |a |our )?(?:new )?([A-Z][A-Za-z'-]*(?: [A-Z][A-Za-z'-]*){0,2}) (shop|store|stall|vendor|market|cafe|garden|library|factory|clinic|school)\b")
    DESCRIBED_LOCAL_ENTITY = re.compile(r"\b((?:new|old|community|riverside|downtown|local) (?:shop|store|stall|vendor|market|cafe|bakery|bookstore|garden|museum|factory|clinic|school|mill))\b", re.I)
    HONORIFIC_PERSON = re.compile(r"\b(?:Mr|Mrs|Ms|Dr)\.\s*[A-Z][A-Za-z'-]+\b")

    def validate(self, dialogue: str, refs: list[str], context: dict, *, follow_through: dict | None = None) -> GroundingResult:
        sources = context.get("grounding_sources") or build_grounding_sources(context)
        refs = list(dict.fromkeys(str(ref) for ref in (refs or [])))
        invalid = [ref for ref in refs if ref not in sources]
        valid = [ref for ref in refs if ref in sources]
        packet = {str(row.get("ref")): row for row in context.get("grounding_packet", []) if isinstance(row, dict)}
        if invalid:
            return GroundingResult(False, "invalid_grounding_ref", "invalid_reference", invalid, valid, ["reference_not_in_current_context"])
        text = " ".join(str(dialogue).split())
        if re.search(r"\b(?:g\d+|memory:\d+|commitment-\d{8})\b", text, re.I):
            return GroundingResult(False, "grounding_metadata_in_dialogue", "metadata_leak", valid_refs=valid, diagnostics=["opaque_reference_spoken"])
        referenced = [packet[ref] for ref in valid if ref in packet]
        polarities = {row.get("outcome_polarity", "neutral") for row in referenced}
        claims_fulfilled = bool(self.FULFILLED.search(text)) and not bool(
            re.search(r"\b(?:not|wasn't|isn't|never) (?:fulfilled|completed)\b", text, re.I)
        )
        if claims_fulfilled and polarities & {"failed", "failed_private", "accepted"}:
            return GroundingResult(False, "outcome_polarity_reversed", "polarity", valid_refs=valid)
        if self.FAILED.search(text) and "fulfilled" in polarities:
            return GroundingResult(False, "outcome_polarity_reversed", "polarity", valid_refs=valid)
        if self.ACCEPTED_COMMITMENT.search(text) and any(
            row.get("source_type", "").startswith("plan_") for row in referenced
        ):
            return GroundingResult(False, "private_plan_treated_as_commitment", "polarity", valid_refs=valid)
        if self.CULPRIT.search(text) and "unknown_culprit" in polarities:
            return GroundingResult(False, "unknown_culprit_asserted", "private_information", valid_refs=valid)
        if self.PRIVATE_REASON.search(text) and not any(row.get("knowledge_basis") == "self_action" for row in referenced):
            return GroundingResult(False, "private_plan_reason_exposed", "private_information", valid_refs=valid)
        if self.AUTHORITATIVE_ASSERTION.search(text) and not polarities & {"fulfilled", "completed"}:
            return GroundingResult(False, "unsupported_authoritative_assertion", "authority_boundary", valid_refs=valid)
        sanitized, errors = self._validate_follow_through(follow_through, packet, valid)
        if errors:
            return GroundingResult(False, errors[0], "follow_through", valid_refs=valid, diagnostics=errors)
        ordinary_question = bool(re.match(r"^(?:what|where|why|how|who|is|are|do|does|did|can|could|would|have|has)\b", text, re.I))
        if text and not self.UNCERTAIN.search(text) and not ordinary_question and self.SHARED_HISTORY.search(text) and not self._supported(text, " ".join(sources.values()).lower(), valid, sources):
            return GroundingResult(False, "unsupported_shared_history_candidate", "shared_history", valid_refs=valid)
        supplied = " ".join(sources.values()).lower()
        named = self.LOCAL_ENTITY.search(text)
        if named and named.group(1).lower() not in {"the", "a", "our", "new", str(context.get("location", "")).replace("_", " ").lower()} and named.group(1).lower() not in supplied:
            return GroundingResult(False, "unsupported_named_world_entity_candidate", "named_world_entity", valid_refs=valid)
        described = self.DESCRIBED_LOCAL_ENTITY.search(text)
        if described and described.group(1).lower() not in supplied:
            return GroundingResult(False, "unsupported_named_world_entity_candidate", "named_world_entity", valid_refs=valid)
        person = self.HONORIFIC_PERSON.search(text)
        if person and person.group(0).lower() not in supplied:
            return GroundingResult(False, "unsupported_named_person_candidate", "named_world_entity", valid_refs=valid)
        return GroundingResult(True, valid_refs=valid, follow_through=sanitized)

    @staticmethod
    def _validate_follow_through(value, packet, valid_refs):
        if not value:
            return {}, []
        if not isinstance(value, dict):
            return {}, ["malformed_follow_through"]
        if value.get("_malformed"):
            return {}, ["malformed_follow_through"]
        kind, source_ref, target = (str(value.get(key, "")).strip().lower() if key == "kind" else str(value.get(key, "")).strip() for key in ("kind", "source_ref", "target"))
        if kind not in ALLOWED_FOLLOW_THROUGH:
            return {}, ["unsupported_follow_through_kind"]
        if kind == "none":
            return {}, []
        if source_ref not in valid_refs or source_ref not in packet:
            return {}, ["follow_through_source_not_valid"]
        fact = packet[source_ref]
        counterpart = str(fact.get("counterpart", "")).strip()
        if target and counterpart and target != counterpart:
            return {}, ["follow_through_counterpart_mismatch"]
        if kind in {"propose_repair", "decline_similar", "cooperate"} and (
            not target or not counterpart or target != counterpart
        ):
            return {}, ["follow_through_counterpart_required"]
        allowed = {
            "fulfilled": {"acknowledge", "appreciate", "cooperate"},
            "failed": {"acknowledge", "request_explanation", "apologize", "propose_repair", "decline_similar"},
            "completed": {"acknowledge", "appreciate"}, "witnessed": {"acknowledge", "request_explanation"},
            "unknown_culprit": {"acknowledge"},
            "cancelled": {"acknowledge", "request_explanation"},
            "adjudicated": {"acknowledge"},
        }.get(fact.get("outcome_polarity"), {"acknowledge"})
        if kind not in allowed:
            return {}, ["follow_through_incompatible_with_outcome"]
        return {"kind": kind, "target": target, "source_ref": source_ref}, []

    @staticmethod
    def _supported(text, supplied, refs, sources):
        if refs:
            supplied = " ".join(sources[ref] for ref in refs).lower()
        ignored = {"remember", "when", "last", "time", "used", "with", "that", "this", "together"}
        tokens = {token for token in re.findall(r"[a-z][a-z'-]{3,}", text.lower()) if token not in ignored}
        return bool(tokens & set(re.findall(r"[a-z][a-z'-]{3,}", supplied)))
