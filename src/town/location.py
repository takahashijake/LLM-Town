from dataclasses import dataclass


@dataclass
class Location:
    id: str
    name: str
    description: str