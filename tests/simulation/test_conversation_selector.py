from src.agents.agent import Agent
from src.agents.relationships import RelationshipManager
from src.simulation.conversation_selector import ConversationSelector


def build_agent(
    name: str,
    location_id: str,
) -> Agent:
    return Agent(
        id=f"agent_{name.lower()}",
        name=name,
        personality="curious",
        location_id=location_id,
        occupation="resident",
        goals=[],
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
    )


def test_group_agents_by_location_groups_agents_by_current_location():
    selector = ConversationSelector(
        relationships=RelationshipManager(),
    )

    maya = build_agent("Maya", "library")
    ethan = build_agent("Ethan", "library")
    lena = build_agent("Lena", "market")

    grouped = selector.group_agents_by_location(
        agents=[
            maya,
            ethan,
            lena,
        ],
    )

    assert grouped == {
        "library": [
            maya,
            ethan,
        ],
        "market": [
            lena,
        ],
    }


def test_choose_conversation_pair_returns_two_different_agents():
    selector = ConversationSelector(
        relationships=RelationshipManager(),
    )

    maya = build_agent("Maya", "library")
    ethan = build_agent("Ethan", "library")

    speaker, listener = selector.choose_conversation_pair(
        agents_here=[
            maya,
            ethan,
        ],
    )

    assert speaker in [maya, ethan]
    assert listener in [maya, ethan]
    assert speaker is not listener


def test_choose_conversation_pair_uses_intent_bonus_function():
    relationships = RelationshipManager()
    selector = ConversationSelector(
        relationships=relationships,
    )

    maya = build_agent("Maya", "library")
    ethan = build_agent("Ethan", "library")
    lena = build_agent("Lena", "library")

    calls = []

    def intent_bonus_fn(speaker, listener):
        calls.append((speaker.name, listener.name))
        return 3

    selector.choose_conversation_pair(
        agents_here=[
            maya,
            ethan,
            lena,
        ],
        intent_bonus_fn=intent_bonus_fn,
    )

    assert calls
    assert all(
        speaker_name != listener_name
        for speaker_name, listener_name in calls
    )


def test_get_intent_bonus_returns_zero_without_callback():
    selector = ConversationSelector(
        relationships=RelationshipManager(),
    )

    maya = build_agent("Maya", "library")
    ethan = build_agent("Ethan", "library")

    assert selector.get_intent_bonus(
        speaker=maya,
        listener=ethan,
        intent_bonus_fn=None,
    ) == 0


def test_get_intent_bonus_uses_callback_when_provided():
    selector = ConversationSelector(
        relationships=RelationshipManager(),
    )

    maya = build_agent("Maya", "library")
    ethan = build_agent("Ethan", "library")

    assert selector.get_intent_bonus(
        speaker=maya,
        listener=ethan,
        intent_bonus_fn=lambda speaker, listener: 5,
    ) == 5