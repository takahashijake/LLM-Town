from src.agents.agent import Agent
from src.agents.intent import AgentIntent
from src.simulation.intent_system import IntentSystem


class FakeIntentPlanner:
    def __init__(self, intent_type: str = "socialize"):
        self.intent_type = intent_type
        self.calls = []

    def create_intent_for_agent(self, agent, engine, current_day):
        self.calls.append((agent.name, current_day))

        return AgentIntent(
            agent_name=agent.name,
            intent_type=self.intent_type,
            description=f"{agent.name} wants to {self.intent_type}.",
            created_day=current_day,
            expires_day=current_day + 2,
            priority=2,
            target_agent=None,
            target_location="cafe",
        )


def build_agent(name: str) -> Agent:
    return Agent(
        id=f"agent_{name.lower()}",
        name=name,
        personality="curious",
        location_id="cafe",
        occupation="resident",
        goals=[],
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
    )


def build_intent(
    agent_name: str,
    intent_type: str,
    target_agent: str | None = None,
) -> AgentIntent:
    return AgentIntent(
        agent_name=agent_name,
        intent_type=intent_type,
        description=f"{agent_name} has intent {intent_type}.",
        created_day=1,
        expires_day=3,
        priority=2,
        target_agent=target_agent,
        target_location=None,
    )


def test_get_intent_listener_weight_bonus_returns_zero_without_intent():
    system = IntentSystem(
        intent_planner=FakeIntentPlanner(),
        agent_intents={},
    )

    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    assert system.get_intent_listener_weight_bonus(speaker, listener) == 0


def test_get_intent_listener_weight_bonus_uses_targeted_intent_type():
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    system = IntentSystem(
        intent_planner=FakeIntentPlanner(),
        agent_intents={
            "Maya": build_intent(
                agent_name="Maya",
                intent_type="repair_relationship",
                target_agent="Ethan",
            )
        },
    )

    assert system.get_intent_listener_weight_bonus(speaker, listener) == 5


def test_get_intent_listener_weight_bonus_returns_zero_for_wrong_target():
    speaker = build_agent("Maya")
    listener = build_agent("Ethan")

    system = IntentSystem(
        intent_planner=FakeIntentPlanner(),
        agent_intents={
            "Maya": build_intent(
                agent_name="Maya",
                intent_type="build_friendship",
                target_agent="Lena",
            )
        },
    )

    assert system.get_intent_listener_weight_bonus(speaker, listener) == 0


def test_update_agent_intents_limits_same_type_to_two_agents():
    agents = [
        build_agent("Maya"),
        build_agent("Ethan"),
        build_agent("Lena"),
        build_agent("Carlos"),
    ]

    system = IntentSystem(
        intent_planner=FakeIntentPlanner(intent_type="socialize"),
        agent_intents={},
    )

    system.update_agent_intents(
        agents=agents,
        current_day=1,
        engine=object(),
    )

    assert len(system.agent_intents) == 2
    assert {
        intent.intent_type
        for intent in system.agent_intents.values()
    } == {"socialize"}


def test_update_agent_intents_keeps_unexpired_existing_intent():
    maya = build_agent("Maya")

    existing_intent = build_intent(
        agent_name="Maya",
        intent_type="investigate",
        target_agent=None,
    )

    system = IntentSystem(
        intent_planner=FakeIntentPlanner(intent_type="socialize"),
        agent_intents={
            "Maya": existing_intent,
        },
    )

    system.update_agent_intents(
        agents=[maya],
        current_day=2,
        engine=object(),
    )

    assert system.agent_intents["Maya"] is existing_intent
    assert system.intent_planner.calls == []


def test_get_agent_intent_text_returns_description_or_default():
    intent = build_intent(
        agent_name="Maya",
        intent_type="investigate",
        target_agent=None,
    )

    system = IntentSystem(
        intent_planner=FakeIntentPlanner(),
        agent_intents={
            "Maya": intent,
        },
    )

    assert system.get_agent_intent_text("Maya") == intent.description
    assert system.get_agent_intent_text("Ethan") == "No active intent."


def test_adjust_action_weights_for_repair_relationship_intent():
    system = IntentSystem(
        intent_planner=FakeIntentPlanner(),
        agent_intents={},
    )

    weights = {
        "chat": 8,
        "apologize": 1,
        "offer_help": 1,
        "argue": 3,
    }

    intent = build_intent(
        agent_name="Maya",
        intent_type="repair_relationship",
        target_agent="Ethan",
    )

    adjusted = system.adjust_action_weights_for_intent(
        weights=weights,
        intent=intent,
        listener_name="Ethan",
    )

    assert adjusted["apologize"] == 5
    assert adjusted["offer_help"] == 3
    assert adjusted["chat"] == 9
    assert adjusted["argue"] == 1


def test_adjust_action_weights_for_investigate_intent():
    system = IntentSystem(
        intent_planner=FakeIntentPlanner(),
        agent_intents={},
    )

    weights = {
        "chat": 8,
        "ask_for_help": 2,
        "share_rumor": 1,
    }

    intent = build_intent(
        agent_name="Maya",
        intent_type="investigate",
        target_agent=None,
    )

    adjusted = system.adjust_action_weights_for_intent(
        weights=weights,
        intent=intent,
        listener_name="Ethan",
    )

    assert adjusted["ask_for_help"] == 5
    assert adjusted["share_rumor"] == 3
    assert adjusted["chat"] == 9


def test_adjust_action_weights_for_wrong_target_returns_copy_unchanged():
    system = IntentSystem(
        intent_planner=FakeIntentPlanner(),
        agent_intents={},
    )

    weights = {
        "chat": 8,
        "offer_help": 1,
    }

    intent = build_intent(
        agent_name="Maya",
        intent_type="build_friendship",
        target_agent="Lena",
    )

    adjusted = system.adjust_action_weights_for_intent(
        weights=weights,
        intent=intent,
        listener_name="Ethan",
    )

    assert adjusted == weights
    assert adjusted is not weights