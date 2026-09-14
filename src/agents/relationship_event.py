from dataclasses import dataclass, asdict, field
import uuid


@dataclass
class RelationshipEvent:
    day: int
    hour: int
    agent_a: str
    agent_b: str
    action: str
    relationship_change: int
    relationship_score: int
    relationship_label: str
    description: str
    location: str
    tags: list[str]
    conversation: str = ""
    outcome: str = "observed"
    directed_deltas: dict[str, dict[str, float]] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def involves(self, agent_name: str) -> bool:
        return agent_name in [self.agent_a, self.agent_b]

    def involves_pair(self, name_a: str, name_b: str) -> bool:
        return set([self.agent_a, self.agent_b]) == set([name_a, name_b])

    def to_dict(self) -> dict:
        return asdict(self)
