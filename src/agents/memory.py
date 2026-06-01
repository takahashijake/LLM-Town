from dataclasses import dataclass, asdict


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

    def to_dict(self) -> dict:
        return asdict(self)