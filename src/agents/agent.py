from dataclasses import dataclass, field 
import random 

from src.agents.memory import Memory

@dataclass
class Agent:
    id: str 
    name: str 
    personality: str 
    location_id: str 
    memory: list[str] = field(default_factory=list)
    relationships: dict[str, int] = field(default_factory=dict)

    def move(self, location_ids: list[str]) -> None: 
        self.location_id = random.choice(location_ids)

    def remember(self, event: str) -> None: 
        self.memory.append(event)

    def speak_to(self, other: "Agent", relationship_label: str) -> str:
        if relationship_label == "close friends":
            return (
                f"{self.name} happily catches up with {other.name}. "
                f"They seem very comfortable around each other."
            )
    
        if relationship_label == "friendly":
            return (
                f"{self.name} warmly chats with {other.name}. "
                f"The conversation feels easy and positive."
            )
    
        if relationship_label == "tense":
            return (
                f"{self.name} has an awkward conversation with {other.name}. "
                f"There is some tension between them."
            )
    
        if relationship_label == "enemies":
            return (
                f"{self.name} argues sharply with {other.name}. "
                f"They clearly do not trust each other."
            )
    
        return (
            f"{self.name} talks with {other.name}. "
            f"{self.name} is feeling {self.personality}."
        )

    def update_relationship(self, other_name: str, score: int) -> None:
        self.relationships[other_name] = score
    