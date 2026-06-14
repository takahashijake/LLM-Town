from dataclasses import dataclass


@dataclass
class Activity:
    id: str
    name: str
    location_id: str
    reason: str
    tags: list[str]