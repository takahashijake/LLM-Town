from dataclasses import dataclass


@dataclass
class Activity:
    id: str
    name: str
    location_id: str
    reason: str
    tags: list[str]
    source_commitment_id: str | None = None
    commitment_priority: float = 0.0
    commitment_decision: dict | None = None
