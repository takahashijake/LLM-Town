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

        weights = [
            self.relationships.get_conversation_weight(
                speaker.name,
                listener.name,
            )
            + self.get_intent_bonus(
                speaker=speaker,
                listener=listener,
                intent_bonus_fn=intent_bonus_fn,
            )
            for listener in possible_listeners
        ]

        listener = random.choices(
            possible_listeners,
            weights=weights,
            k=1,
        )[0]

        return speaker, listener

    def get_intent_bonus(
        self,
        speaker: Agent,
        listener: Agent,
        intent_bonus_fn: Callable[[Agent, Agent], int] | None,
    ) -> int:
        if not intent_bonus_fn:
            return 0

        return intent_bonus_fn(speaker, listener)