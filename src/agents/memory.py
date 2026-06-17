from dataclasses import dataclass, asdict, field
import uuid


@dataclass
class Memory:
    day: int
    hour: int
    type: str
    description: str
    participants: list[str]
    location: str
    importance: int
    sentiment: int
    tags: list[str]

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    last_accessed_day: int | None = None
    strength: int = 1

    def to_dict(self) -> dict:
        return asdict(self)