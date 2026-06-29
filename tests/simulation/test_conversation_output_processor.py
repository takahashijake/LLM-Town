from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.simulation.conversation_output_processor import ConversationOutputProcessor
from src.simulation.conversation_policy import ConversationPolicy
from src.town.daily_event import DailyEvent


def build_agent(name: str) -> Agent:
    return Agent(
        id=f"agent_{name.lower()}",
        name=name,
        personality="curious",
        location_id="library",
        occupation="resident",
        goals=[],
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
    )


def build_processor(
    recent_dialogues: list[str] | None = None,
) -> ConversationOutputProcessor:
    actions = ActionSystem()
    policy = ConversationPolicy(
        actions=actions,
        recent_dialogues=recent_dialogues or [],
        recent_actions=[],
    )

    return ConversationOutputProcessor(
        conversation_policy=policy,
    )


def test_process_llm_output_parses_json_and_cleans_dialogue():
    processor = build_processor()
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    raw_output = """
    {
        "dialogue": "Hello.I can help with that.",
        "action": "offer_help",
        "tags": ["helpful"],
        "reason": "Maya offers help."
    }
    """

    output = processor.process_llm_output(
        raw_output=raw_output,
        allowed_actions=["chat", "offer_help"],
        speaker=speaker,
        listener=listener,
        old_relationship_label="neutral",
        location_id="library",
        suggested_action="offer_help",
        current_day=2,
        current_daily_event=None,
        daily_event_history=[],
    )

    assert output["conversation"] == "Hello. I can help with that."
    assert output["parsed_action"] == "offer_help"
    assert output["parsed_output"]["action_source"] == "llm"
    assert output["parsed_output"]["tags"] == ["helpful"]


def test_process_llm_output_fixes_stale_event_reference():
    processor = build_processor()
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    current_event = DailyEvent(
        id="farmers_market",
        name="Farmers Market",
        description="Local vendors are setting up booths.",
        location_id="market",
        tags=["market"],
    )

    raw_output = """
    {
        "dialogue": "The book club today seems important.",
        "action": "chat",
        "tags": ["event"],
        "reason": ""
    }
    """

    output = processor.process_llm_output(
        raw_output=raw_output,
        allowed_actions=["chat"],
        speaker=speaker,
        listener=listener,
        old_relationship_label="neutral",
        location_id="library",
        suggested_action="chat",
        current_day=2,
        current_daily_event=current_event,
        daily_event_history=[
            {
                "day": 1,
                "id": "book_club",
                "name": "Book Club",
            }
        ],
    )

    assert output["conversation"] == "The book club recently seems important."


def test_process_llm_output_replaces_narration_with_agent_fallback():
    processor = build_processor()
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    raw_output = """
    {
        "dialogue": "Maya says hello to Ethan.",
        "action": "compliment",
        "tags": [],
        "reason": ""
    }
    """

    output = processor.process_llm_output(
        raw_output=raw_output,
        allowed_actions=["chat", "compliment"],
        speaker=speaker,
        listener=listener,
        old_relationship_label="friendly",
        location_id="library",
        suggested_action="compliment",
        current_day=2,
        current_daily_event=None,
        daily_event_history=[],
    )

    assert output["conversation"] == "I am glad we ran into each other today."
    assert output["parsed_action"] == "chat"


def test_process_llm_output_replaces_repeated_dialogue_with_fallback():
    repeated_dialogue = "the town feels busy today."

    processor = build_processor(
        recent_dialogues=[
            repeated_dialogue,
        ],
    )
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    raw_output = """
    {
        "dialogue": "The town feels busy today.",
        "action": "chat",
        "tags": [],
        "reason": ""
    }
    """

    output = processor.process_llm_output(
        raw_output=raw_output,
        allowed_actions=["chat", "offer_help"],
        speaker=speaker,
        listener=listener,
        old_relationship_label="neutral",
        location_id="library",
        suggested_action="offer_help",
        current_day=2,
        current_daily_event=None,
        daily_event_history=[],
    )

    assert output["conversation"] != "The town feels busy today."
    assert output["conversation"].startswith("I can help")
    assert output["parsed_action"] == "chat"