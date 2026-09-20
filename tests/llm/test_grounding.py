import json

import pytest

from src.llm.grounding import GroundingValidator
from src.llm.parser import parse_llm_conversation_output


@pytest.fixture
def context():
    return {
        "location": "library",
        "grounding_sources": {
            "memory:1": "Maya and Ethan sorted the records together yesterday.",
            "public_event:event-1": "Book fair: A public book fair is underway.",
            "reputation_claim:1": "Carlos seems helpful based on direct experience.",
        },
    }


@pytest.mark.parametrize("dialogue,refs", [
    ("Remember when we sorted the records together?", ["memory:1"]),
    ("The book fair is underway.", ["public_event:event-1"]),
    ("Carlos seems helpful.", ["reputation_claim:1"]),
    ("I think the records are tedious.", []),
    ("Do you know whether a shop opened?", []),
    ("Maybe there is a garden nearby.", []),
])
def test_supported_or_nonfactual_language_is_allowed(context, dialogue, refs):
    assert GroundingValidator().validate(dialogue, refs, context).valid


def test_invented_shared_history_is_detected(context):
    result = GroundingValidator().validate("Remember when we played cards?", [], context)
    assert not result.valid
    assert result.candidate_type == "shared_history"


def test_invented_named_world_entity_is_detected(context):
    result = GroundingValidator().validate("The Willow Garden shop sells bread.", [], context)
    assert not result.valid
    assert result.candidate_type == "named_world_entity"


@pytest.mark.parametrize("dialogue", [
    "The old mill could use a fresh coat of paint.",
    "Mrs. Thompson always has valuable insights.",
])
def test_invented_described_place_or_person_is_detected(context, dialogue):
    result = GroundingValidator().validate(dialogue, [], context)
    assert not result.valid
    assert result.candidate_type == "named_world_entity"


def test_invalid_reference_is_rejected_and_metadata_is_not_dialogue(context):
    raw = json.dumps({"dialogue": "The fair is busy.", "action": "chat", "grounding_refs": ["memory:999"]})
    parsed = parse_llm_conversation_output(raw)
    result = GroundingValidator().validate(parsed["dialogue"], parsed["grounding_refs"], context)
    assert not result.valid
    assert "memory:999" not in parsed["dialogue"]


def test_grounding_metadata_in_spoken_dialogue_is_rejected(context):
    result = GroundingValidator().validate(
        "According to memory:1, we sorted the records.", ["memory:1"], context
    )
    assert not result.valid
    assert result.candidate_type == "metadata_leak"
