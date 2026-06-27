from dataclasses import dataclass, asdict


@dataclass
class TownArc:
    id: str
    name: str
    description: str
    status: str
    location_id: str | None
    involved_agents: list[str]
    tags: list[str]
    tension: int
    progress: int
    created_day: int
    updated_day: int
    resolved_day: int | None = None

    def is_active(self) -> bool:
        return self.status == "active" and self.resolved_day is None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TownArc":
        return cls(**data)