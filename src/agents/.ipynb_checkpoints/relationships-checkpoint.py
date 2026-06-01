class RelationshipManager:
    def __init__(self):
        self.scores = {}

    def _key(self, agent_a: str, agent_b: str) -> tuple[str, str]:
        return tuple(sorted([agent_a, agent_b]))

    def get_score(self, agent_a: str, agent_b: str) -> int:
        return self.scores.get(self._key(agent_a, agent_b), 0)

    def change_score(self, agent_a: str, agent_b: str, amount: int) -> int:
        key = self._key(agent_a, agent_b)
        self.scores[key] = self.scores.get(key, 0) + amount
        return self.scores[key]

    def describe_relationship(self, agent_a: str, agent_b: str) -> str:
        score = self.get_score(agent_a, agent_b)

        if score >= 5:
            return "close friends"
        if score >= 2:
            return "friendly"
        if score <= -5:
            return "enemies"
        if score <= -2:
            return "tense"

        return "neutral"

    def get_conversation_weight(self, agent_a: str, agent_b: str) -> int:
        label = self.describe_relationship(agent_a, agent_b)
    
        if label == "close friends":
            return 6
        if label == "friendly":
            return 4
        if label == "neutral":
            return 2
        if label == "tense":
            return 1
        if label == "enemies":
            return 1
    
        return 2