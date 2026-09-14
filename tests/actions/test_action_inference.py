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


def test_infer_personal_uncertainty_as_chat_not_rumor():
    actions = ActionSystem()

    assert actions.infer_action(
        "I'm not sure this cleanup effort will make much difference.", []
    ) == "chat"


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


def test_infer_common_real_llm_action_language_variants_and_reason():
    actions = ActionSystem()
    cases = {
        "Would you be able to help me check these records?": "ask_for_help",
        "I'm happy to help with the cleanup.": "offer_help",
        "I think you're mistaken about the schedule.": "argue",
        "You were excellent with the volunteers.": "compliment",
        "The library shelves are so organized.": "compliment",
        "Let's tackle this together before noon.": "cooperate",
        "Let's sort these supplies together while we're here.": "cooperate",
        "Let's sort these boxes together while we're here.": "cooperate",
        "Word is the supplier may be unreliable, though I cannot confirm it.": "share_rumor",
        "Do you have any contacts in the farming community?": "ask_for_help",
        "Can you tell me more about the town's history?": "ask_for_help",
    }

    for dialogue, expected_action in cases.items():
        action, reason = actions.infer_action_with_reason(dialogue, [])
        assert action == expected_action
        assert reason != "no_action_language"
