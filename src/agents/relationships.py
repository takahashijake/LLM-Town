class RelationshipManager:
    def __init__(self):
        self.scores = {}

    def _key(self, agent_a: str, agent_b: str) -> tuple[str, str]:
        return tuple(sorted([agent_a, agent_b]))

    def get_score(self, agent_a: str, agent_b: str) -> int:
        return self.scores.get(self._key(agent_a, agent_b), 0)

    def change_score(self, agent_a: str, agent_b: str, amount: int) -> int:
        key = self._key(agent_a, agent_b)
        new_score = self.scores.get(key, 0) + amount
    
        new_score = max(-10, min(10, new_score))
    
        self.scores[key] = new_score
        return new_score

    def decay_all_relationships(self, probability: float = 0.05) -> None: 
        import random 

        for key, score in list(self.scores.items()): 
            if score > 0 and random.random() < probability: 
                self.scores[key] = score - 1 
            elif score < 0 and random.random() < probability: 
                self.scores[key] = score + 1 
        
    def describe_relationship(self, agent_a: str, agent_b: str) -> str:
        score = self.get_score(agent_a, agent_b)
    
        if score >= 7:
            return "close friends"
        if score >= 3:
            return "friendly"
        if score <= -7:
            return "enemies"
        if score <= -3:
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