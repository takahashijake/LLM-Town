import pytest

from src.actions.action_system import ActionSystem


@pytest.mark.parametrize("dialogue,expected", [
    ("Could you help me carry these?", "ask_for_help"),
    ("Would you give me a hand?", "ask_for_help"),
    ("I could use some help.", "ask_for_help"),
    ("Can you help me sort this?", "ask_for_help"),
    ("We could use some extra hands. Want to join us?", "ask_for_help"),
    ("Do you think you could gather feedback?", "ask_for_help"),
    ("Do you have any trash bags?", "ask_for_help"),
    ("Could you lend me a hand?", "ask_for_help"),
    ("I can help you carry that.", "offer_help"),
    ("Let me give you a hand.", "offer_help"),
    ("I'll help you with the records.", "offer_help"),
    ("I can take care of that for you.", "offer_help"),
    ("I can lend you a hand.", "offer_help"),
    ("Let's sort these together.", "cooperate"),
    ("We can work on this together.", "cooperate"),
    ("Why don't we check the records together?", "cooperate"),
    ("Let's split the work.", "cooperate"),
    ("You handled that really well.", "compliment"),
    ("I disagree with that plan.", "argue"),
    ("Good morning.", "chat"),
    ("Where is the library?", "chat"),
    ("Would you like to come to the fair?", "chat"),
])
def test_social_paraphrase_matrix(dialogue, expected):
    assert ActionSystem().infer_action(dialogue, []) == expected
