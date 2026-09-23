import json

import pytest

from types import SimpleNamespace

from src.agents.memory import Memory
from src.llm.grounding import GroundingValidator, build_grounding_packet, grounding_packet_for_prompt
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


def causal_memory(owner="a", event="commitment_fulfilled", counterparts=None, basis="participant"):
    return Memory(day=2, hour=1, type=event, event_type=event,
                  description="Ava fulfilled the promise to Bo concerning repairs.",
                  participants=["Ava", "Bo"], location="market", importance=5,
                  sentiment=2, tags=["causal_outcome"], source_system="commitments",
                  source_id="commitment-00000001", knowledge_basis=basis,
                  owner_id=owner, counterpart_ids=counterparts or ["b"], causal=True)


def test_packet_is_bounded_stable_and_hides_private_ids():
    speaker, listener = SimpleNamespace(id="a", name="Ava"), SimpleNamespace(id="b", name="Bo")
    memories = [causal_memory() for _ in range(8)]
    memories.append(causal_memory(owner="other"))
    packet = build_grounding_packet(memories, speaker=speaker, listener=listener, current_day=9)
    prompt = grounding_packet_for_prompt(packet)
    assert [row["ref"] for row in prompt] == ["g1", "g2", "g3"]
    assert all(row["outcome_polarity"] == "fulfilled" for row in prompt)
    assert all("owner_id" not in row and "counterpart_ids" not in row and "commitment-" not in str(row) for row in prompt)


@pytest.mark.parametrize("dialogue,polarity,reason", [
    ("You fulfilled that promise.", "failed", "outcome_polarity_reversed"),
    ("You failed that promise.", "fulfilled", "outcome_polarity_reversed"),
    ("You stole the missing goods.", "unknown_culprit", "unknown_culprit_asserted"),
    ("The materials have been transferred.", "accepted", "unsupported_authoritative_assertion"),
])
def test_structured_causal_claims_preserve_authority(dialogue, polarity, reason):
    packet = [{"ref": "g1", "fact": "bounded fact", "source_type": "test",
               "knowledge_basis": "participant", "counterpart": "Bo",
               "event_day": 2, "age_days": 1, "outcome_polarity": polarity}]
    result = GroundingValidator().validate(dialogue, ["g1"], {
        "grounding_packet": packet, "grounding_sources": {"g1": "bounded fact"},
    })
    assert not result.valid
    assert result.reason == reason


def test_follow_through_is_bounded_and_counterpart_scoped():
    packet = [{"ref": "g1", "fact": "promise failed", "source_type": "commitment_failed",
               "knowledge_basis": "participant", "counterpart": "Bo",
               "event_day": 2, "age_days": 1, "outcome_polarity": "failed"}]
    context = {"grounding_packet": packet, "grounding_sources": {"g1": "promise failed"}}
    valid = GroundingValidator().validate("Can we try again tomorrow?", ["g1"], context,
        follow_through={"kind": "propose_repair", "target": "Bo", "source_ref": "g1"})
    invalid = GroundingValidator().validate("Thanks.", ["g1"], context,
        follow_through={"kind": "appreciate", "target": "Else", "source_ref": "g1"})
    assert valid.valid and valid.follow_through["kind"] == "propose_repair"
    assert not invalid.valid and not invalid.follow_through


def test_targeted_follow_through_requires_the_visible_counterpart():
    packet = [{"ref": "g1", "fact": "promise failed", "source_type": "commitment_failed",
               "knowledge_basis": "participant", "counterpart": "Bo",
               "event_day": 2, "age_days": 1, "outcome_polarity": "failed"}]
    context = {"grounding_packet": packet, "grounding_sources": {"g1": "promise failed"}}
    result = GroundingValidator().validate(
        "Could we try again tomorrow?", ["g1"], context,
        follow_through={"kind": "propose_repair", "target": "", "source_ref": "g1"},
    )
    assert not result.valid
    assert result.reason == "follow_through_counterpart_required"
