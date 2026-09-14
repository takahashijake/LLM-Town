import random
from collections.abc import Callable

from src.agents.agent import Agent
from src.agents.relationships import RelationshipManager


class ConversationSelector:
    def __init__(self, relationships: RelationshipManager):
        self.relationships = relationships

    def group_agents_by_location(
        self,
        agents: list[Agent],
    ) -> dict[str, list[Agent]]:
        agents_by_location = {}

        for agent in agents:
            agents_by_location.setdefault(agent.location_id, []).append(agent)

        return agents_by_location

    def choose_conversation_pair(
        self,
        agents_here: list[Agent],
        intent_bonus_fn: Callable[[Agent, Agent], int] | None = None,
    ) -> tuple[Agent, Agent]:
        speaker = random.choice(agents_here)

        possible_listeners = [
            agent
            for agent in agents_here
            if agent.name != speaker.name
        ]

        weights = self.get_listener_weights(
            speaker,
            possible_listeners,
            intent_bonus_fn=intent_bonus_fn,
        )

        listener = random.choices(
            possible_listeners,
            weights=weights,
            k=1,
        )[0]

        return speaker, listener

    def get_listener_weights(
        self,
        speaker: Agent,
        listeners: list[Agent],
        intent_bonus_fn: Callable[[Agent, Agent], int] | None = None,
    ) -> list[int]:
        """Expose the interpretable target weights used by seeded selection."""
        return [
            max(
                1,
                self.relationships.get_conversation_weight(
                    speaker.name, listener.name
                )
                + self.get_relationship_memory_bonus(speaker, listener)
                + self.get_intent_bonus(
                    speaker=speaker,
                    listener=listener,
                    intent_bonus_fn=intent_bonus_fn,
                ),
            )
            for listener in listeners
        ]

    @staticmethod
    def get_relationship_memory_bonus(speaker: Agent, listener: Agent) -> int:
        state = speaker.get_relationship_state(listener.name)
        return round(state.decision_value() * 4)

    def get_intent_bonus(
        self,
        speaker: Agent,
        listener: Agent,
        intent_bonus_fn: Callable[[Agent, Agent], int] | None,
    ) -> int:
        if not intent_bonus_fn:
            return 0

        return intent_bonus_fn(speaker, listener)
