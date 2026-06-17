import json
from pathlib import Path


class SimulationState:
    def __init__(self, path: str = "data/save_state.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, engine, current_day: int, current_hour: int) -> None:
        state = {
            "current_day": current_day,
            "current_hour": current_hour,
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
                    "goals" : agent.goals,
                    "needs" : agent.needs,
                    "relationships": agent.relationships,
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
        }

        self.path.write_text(json.dumps(state, indent=2))

    def load(self) -> dict | None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return None

        return json.loads(self.path.read_text())