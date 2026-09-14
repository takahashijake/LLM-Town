"""Legacy pair scores and Prompt 5 agent-specific relationship memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


RELATIONSHIP_DIMENSIONS = (
    "trust",
    "affinity",
    "cooperation",
    "helpfulness",
    "hostility",
)


def _bounded(value: float) -> float:
    return round(max(-1.0, min(1.0, float(value))), 3)


@dataclass
class SocialMemory:
    """A compact episode derived from a structured interaction outcome."""

    day: int
    hour: int
    counterpart: str
    actor: str
    action: str
    outcome: str
    summary: str
    deltas: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SocialMemory":
        known = cls.__dataclass_fields__
        return cls(**{key: value for key, value in data.items() if key in known})


@dataclass
class RelationshipState:
    """One agent's private, directional experience of one counterpart."""

    trust: float = 0.0
    affinity: float = 0.0
    cooperation: float = 0.0
    helpfulness: float = 0.0
    hostility: float = 0.0
    interaction_count: int = 0
    positive_interactions: int = 0
    negative_interactions: int = 0
    last_interaction_day: int | None = None

    def apply(self, deltas: dict[str, float], day: int) -> dict[str, float]:
        applied: dict[str, float] = {}
        for dimension in RELATIONSHIP_DIMENSIONS:
            amount = float(deltas.get(dimension, 0.0))
            if not amount:
                continue
            old = float(getattr(self, dimension))
            new = _bounded(old + amount)
            setattr(self, dimension, new)
            if new != old:
                applied[dimension] = round(new - old, 3)
        self.interaction_count += 1
        if any(
            applied.get(name, 0.0) > 0
            for name in ("trust", "affinity", "cooperation", "helpfulness")
        ) or applied.get("hostility", 0.0) < 0:
            self.positive_interactions += 1
        if any(
            applied.get(name, 0.0) < 0
            for name in ("trust", "affinity", "cooperation", "helpfulness")
        ) or applied.get("hostility", 0.0) > 0:
            self.negative_interactions += 1
        self.last_interaction_day = day
        return applied

    def decision_value(self) -> float:
        """Positive means a safer/more useful social counterpart."""
        return round(
            self.trust * 0.3
            + self.affinity * 0.15
            + self.cooperation * 0.2
            + self.helpfulness * 0.25
            - self.hostility * 0.35,
            3,
        )

    def is_neutral(self) -> bool:
        return self.interaction_count == 0 and all(
            getattr(self, dimension) == 0.0
            for dimension in RELATIONSHIP_DIMENSIONS
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RelationshipState":
        known = cls.__dataclass_fields__
        return cls(**{key: value for key, value in data.items() if key in known})


class RelationshipManager:
    """Backward-compatible symmetric score used by pre-Prompt-5 policies."""
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
        return {
            "close friends": 6,
            "friendly": 4,
            "neutral": 2,
            "tense": 1,
            "enemies": 1,
        }.get(self.describe_relationship(agent_a, agent_b), 2)
