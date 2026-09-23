"""Canonical, provider-neutral contract for model conversation responses."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OutputConstraintMode(str, Enum):
    NATIVE_JSON_SCHEMA = "native_json_schema"
    NATIVE_JSON_OR_GRAMMAR = "native_json_or_grammar"
    PROMPTED_JSON = "prompted_json"
    LEGACY_TEXT = "legacy_text"


SOCIAL_INTENTS = (
    "none", "acknowledge", "appreciate", "question", "repair", "caution", "other",
)
FOLLOW_THROUGH_KINDS = (
    "none", "propose_repair", "decline_similar", "cooperate",
)


def grounded_response_schema() -> dict:
    """Return the same compact schema used for prompting and validation."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["utterance", "grounding_refs", "social_intent", "follow_through"],
        "properties": {
            "utterance": {"type": "string", "maxLength": 240},
            "grounding_refs": {
                "type": "array", "items": {"type": "string", "pattern": "^g[1-3]$"},
                "maxItems": 3, "uniqueItems": True,
            },
            "social_intent": {"type": "string", "enum": list(SOCIAL_INTENTS)},
            "follow_through": {
                "type": "object", "additionalProperties": False,
                "required": ["kind", "target", "grounding_ref"],
                "properties": {
                    "kind": {"type": "string", "enum": list(FOLLOW_THROUGH_KINDS)},
                    "target": {"type": "string", "maxLength": 80},
                    "grounding_ref": {"type": "string", "pattern": "^(|g[1-3])$"},
                },
            },
        },
    }


def compact_contract_example() -> str:
    return (
        '{"utterance":"spoken line","grounding_refs":[],"social_intent":"none",'
        '"follow_through":{"kind":"none","target":"","grounding_ref":""}}'
    )


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    supported_modes: tuple[OutputConstraintMode, ...]
    detail: str

    def select(self, requested: OutputConstraintMode) -> OutputConstraintMode:
        if requested in self.supported_modes:
            return requested
        raise ValueError(
            f"{self.provider} does not support {requested.value}; supported modes: "
            + ", ".join(mode.value for mode in self.supported_modes)
        )


TRANSFORMERS_CAPABILITIES = ProviderCapabilities(
    provider="huggingface_transformers_generate",
    supported_modes=(OutputConstraintMode.PROMPTED_JSON, OutputConstraintMode.LEGACY_TEXT),
    detail=(
        "The local AutoModelForCausalLM.generate path has no configured JSON schema or "
        "grammar processor. JSON is prompt-constrained only."
    ),
)
