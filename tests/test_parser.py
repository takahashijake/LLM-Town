from src.llm.parser import infer_conversation_tags


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