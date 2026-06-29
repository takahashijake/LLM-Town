import random

from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.agents.relationship_event import RelationshipEvent
from src.agents.relationships import RelationshipManager


class RelationshipUpdater:
    def __init__(
        self,
        relationships: RelationshipManager,
        actions: ActionSystem,
    ):
        self.relationships = relationships
        self.actions = actions

    def should_record_relationship_event(
        self,
        action: str,
        relationship_change: int,
    ) -> bool:
        return action != "chat" or relationship_change != 0

    def create_relationship_event(
        self,
        day: int,
        hour: int,
        location_id: str,
        speaker: Agent,
        listener: Agent,
        action: str,
        relationship_change: int,
        new_score: int,
        relationship_label: str,
        conversation: str,
        tags: list[str],
    ) -> RelationshipEvent:
        if relationship_change > 0:
            direction = "improved"
        elif relationship_change < 0:
            direction = "worsened"
        else:
            direction = "stayed the same"

        description = (
            f"{speaker.name} used action '{action}' with {listener.name}. "
            f"Their relationship {direction} by {relationship_change:+d}; "
            f"score is now {new_score:+d} ({relationship_label})."
        )

        return RelationshipEvent(
            day=day,
            hour=hour,
            agent_a=speaker.name,
            agent_b=listener.name,
            action=action,
            relationship_change=relationship_change,
            relationship_score=new_score,
            relationship_label=relationship_label,
            description=description,
            location=location_id,
            tags=tags,
            conversation=conversation,
        )

    def record_relationship_event(
        self,
        relationship_events: list[RelationshipEvent],
        relationship_event: RelationshipEvent,
    ) -> None:
        relationship_events.append(relationship_event)

    def get_recent_relationship_events(
        self,
        relationship_events: list[RelationshipEvent],
        agent_a: str,
        agent_b: str,
        limit: int = 3,
    ) -> list[RelationshipEvent]:
        matching_events = [
            event
            for event in relationship_events
            if event.involves_pair(agent_a, agent_b)
        ]

        matching_events.sort(
            key=lambda event: (
                event.day,
                event.hour,
            ),
            reverse=True,
        )

        return matching_events[:limit]

    def format_relationship_history_for_prompt(
        self,
        relationship_events: list[RelationshipEvent],
        agent_a: str,
        agent_b: str,
        limit: int = 3,
    ) -> list[str]:
        events = self.get_recent_relationship_events(
            relationship_events=relationship_events,
            agent_a=agent_a,
            agent_b=agent_b,
            limit=limit,
        )

        return [
            (
                f"Day {event.day}, {event.hour}:00: "
                f"{event.description} "
                f"Conversation: \"{event.conversation}\""
            )
            for event in events
        ]

    def sync_agent_relationships_from_manager(
        self,
        agents: list[Agent],
    ) -> None:
        agents_by_name = {
            agent.name: agent
            for agent in agents
        }

        for (agent_a, agent_b), score in self.relationships.scores.items():
            if agent_a not in agents_by_name or agent_b not in agents_by_name:
                continue

            agents_by_name[agent_a].update_relationship(agent_b, score)
            agents_by_name[agent_b].update_relationship(agent_a, score)

    def get_relationship_change(self, relationship_label: str) -> int:
        if relationship_label == "close friends":
            return random.choice([-1, 0, 0, 0, 0, 0])

        if relationship_label == "friendly":
            return random.choice([-1, 0, 0, 0, 0])

        if relationship_label == "neutral":
            return random.choice([-1, 0, 0, 0, 0, 1])

        if relationship_label == "tense":
            return random.choice([-1, -1, 0, 0, 0])

        if relationship_label == "enemies":
            return random.choice([-1, 0, 0, 0])

        return random.choice([-1, 0, 0, 0])

    def calculate_relationship_change(
        self,
        action: str,
        old_relationship_label: str,
        old_relationship_score: int,
        relationship_drift: int | None = None,
    ) -> int:
        action_effect = self.actions.get_relationship_effect(action)

        if relationship_drift is None:
            relationship_drift = self.get_relationship_change(old_relationship_label)

        relationship_change = action_effect + relationship_drift

        # Saturation: close relationships are harder to improve.
        if old_relationship_score >= 7 and relationship_change > 0:
            relationship_change = 0

        # Very bad relationships are harder to repair casually.
        if old_relationship_score <= -7 and relationship_change > 0 and action == "chat":
            relationship_change = 0

        return max(-3, min(3, relationship_change))

    def apply_relationship_change(
        self,
        speaker: Agent,
        listener: Agent,
        relationship_change: int,
    ) -> tuple[int, str]:
        new_score = self.relationships.change_score(
            speaker.name,
            listener.name,
            relationship_change,
        )

        speaker.update_relationship(listener.name, new_score)
        listener.update_relationship(speaker.name, new_score)

        relationship_label = self.relationships.describe_relationship(
            speaker.name,
            listener.name,
        )

        return new_score, relationship_label

        