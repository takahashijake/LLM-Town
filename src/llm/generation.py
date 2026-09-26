"""Immutable identities for conversation generation calls."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Mapping


@dataclass(frozen=True)
class ConversationGenerationRequest:
    request_id: str
    session_id: str
    schedule_index: int
    turn_index: int
    generation_attempt: int
    seed: int
    request_kind: str
    context: Mapping
    invalid_output: str = ""
    validation_error: str = ""


@dataclass(frozen=True)
class ConversationGenerationResult:
    request_id: str
    output: str = ""
    error: str = ""
    generated_token_count: int = 0


def generation_request_id(
    *, simulation_seed: int, day: int, hour: int, session_id: str,
    schedule_index: int, turn_index: int, generation_attempt: int,
    request_kind: str,
) -> str:
    identity = "|".join(map(str, (
        simulation_seed, day, hour, session_id, schedule_index, turn_index,
        generation_attempt, request_kind,
    )))
    return f"conversation-{hashlib.sha256(identity.encode()).hexdigest()[:24]}"
