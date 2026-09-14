from src.actions.action_system import ActionSystem


def test_infer_compliment_from_praise():
    actions = ActionSystem()

    assert actions.infer_action(
        "You did a good job organizing that.", []
    ) == "compliment"


def test_infer_offer_help_from_assistance_offer():
    actions = ActionSystem()

    assert actions.infer_action(
        "I can help you organize the cleanup.", []
    ) == "offer_help"


def test_infer_ask_for_help_from_advice_request():
    actions = ActionSystem()

    assert actions.infer_action(
        "Could you give me advice on where to start?", []
    ) == "ask_for_help"


def test_infer_apology_from_regret():
    actions = ActionSystem()

    assert actions.infer_action(
        "I'm sorry about earlier. I should have handled that better.", []
    ) == "apologize"


def test_infer_rumor_from_uncertain_information():
    actions = ActionSystem()

    assert actions.infer_action(
        "Someone said the supplier might be unreliable.", []
    ) == "share_rumor"


def test_infer_argue_from_disagreement():
    actions = ActionSystem()

    assert actions.infer_action(
        "I disagree. That plan does not make sense.", []
    ) == "argue"

def test_infer_compliment_from_gratitude():
    actions = ActionSystem()

    assert actions.infer_action(
        "Thanks for coming to support the fundraiser, Ethan.", []
    ) == "compliment"


def test_infer_compliment_from_appreciation():
    actions = ActionSystem()

    assert actions.infer_action(
        "I appreciate you helping with the cleanup.", []
    ) == "compliment"

def test_infer_cooperate_from_team_up():
    actions = ActionSystem()

    assert actions.infer_action(
        "Want to team up for the cleanup?", []
    ) == "cooperate"


def test_infer_cooperate_from_work_together():
    actions = ActionSystem()

    assert actions.infer_action(
        "We could work together on this.", []
    ) == "cooperate"


def test_infer_cooperate_from_coordinate():
    actions = ActionSystem()

    assert actions.infer_action(
        "Let's coordinate with the volunteers.", []
    ) == "cooperate"


def test_infer_recommendation_as_chat_not_offer_help():
    actions = ActionSystem()

    assert actions.infer_action(
        "That discount might be worth checking out.", []
    ) == "chat"
