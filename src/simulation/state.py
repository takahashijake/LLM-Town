import json
from pathlib import Path


class SimulationState:
    def __init__(self, path: str = "data/save_state.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        engine,
        current_day: int,
        current_hour: int,
        *,
        day_complete: bool = False,
    ) -> None:
        current_daily_event = getattr(engine, "current_daily_event", None)

        state = {
            "current_day": current_day,
            "current_hour": current_hour,
            "day_complete": day_complete,
            "current_daily_event": (
                {
                    "id": current_daily_event.id,
                    "name": current_daily_event.name,
                    "description": current_daily_event.description,
                    "location_id": current_daily_event.location_id,
                    "tags": current_daily_event.tags,
                }
                if current_daily_event
                else None
            ),
            "daily_event_history": getattr(engine, "daily_event_history", []),
            "recent_dialogues": getattr(engine, "recent_dialogues", []),
            "recent_actions": getattr(engine, "recent_actions", []),
            "activity_records": getattr(engine, "activity_records", []),
            "agents": [
                {
                    "id": agent.id,
                    "name": agent.name,
                    "personality": agent.personality,
                    "location_id": agent.location_id,
                    "memory": [memory.to_dict() for memory in agent.memory],
                    "memory_archive": [
                        memory.to_dict()
                        for memory in agent.memory_archive
                    ],
                    "memory_summary": agent.memory_summary,
                    "daily_journals" : [
                        journal.to_dict()
                        for journal in agent.daily_journals
                    ],
                    # Keep the legacy text field while preserving the complete
                    # durable model in a backward-compatible sibling field.
                    "goals": agent.goal_descriptions(),
                    "structured_goals": [
                        goal.to_dict() for goal in agent.goals
                        if hasattr(goal, "to_dict")
                    ],
                    "needs" : agent.needs,
                    "relationships": agent.relationships,
                    "relationship_states": {
                        counterpart: relationship.to_dict()
                        for counterpart, relationship in agent.relationship_states.items()
                    },
                    "social_memories": {
                        counterpart: [memory.to_dict() for memory in memories]
                        for counterpart, memories in agent.social_memories.items()
                    },
                    "reputation_beliefs": {
                        target: {
                            dimension: belief.to_dict()
                            for dimension, belief in dimensions.items()
                        }
                        for target, dimensions in agent.reputation_beliefs.items()
                    },
                    "occupation" : agent.occupation,
                    "recent_topics" : agent.recent_topics,
                    "current_activity": agent.current_activity,
                    "current_activity_reason": agent.current_activity_reason,
                    "current_activity_tags": agent.current_activity_tags,
                }
                for agent in engine.agents
            ],
            "relationship_scores": {
                f"{a}|{b}": score
                for (a, b), score in engine.relationships.scores.items()
            },
            "relationship_events": [
                event.to_dict() 
                for event in getattr(engine, "relationship_events", [])
            ],
            "reputation_updates": list(
                getattr(engine, "reputation_updates", [])
            ),
            "agent_intents": {
                agent_name: intent.to_dict()
                for agent_name, intent in getattr(engine, "agent_intents", {}).items()
            },
            "intent_history": [
                intent.to_dict() if hasattr(intent, "to_dict") else intent
                for intent in getattr(engine, "intent_history", [])
            ],
            "town_arcs": [
                arc.to_dict()
                for arc in getattr(engine, "town_arcs", [])
            ],
            "economy": (
                engine.economy.to_dict()
                if getattr(engine, "economy", None) is not None
                else None
            ),
            "materials": (
                engine.materials.to_dict()
                if getattr(engine, "materials", None) is not None
                else None
            ),
            "crime": (
                engine.crime.to_dict()
                if getattr(engine, "crime", None) is not None
                else None
            ),
            "justice": (
                engine.justice.to_dict()
                if getattr(engine, "justice", None) is not None
                else None
            ),
        }

        self.path.write_text(json.dumps(state, indent=2))

    def load(self) -> dict | None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return None

        return json.loads(self.path.read_text())
