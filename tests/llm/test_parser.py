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

def test_parse_uses_llm_action_when_allowed():
    output = (
        '{"dialogue": "Carlos, your presentation was really engaging.", '
        '"action": "compliment", '
        '"tags": ["event"], '
        '"reason": "The speaker praises Carlos."}'
    )

    parsed = parse_llm_conversation_output(
        output,
        allowed_actions=["chat", "compliment"],
    )

    assert parsed["dialogue"] == "Carlos, your presentation was really engaging."
    assert parsed["action"] == "compliment"
    assert parsed["tags"] == ["event"]
    assert parsed["reason"] == "The speaker praises Carlos."
    assert parsed["action_source"] == "llm"


def test_parse_disallowed_action_falls_back_to_chat():
    output = (
        '{"dialogue": "You handled that well.", '
        '"action": "compliment"}'
    )

    parsed = parse_llm_conversation_output(
        output,
        allowed_actions=["chat", "argue"],
    )

    assert parsed["action"] == "chat"
    assert parsed["raw_action"] == "compliment"
    assert parsed["action_source"] == "fallback_disallowed_action"


def test_parse_action_alias_normalizes_to_known_action():
    output = (
        '{"dialogue": "You handled that well.", '
        '"action": "praise"}'
    )

    parsed = parse_llm_conversation_output(
        output,
        allowed_actions=["chat", "compliment"],
    )

    assert parsed["action"] == "compliment"
    assert parsed["action_source"] == "llm"


def test_parse_keeps_chat_when_chat_is_allowed():
    output = (
        '{"dialogue": "The market seems busier than usual today.", '
        '"action": "chat"}'
    )

    parsed = parse_llm_conversation_output(
        output,
        allowed_actions=["chat", "compliment"],
    )

    assert parsed["action"] == "chat"
    assert parsed["action_source"] == "llm"