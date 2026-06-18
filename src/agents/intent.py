from dataclasses import dataclass, asdict, field
import uuid


@dataclass
class AgentIntent:
    agent_name: str
    intent_type: str
    description: str
    created_day: int
    expires_day: int
    priority: int
    target_agent: str | None = None
    target_location: str | None = None
    status: str = "active"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def is_expired(self, current_day: int) -> bool:
        return current_day > self.expires_day

    def involves_agent(self, agent_name: str) -> bool:
        return self.target_agent == agent_name

    def to_dict(self) -> dict:
        return asdict(self)