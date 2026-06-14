from dataclasses import dataclass, field 
import random 

from src.agents.memory import Memory

@dataclass
class Agent:
    id: str 
    name: str 
    personality: str 
    location_id: str 
    occupation: str = "unemployed"
    goals : list[str] = field(default_factory=list)
    needs: dict[str, int] = field(default_factory=dict)
    memory: list[Memory] = field(default_factory=list)
    recent_topics: list[str] = field(default_factory=list)
    relationships: dict[str, int] = field(default_factory=dict)
    current_activity: str = "idle" 
    current_activity_reason: str = ""
    current_activity_tags: list[str] = field(default_factory=list)

    def set_activity(self, activity) -> None: 
        self.current_activity = activity.name 
        self.current_activity_reason = activity.reason 
        self.current_activity_tags = activity.tags 
        self.location_id = activity.location_id 
        
    def satisfy_need(self, need: str, amount: int) -> None:
        self.initialize_needs()

        if need not in self.needs:
            return 

        self.needs[need] = min(100, self.needs[need] + amount)
        
    def remember_topics(self, tags: list[str], limit: int = 10) -> None:
        ignored_tags = {
            "conversation", 
            "neutral", 
            "friendly", 
            "tense",
            "enemies",
            "close friends", 
            "chat",
        }

        for tag in tags:
            if tag not in ignored_tags:
                self.recent_topics.append(tag)

        self.recent_topics = self.recent_topics[-limit:]
        
    def choose_location_by_need(self, location_ids: list[str]) -> str:
        self.initialize_needs()
        primary_need = self.get_primary_need()

        need_location_preferences = {
            "social": ["cafe", "town_square", "market"],
            "wealth": ["market", "cafe", "town_square"],
            "knowledge": ["library", "town_square"],
        }

        preferred_locations = need_location_preferences.get(primary_need, location_ids)

        valid_preferred_locations = [
            preferred_location 
            for preferred_location in preferred_locations 
            if preferred_location in location_ids
        ]

        if valid_preferred_locations and random.random() < 0.75:
            return random.choice(valid_preferred_locations)

        return random.choice(location_ids)
        
    def move(self, location_ids: list[str]) -> None: 
        self.location_id = self.choose_location_by_need(location_ids)

    def remember(self, memory: Memory) -> None:
        self.memory.append(memory)

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
        
    def get_recent_memories(self, limit: int = 5): 
        return self.memory[-limit:]

    def get_memories_about(self, other_name: str, limit: int = 5):
        memories = [
            memory for memory in self.memory
            if other_name in memory.participants 
        ]

        return memories[-limit:]

    def get_relevant_memories(
        self,
        other_name: str,
        current_day: int,
        limit: int = 5,
        max_age_days: int = 7,
    ) -> list[Memory]:
        memories = [
            memory
            for memory in self.memory
            if current_day - memory.day <= max_age_days
            and (
                other_name in memory.participants
                or memory.type == "daily_event"
            )
        ]
    
        memories.sort(
            key=lambda memory: (
                memory.importance,
                memory.day,
                memory.hour,
            ),
            reverse=True,
        )
    
        return memories[:limit]

    def initialize_needs(self) -> None:
        if not self.needs:
            self.needs = {
                "social" : 50, 
                "wealth" : 50, 
                "knowledge" : 50,
            }

    def decay_needs(self) -> None: 
        self.needs["social"] = max(0, self.needs["social"] - 1) 
        self.needs["wealth"] = max(0, self.needs["wealth"] - 1) 
        self.needs["knowledge"] = max(0, self.needs["knowledge"] - 1) 

    def get_primary_need(self) -> str: 
        self.initialize_needs()
        return min(self.needs, key=self.needs.get)

    
        
        