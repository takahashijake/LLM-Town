import random

from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.agents.relationship_event import RelationshipEvent
from src.agents.relationships import RelationshipManager, SocialMemory


class RelationshipUpdater:
    """Apply legacy pair scores and conservative directional social learning."""

    MEMORY_LIMIT = 8
    RECIPIENT_DELTAS = {
        "compliment": {"affinity": 0.10},
        "apologize": {"trust": 0.08, "affinity": 0.08, "hostility": -0.12},
        "offer_help": {
            "trust": 0.12, "affinity": 0.06,
            "helpfulness": 0.18, "hostility": -0.04,
        },
        "cooperate": {
            "trust": 0.12, "affinity": 0.06,
            "cooperation": 0.20, "helpfulness": 0.04, "hostility": -0.05,
        },
        "argue": {"trust": -0.08, "affinity": -0.15, "hostility": 0.15},
        "insult": {"trust": -0.18, "affinity": -0.25, "hostility": 0.28},
        "storm_off": {"trust": -0.12, "affinity": -0.18,
                       "cooperation": -0.12, "hostility": 0.18},
        "share_rumor": {"trust": -0.04, "hostility": 0.03},
    }
    ACTOR_DELTAS = {
        "apologize": {"affinity": 0.04, "hostility": -0.06},
        "cooperate": {
            "trust": 0.08, "affinity": 0.05,
            "cooperation": 0.16, "hostility": -0.05,
        },
        "argue": {"affinity": -0.08, "hostility": 0.10},
        "insult": {"affinity": -0.12, "hostility": 0.16},
        "storm_off": {"affinity": -0.10, "hostility": 0.12},
    }
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
        outcome: str = "completed",
        directed_deltas: dict[str, dict[str, float]] | None = None,
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
            outcome=outcome,
            directed_deltas=directed_deltas or {},
        )

    @staticmethod
    def _summary(
        owner: Agent,
        counterpart: Agent,
        actor: Agent,
        action: str,
        outcome: str,
    ) -> str:
        if action == "ask_for_help" and outcome in {"refused", "rejected", "failed"}:
            if owner.name == actor.name:
                return f"{counterpart.name} refused my request for help."
            return f"I refused {counterpart.name}'s request for help."
        reciprocal = {
            "cooperate": f"{counterpart.name} and I cooperated.",
        }
        if action in reciprocal:
            return reciprocal[action]
        recipient_phrases = {
            "compliment": "complimented me",
            "apologize": "apologized to me",
            "offer_help": "offered me help",
            "ask_for_help": "asked me for help",
            "argue": "argued with me",
            "insult": "insulted me",
            "storm_off": "walked away from our conversation",
            "share_rumor": "shared a rumor with me",
        }
        actor_phrases = {
            "compliment": "complimented",
            "apologize": "apologized to",
            "offer_help": "offered help to",
            "ask_for_help": "asked for help from",
            "argue": "argued with",
            "insult": "insulted",
            "storm_off": "walked away from",
            "share_rumor": "shared a rumor with",
        }
        if owner.name == actor.name:
            phrase = actor_phrases.get(action, "spoke with")
            return f"I {phrase} {counterpart.name}."
        phrase = recipient_phrases.get(action, "spoke with me")
        return f"{counterpart.name} {phrase}."

    def apply_structured_relationship_update(
        self,
        *,
        day: int,
        hour: int,
        speaker: Agent,
        listener: Agent,
        action: str,
        outcome: str = "completed",
    ) -> dict[str, dict]:
        """Update both private views using only a finalized action/outcome."""
        actor_deltas = dict(self.ACTOR_DELTAS.get(action, {}))
        recipient_deltas = dict(self.RECIPIENT_DELTAS.get(action, {}))
        if action == "ask_for_help" and outcome in {"refused", "rejected", "failed"}:
            actor_deltas = {
                "trust": -0.12, "affinity": -0.08,
                "helpfulness": -0.18, "cooperation": -0.08,
            }

        updates: dict[str, dict] = {}
        for owner, counterpart, deltas in (
            (speaker, listener, actor_deltas),
            (listener, speaker, recipient_deltas),
        ):
            state = owner.get_relationship_state(counterpart.name)
            applied = state.apply(deltas, day)
            memory = None
            if action != "chat" or applied:
                memory = SocialMemory(
                    day=day,
                    hour=hour,
                    counterpart=counterpart.name,
                    actor=speaker.name,
                    action=action,
                    outcome=outcome,
                    summary=self._summary(owner, counterpart, speaker, action, outcome),
                    deltas=applied,
                )
                owner.remember_social_episode(memory, self.MEMORY_LIMIT)
            updates[owner.name] = {
                "counterpart": counterpart.name,
                "delta": applied,
                "snapshot": state.to_dict(),
                "memory": memory.to_dict() if memory else None,
            }
        return updates

    @staticmethod
    def relationship_snapshot(agent: Agent, counterpart: str) -> dict:
        return agent.get_relationship_state(counterpart).to_dict()

    @staticmethod
    def format_social_memories(
        agent: Agent,
        counterpart: str,
        limit: int = 3,
    ) -> list[str]:
        return [
            f"Day {memory.day}: {memory.summary}"
            for memory in agent.get_social_memories(counterpart, limit=limit)
        ]

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
