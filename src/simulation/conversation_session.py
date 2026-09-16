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
        "not interested", "leave me alone",
    )
    ACCEPTED = (
        "yes", "yeah", "sure", "please do", "i'd appreciate", "i would appreciate",
        "that would help", "sounds good", "let's do", "let us do", "count me in",
        "happy to", "gladly", "thank you", "thanks",
    )

    def resolve(self, previous_action: str, reply: str) -> str:
        if previous_action not in self.RESPONSIVE_ACTIONS:
            return "unresolved"
        text = " ".join(reply.lower().split())
        if any(marker in text for marker in self.DECLINED):
            return "declined"
        if previous_action == "ask_for_help" and self._looks_like_answer(text):
            return "answered"
        if any(marker in text for marker in self.ACCEPTED):
            return "accepted"
        if previous_action == "cooperate" and re.search(r"\b(i|we) (can|will|'ll)\b", text):
            return "accepted"
        return "unresolved"

    @staticmethod
    def _looks_like_answer(text: str) -> bool:
        return bool(
            re.search(r"\b(try|use|ask|go|look|start|check|know|suggest|recommend|because|the answer|you should)\b", text)
            and not text.rstrip().endswith("?")
        )
