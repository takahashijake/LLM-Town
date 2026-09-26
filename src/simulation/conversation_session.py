"""Bounded conversation-session records and deterministic response outcomes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from src.simulation.social_semantics import resolve_response


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
    regenerated_for_commitment_state: bool = False
    commitment_state_valid: bool = True
    commitment_state_reason: str = "no_supplied_commitment_claim"
    related_commitment_id: str = ""
    grounding_valid: bool = True
    grounding_reason: str = ""
    grounding_candidate_type: str = ""
    grounding_refs: list[str] = field(default_factory=list)
    invalid_grounding_refs: list[str] = field(default_factory=list)
    grounding_metadata_advisory: dict = field(default_factory=dict)
    grounding_metadata_disagreements: list[str] = field(default_factory=list)
    grounded_repair_used: bool = False
    grounded_fallback_used: bool = False
    effect_applied: bool = False
    effect_suppressed: bool = False
    effect_suppression_reason: str = ""
    generation_error: str = ""
    response_to_turn: int | None = None
    response_outcome: str | None = None
    social_response: dict = field(default_factory=dict)
    commitment_relation: dict = field(default_factory=dict)
    follow_through: dict = field(default_factory=dict)
    response_resolution_reason: str = ""
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
    snapshot_id: str = ""
    schedule_index: int = 0
    request_seed: int = 0
    simulation_seed: int = 0
    commit_position: int | None = None
    turns: list[ConversationTurn] = field(default_factory=list)
    termination_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ResponseOutcomeResolver:
    """Conservatively resolve a reply to the preceding social action."""

    RESPONSIVE_ACTIONS = {"offer_help", "ask_for_help", "cooperate"}
    def resolve(
        self, previous_action: str, reply: str, *, proposal: dict | None = None,
        parsed_action: str = "", social_response: dict | None = None,
    ) -> str:
        if previous_action not in self.RESPONSIVE_ACTIONS:
            return "unresolved"
        return resolve_response(
            previous_action, reply, proposal=proposal, parsed_action=parsed_action,
            social_response=social_response,
        )[0]

    def resolve_with_reason(self, previous_action: str, reply: str, **signals) -> tuple[str, str]:
        if previous_action not in self.RESPONSIVE_ACTIONS:
            return "unresolved", "preceding_action_requires_no_response_resolution"
        return resolve_response(previous_action, reply, **signals)
