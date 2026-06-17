from src.llm.parser import infer_conversation_tags
from src.llm.parser import parse_llm_conversation_output

def test_infer_business_tag():
    tags = infer_conversation_tags("The market stall has a new business project.")

    assert "conversation" in tags
    assert "business" in tags


def test_infer_rumor_tag():
    tags = infer_conversation_tags("I heard a suspicious rumor about trust issues.")

    assert "conversation" in tags
    assert "rumor" in tags


def test_infer_market_tag():
    tags = infer_conversation_tags("The market price is too high.")

    assert "conversation" in tags
    assert "market" in tags


def test_infer_learning_tag():
    tags = infer_conversation_tags("I want to read a book for research.")

    assert "conversation" in tags
    assert "learning" in tags


def test_infer_conflict_tag():
    tags = infer_conversation_tags("I am done talking about this issue.")

    assert "conversation" in tags
    assert "conflict" in tags

def test_parse_cooperate_action():
    output = '{"dialogue": "We could work together on the cleanup.", "action": "cooperate"}'

    parsed = parse_llm_conversation_output(output)

    assert parsed["dialogue"] == "We could work together on the cleanup."
    assert parsed["action"] == "cooperate"


def test_parse_unknown_action_falls_back_to_chat():
    output = '{"dialogue": "Let us do something unusual.", "action": "dance"}'

    parsed = parse_llm_conversation_output(output)

    assert parsed["dialogue"] == "Let us do something unusual."
    assert parsed["action"] == "chat"