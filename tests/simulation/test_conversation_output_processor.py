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


def test_real_mode_narration_fallback_preserves_grounded_suggested_move():
    processor = build_processor()
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")
    speaker.current_activity = "Review public records"

    output = processor.process_llm_output(
        raw_output=(
            '{"dialogue":"Maya asked Ethan for a lead.",'
            '"action":"ask_for_help","tags":[],"reason":""}'
        ),
        allowed_actions=["chat", "ask_for_help"],
        speaker=speaker,
        listener=listener,
        old_relationship_label="neutral",
        location_id="library",
        suggested_action="ask_for_help",
        current_day=2,
        current_daily_event=None,
        daily_event_history=[],
        conversation_context={"speaker_activity": "Review public records"},
        enforce_information_boundaries=True,
    )

    assert "advice" in output["conversation"].lower()
    assert ActionSystem().infer_action(output["conversation"], []) == "ask_for_help"
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


def test_process_malformed_output_uses_spoken_agent_fallback():
    processor = build_processor()
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    output = processor.process_llm_output(
        raw_output="model emitted no object",
        allowed_actions=["chat"],
        speaker=speaker,
        listener=listener,
        old_relationship_label="friendly",
        location_id="library",
        suggested_action="chat",
        current_day=2,
        current_daily_event=None,
        daily_event_history=[],
    )

    assert output["conversation"] == "I am glad we ran into each other today."
    assert output["dialogue_source"] == "agent_fallback_empty"
    assert output["parsed_output"]["action_source"] == "fallback_no_json"


def test_placeholder_and_third_person_narration_use_safe_fallbacks():
    processor = build_processor()
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")
    common = {
        "allowed_actions": ["chat"],
        "speaker": speaker,
        "listener": listener,
        "old_relationship_label": "neutral",
        "location_id": "library",
        "suggested_action": "chat",
        "current_day": 2,
        "current_daily_event": None,
        "daily_event_history": [],
    }

    placeholder = processor.process_llm_output(
        raw_output='{"dialogue": "spoken line", "action": "chat"}',
        **common,
    )
    narration = processor.process_llm_output(
        raw_output=(
            '{"dialogue": "Maya leaned closer to the map.", "action": "chat"}'
        ),
        **common,
    )

    assert placeholder["dialogue_source"] == "agent_fallback_empty"
    assert narration["dialogue_source"] == "agent_fallback_narration"


def test_unsourced_hearsay_is_not_saved_as_real_model_dialogue():
    processor = build_processor()
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    output = processor.process_llm_output(
        raw_output='{"dialogue": "I heard a stranger stole the ledger.", "action": "share_rumor", "tags": ["rumor"]}',
        allowed_actions=["chat", "share_rumor"],
        speaker=speaker,
        listener=listener,
        old_relationship_label="neutral",
        location_id="library",
        suggested_action="share_rumor",
        current_day=2,
        current_daily_event=None,
        daily_event_history=[],
        conversation_context={"relevant_memories": []},
        enforce_information_boundaries=True,
    )

    assert "stole the ledger" not in output["conversation"]
    assert "busy with" in output["conversation"]
    assert output["parsed_action"] == "chat"
    assert output["dialogue_source"] == "policy_fallback_unsourced_hearsay"
    assert "rumor" not in output["parsed_output"]["tags"]


def test_hearsay_is_preserved_when_speaker_has_an_uncertain_source():
    processor = build_processor()
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    output = processor.process_llm_output(
        raw_output='{"dialogue": "I heard the ledger may be missing.", "action": "share_rumor", "tags": ["rumor"]}',
        allowed_actions=["chat", "share_rumor"],
        speaker=speaker,
        listener=listener,
        old_relationship_label="neutral",
        location_id="library",
        suggested_action="share_rumor",
        current_day=2,
        current_daily_event=None,
        daily_event_history=[],
        conversation_context={
            "relevant_memories": ["Ethan said he was not sure where the ledger went."]
        },
        enforce_information_boundaries=True,
    )

    assert output["conversation"] == "I heard the ledger may be missing."
    assert output["parsed_action"] == "share_rumor"
    assert output["dialogue_source"] == "llm"


def test_unrelated_uncertain_source_does_not_license_invented_hearsay():
    processor = build_processor()
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    output = processor.process_llm_output(
        raw_output=(
            '{"dialogue": "I heard Lena stole from the bakery.", '
            '"action": "argue", "tags": []}'
        ),
        allowed_actions=["chat", "argue", "share_rumor"],
        speaker=speaker,
        listener=listener,
        old_relationship_label="neutral",
        location_id="library",
        suggested_action="chat",
        current_day=2,
        current_daily_event=None,
        daily_event_history=[],
        conversation_context={
            "relevant_memories": [
                "Someone said the market supplier might be unreliable."
            ]
        },
        enforce_information_boundaries=True,
    )

    assert "bakery" not in output["conversation"].lower()
    assert output["parsed_action"] == "chat"
    assert output["dialogue_source"] == "policy_fallback_unsourced_hearsay"


def test_structured_claim_blocks_mismatched_hearsay_even_with_wrong_model_action():
    processor = build_processor()
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")
    claim = {
        "subject_agent": "Lena",
        "dimension": "helpfulness",
        "value": 1,
        "source_type": "direct_interaction",
    }

    output = processor.process_llm_output(
        raw_output=(
            '{"dialogue": "I heard Lena was caught stealing from the bakery.", '
            '"action": "argue", "tags": []}'
        ),
        allowed_actions=["chat", "argue", "share_rumor"],
        speaker=speaker,
        listener=listener,
        old_relationship_label="neutral",
        location_id="library",
        suggested_action="chat",
        current_day=2,
        current_daily_event=None,
        daily_event_history=[],
        conversation_context={"reputation_rumor": claim},
        enforce_information_boundaries=True,
    )

    assert "stealing" not in output["conversation"].lower()
    assert output["parsed_action"] == "chat"
    assert output["dialogue_source"] == "policy_fallback_unsourced_hearsay"


def test_structured_reputation_rumor_replaces_changed_or_damaging_claim():
    processor = build_processor()
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")
    claim = {
        "subject_agent": "Carlos",
        "dimension": "helpfulness",
        "value": 1,
        "source_type": "direct_interaction",
    }

    output = processor.process_llm_output(
        raw_output='{"dialogue": "Carlos stole the ledger.", "action": "share_rumor", "tags": ["rumor"]}',
        allowed_actions=["chat", "share_rumor"],
        speaker=speaker,
        listener=listener,
        old_relationship_label="neutral",
        location_id="library",
        suggested_action="share_rumor",
        current_day=2,
        current_daily_event=None,
        daily_event_history=[],
        conversation_context={"reputation_rumor": claim},
        enforce_information_boundaries=True,
    )

    assert "stole" not in output["conversation"]
    assert "Carlos seemed helpful" in output["conversation"]
    assert output["parsed_action"] == "share_rumor"
    assert output["dialogue_source"] == (
        "policy_fallback_structured_reputation_rumor"
    )
