"""Bounded conversation-session records and deterministic response outcomes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re


@dataclass
class ConversationTurn:
    turn_index: int
    speaker: str
    listener: str
    dialogue: str
    suggested_action: str
    parsed_action: str
    inferred_action: str
    inference_reason: str
    final_action: str
    final_action_reason: str
    action_source: str
    dialogue_source: str
    generation_attempt_count: int = 1
    regenerated_for_repetition: bool = False
    regenerated_for_grounding: bool = False
    grounding_valid: bool = True
    grounding_reason: str = ""
    grounding_candidate_type: str = ""
    grounding_refs: list[str] = field(default_factory=list)
    invalid_grounding_refs: list[str] = field(default_factory=list)
    effect_applied: bool = False
    effect_suppressed: bool = False
    effect_suppression_reason: str = ""
    generation_error: str = ""
    response_to_turn: int | None = None
    response_outcome: str | None = None
    context_evidence: dict = field(default_factory=dict)
    context_snapshot: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ConversationSession:
    session_id: str
    day: int
    hour: int
    location: str
    participants: list[str]
    initiating_agent: str
    turns: list[ConversationTurn] = field(default_factory=list)
    termination_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ResponseOutcomeResolver:
    """Conservatively resolve a reply to the preceding social action."""

    RESPONSIVE_ACTIONS = {"offer_help", "ask_for_help", "cooperate"}
    DECLINED = (
        "no thanks", "no thank you", "i've got it", "i have got it",
        "i can handle it", "rather not", "don't need", "do not need",
        "can't help", "cannot help", "won't help", "not able to help",
        "not interested", "leave me alone", "sorry, i can't", "sorry, i cannot",
        "no, i'm busy", "no, i am busy", "i don't want to", "i do not want to",
    )
    OFFER_ACCEPTED = (
        "yes", "yeah", "sure", "please do", "i'd appreciate", "i would appreciate",
        "that would help", "thanks for offering", "thank you for offering",
        "i appreciate your help", "i appreciate the help",
    )
    COOPERATION_ACCEPTED = (
        "yes", "yeah", "sure", "sounds good", "good idea", "let's do", "let us do",
        "count me in", "i'll join", "i will join", "we can do that",
    )

    def resolve(self, previous_action: str, reply: str) -> str:
        if previous_action not in self.RESPONSIVE_ACTIONS:
            return "unresolved"
        text = " ".join(reply.lower().split())
        if self._contains_any(text, self.DECLINED):
            return "declined"
        if previous_action == "ask_for_help" and self._looks_like_answer(text):
            return "accepted"
        if previous_action == "offer_help" and self._contains_any(
            text, self.OFFER_ACCEPTED
        ):
            return "accepted"
        if previous_action == "cooperate" and (
            self._contains_any(text, self.COOPERATION_ACCEPTED)
            or re.search(
                r"\b(i|we) (can|will|'ll) (help|join|work|handle|organize|sort|repair|do)\b",
                text,
            )
            or re.search(
                r"\blet(?:'s| us) (grab|start|split|divide|sort|organize|repair|"
                r"handle|clean|check|work)\b",
                text,
            )
        ):
            return "accepted"
        return "unresolved"

    @staticmethod
    def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
        return any(
            re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", text)
            for marker in markers
        )

    @staticmethod
    def _looks_like_answer(text: str) -> bool:
        has_answer_language = bool(
            re.search(r"\b(try|use|ask|go|look|start|check|know|suggest|recommend|because|the answer|you should|sure thing)\b", text)
            or re.search(r"\bi(?:'ll| will| can)\b.{0,35}\b(help|handle|grab|take|carry|sort|check|do)\b", text)
            or re.search(r"\blet(?:'s| us) do it\b", text)
        )
        return has_answer_language and not text.rstrip().endswith("?")
