from dataclasses import dataclass, field 
import random 

@dataclass
class Agent:
    id: str 
    name: str 
    personality: str 
    location_id: str 
    memory: list[str] = field(default_factory=list)

    def move(self, location_ids: list[str]) -> None: 
        self.location_id = random.choice(location_ids)

    def remember(self, event: str) -> None: 
        self.memory.append(event)

    def speak_to(self, other: "Agent") -> str:
        return f"{self.name} talks with {other.name}. {self.name} is feeling {self.personality}."
    