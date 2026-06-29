from src.simulation.conversation_tagger import ConversationTagger
from src.town.daily_event import DailyEvent


def test_get_initial_conversation_tags_combines_inferred_and_parsed_tags():
    tagger = ConversationTagger()

    tags = tagger.get_initial_conversation_tags(
        conversation="I heard a rumor about the market.",
        parsed_tags=["parser_tag"],
    )

    assert "rumor" in tags
    assert "market" in tags
    assert "parser_tag" in tags


def test_add_daily_event_tags_when_conversation_mentions_event_name():
    tagger = ConversationTagger()

    event = DailyEvent(
        id="farmers_market",
        name="Farmers Market",
        description="Local vendors are setting up booths.",
        location_id="market",
        tags=["market", "community"],
    )

    tags = tagger.add_daily_event_tags(
        conversation="The farmers market is busy today.",
        conversation_tags=["market"],
        current_daily_event=event,
    )

    assert "event" in tags
    assert "farmers_market" in tags


def test_add_daily_event_tags_when_event_tag_already_present():
    tagger = ConversationTagger()

    event = DailyEvent(
        id="library_fundraiser",
        name="Library Fundraiser",
        description="The library is raising money.",
        location_id="library",
        tags=["library", "community"],
    )

    tags = tagger.add_daily_event_tags(
        conversation="People are gathering today.",
        conversation_tags=["event"],
        current_daily_event=event,
    )

    assert tags.count("event") == 2
    assert "library_fundraiser" in tags


def test_add_daily_event_tags_does_nothing_without_event():
    tagger = ConversationTagger()

    tags = tagger.add_daily_event_tags(
        conversation="The town feels busy.",
        conversation_tags=["town"],
        current_daily_event=None,
    )

    assert tags == ["town"]


def test_remove_action_tags_removes_only_action_labels():
    tagger = ConversationTagger()

    tags = tagger.remove_action_tags(
        [
            "market",
            "chat",
            "offer_help",
            "neutral",
            "library",
        ]
    )

    assert tags == [
        "market",
        "neutral",
        "library",
    ]


def test_finalize_conversation_tags_adds_event_relationship_action_and_dedupes():
    tagger = ConversationTagger()

    event = DailyEvent(
        id="farmers_market",
        name="Farmers Market",
        description="Local vendors are setting up booths.",
        location_id="market",
        tags=["market", "community"],
    )

    tags = tagger.finalize_conversation_tags(
        conversation="The farmers market is busy today.",
        conversation_tags=[
            "market",
            "chat",
            "market",
            "event",
        ],
        current_daily_event=event,
        relationship_label="neutral",
        action="offer_help",
    )

    assert tags == [
        "market",
        "event",
        "farmers_market",
        "neutral",
        "offer_help",
    ]
    