import copy
import json

from src.llm.parser import parse_llm_conversation_output
from src.simulation.conversation_session import ResponseOutcomeResolver
from src.simulation.social_semantics import classify_commitment_relation, semantic_action_compatibility
from src.systems.commitments import CommitmentError, CommitmentSystem


def proposal(kind="help"):
    values = {
        "help": {"commitment_type":"help", "metadata":{"task":"repair the fence"}, "due_day":2},
        "transfer": {"commitment_type":"transfer", "metadata":{"good_id":"reference_book", "quantity":1}, "due_day":2},
    }
    return values[kind]


def test_clear_acceptance_and_ambiguous_positivity_are_distinct():
    resolver = ResponseOutcomeResolver()
    assert resolver.resolve("ask_for_help", "Sure, I can help with that. Maybe we can start early?", proposal=proposal(), parsed_action="offer_help") == "accepted"
    assert resolver.resolve("ask_for_help", "Sure, I could use practice on fences. How's yours?", proposal=proposal(), parsed_action="chat") == "unresolved"
    assert resolver.resolve("ask_for_help", "Sure thing, Maya. How about stories over coffee?", proposal=proposal("transfer"), parsed_action="chat") == "unresolved"


def test_structured_annotation_is_bounded_and_backward_compatible():
    old = parse_llm_conversation_output('{"dialogue":"Hello","action":"chat"}')
    assert old["social_response"]["type"] == "none"
    raw = json.dumps({"dialogue":"Sure","action":"chat", "social_response":{"type":"mutate_inventory","target":"gold","confidence":99,"evidence":"all"}})
    parsed = parse_llm_conversation_output(raw)
    assert parsed["social_response"] == {"type":"none", "target":"none", "confidence":"none", "evidence":[]}


def test_social_annotations_and_contradiction_checks_do_not_mutate_state():
    system = CommitmentSystem()
    item = system.create(proposer_id="a", counterpart_id="b", commitment_type="help", day=1, due_day=2, metadata={"task":"repair"})
    system.transition(item.id, "accepted", day=1, reason="accepted")
    before = copy.deepcopy(system.to_dict())
    classify_commitment_relation(item.to_dict(), "I already helped you.", {"commitment_id":item.id,"relation":"references_fulfillment"})
    assert system.to_dict() == before
    assert item.status == "accepted"


def test_false_fulfillment_claim_cannot_fulfill_or_reopen_terminal_commitment():
    system = CommitmentSystem()
    item = system.create(proposer_id="a", counterpart_id="b", commitment_type="help", day=1, due_day=2, metadata={"task":"repair"})
    system.transition(item.id, "accepted", day=1, reason="accepted")
    system.transition(item.id, "expired", day=3, reason="missed")
    result = classify_commitment_relation(item.to_dict(), "I already repaired it.")
    assert result["classification"] == "contradiction"
    assert item.status == "expired"
    try:
        system.transition(item.id, "accepted", day=3, reason="claim")
    except CommitmentError:
        pass
    assert item.status == "expired"


def test_semantic_evaluation_is_deterministic_and_action_compatibility_is_not_literal():
    commitment = {"id":"commitment-00000001", "status":"expired"}
    first = classify_commitment_relation(commitment, "I couldn't do it. I can try again today.")
    assert first == classify_commitment_relation(commitment, "I couldn't do it. I can try again today.")
    assert semantic_action_compatibility("cooperate", "Maybe we could team up on some projects soon.")[0]
