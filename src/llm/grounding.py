"""Deterministic, bounded checks for high-risk factual dialogue claims.

This is deliberately a candidate detector, not a general truth checker.  It
only rejects a few auditable claim shapes whose support should be present in
the exact speaker context used for generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re


GROUNDING_PREFIXES = {
    "memory", "relationship_event", "public_event", "reputation_claim",
    "journal", "town_arc",
}


@dataclass(frozen=True)
class GroundingResult:
    valid: bool
    reason: str = ""
    candidate_type: str = ""
    invalid_refs: list[str] = field(default_factory=list)
    valid_refs: list[str] = field(default_factory=list)


def build_grounding_sources(context: dict) -> dict[str, str]:
    """Assign stable, prompt-local references to supplied factual material."""
    sources: dict[str, str] = {}

    def add(prefix: str, values) -> None:
        for index, value in enumerate(values or [], start=1):
            text = " ".join(str(value).split())
            if text:
                sources[f"{prefix}:{index}"] = text

    add("relationship_event", context.get("relationship_history", []))
    add("memory", context.get("social_memories", []))
    add("memory", context.get("relevant_memories", []))
    add("reputation_claim", context.get("reputation_context", []))
    add("journal", context.get("recent_journals", []))
    event = context.get("daily_event")
    if event:
        sources[f"public_event:{event.get('id', 'today')}"] = (
            f"{event.get('name', '')}: {event.get('description', '')}"
        )
    for arc in context.get("town_arcs", []):
        sources[f"town_arc:{arc.get('id', len(sources) + 1)}"] = (
            f"{arc.get('name', '')}: {arc.get('description', '')}"
        )
    rumor = context.get("reputation_rumor_text")
    if rumor:
        evidence_id = (context.get("reputation_rumor") or {}).get("evidence_id", "shareable")
        sources[f"reputation_claim:{evidence_id}"] = rumor
    return sources


class GroundingValidator:
    """Flag unsupported references, shared history, and named local entities."""

    SHARED_HISTORY = re.compile(
        r"\b(?:remember when|last time we|when we (?:last |used to )?|"
        r"we (?:played|visited|worked|met|went|used to))\b",
        re.IGNORECASE,
    )
    LOCAL_ENTITY = re.compile(
        r"\b(?:the |a |our )?(?:new )?([A-Z][A-Za-z'-]*(?: [A-Z][A-Za-z'-]*){0,2}) "
        r"(shop|store|stall|vendor|market|cafe|garden|library|factory|clinic|school)\b"
    )
    DESCRIBED_LOCAL_ENTITY = re.compile(
        r"\b((?:new|old|community|riverside|downtown|local) "
        r"(?:shop|store|stall|vendor|market|cafe|bakery|bookstore|garden|museum|"
        r"factory|clinic|school|mill))\b",
        re.IGNORECASE,
    )
    HONORIFIC_PERSON = re.compile(r"\b(?:Mr|Mrs|Ms|Dr)\.\s*[A-Z][A-Za-z'-]+\b")
    UNCERTAIN = re.compile(
        r"\b(?:maybe|perhaps|might|could be|i wonder|i'm not sure|i am not sure|"
        r"do you know|have you seen|is there|are there)\b",
        re.IGNORECASE,
    )

    def validate(self, dialogue: str, refs: list[str], context: dict) -> GroundingResult:
        sources = context.get("grounding_sources") or build_grounding_sources(context)
        refs = [str(ref) for ref in (refs or [])]
        invalid = [
            ref for ref in refs
            if ref not in sources or ref.split(":", 1)[0] not in GROUNDING_PREFIXES
        ]
        valid = [ref for ref in refs if ref in sources]
        if invalid:
            return GroundingResult(False, "invalid_grounding_ref", "invalid_reference", invalid, valid)

        text = " ".join(dialogue.split())
        if re.search(
            rf"\b(?:{'|'.join(sorted(GROUNDING_PREFIXES))}):[A-Za-z0-9_.:-]+",
            text,
            re.IGNORECASE,
        ):
            return GroundingResult(
                False, "grounding_metadata_in_dialogue", "metadata_leak",
                valid_refs=valid,
            )
        ordinary_question = bool(re.match(
            r"^(?:what|where|why|how|who|is|are|do|does|did|can|could|would|have|has)\b",
            text,
            re.IGNORECASE,
        ))
        if not text or self.UNCERTAIN.search(text) or ordinary_question:
            return GroundingResult(True, valid_refs=valid)

        supplied = " ".join(sources.values()).lower()
        if self.SHARED_HISTORY.search(text) and not self._supported(text, supplied, valid, sources):
            return GroundingResult(
                False, "unsupported_shared_history_candidate",
                "shared_history", valid_refs=valid,
            )

        match = self.LOCAL_ENTITY.search(text)
        if match:
            entity = match.group(1).lower()
            known = {
                str(context.get("location", "")).replace("_", " ").lower(),
                "town", "town square", "market", "cafe", "library",
            }
            if entity not in {"the", "a", "our", "new"} and entity not in known and entity not in supplied:
                return GroundingResult(
                    False, "unsupported_named_world_entity_candidate",
                    "named_world_entity", valid_refs=valid,
                )
        described = self.DESCRIBED_LOCAL_ENTITY.search(text)
        if described and described.group(1).lower() not in supplied:
            return GroundingResult(
                False, "unsupported_named_world_entity_candidate",
                "named_world_entity", valid_refs=valid,
            )
        named_person = self.HONORIFIC_PERSON.search(text)
        if named_person and named_person.group(0).lower() not in supplied:
            return GroundingResult(
                False, "unsupported_named_person_candidate",
                "named_world_entity", valid_refs=valid,
            )
        return GroundingResult(True, valid_refs=valid)

    @staticmethod
    def _supported(text: str, supplied: str, refs: list[str], sources: dict[str, str]) -> bool:
        if refs:
            supplied = " ".join(sources[ref] for ref in refs).lower()
        ignored = {"remember", "when", "last", "time", "used", "with", "that", "this", "together"}
        tokens = {
            token for token in re.findall(r"[a-z][a-z'-]{3,}", text.lower())
            if token not in ignored
        }
        return bool(tokens & set(re.findall(r"[a-z][a-z'-]{3,}", supplied)))
