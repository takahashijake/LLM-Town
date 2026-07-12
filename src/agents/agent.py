from dataclasses import dataclass, field 
import random 
from src.agents.journal_entry import JournalEntry
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
    memory_archive: list[Memory] = field(default_factory=list) 
    memory_summary: str = ""
    recent_topics: list[str] = field(default_factory=list)
    relationships: dict[str, int] = field(default_factory=dict)
    current_activity: str = "idle" 
    current_activity_reason: str = ""
    current_activity_tags: list[str] = field(default_factory=list)
    daily_journals: list[JournalEntry] = field(default_factory=list)

    def upsert_daily_journal(self, journal: JournalEntry) -> None:
        for index, existing in enumerate(self.daily_journals):
            if existing.day == journal.day:
                self.daily_journals[index] = journal
                return
    
        self.daily_journals.append(journal)
        self.daily_journals.sort(key=lambda entry: entry.day)


    def get_recent_journals(
        self,
        current_day: int,
        limit: int = 3,
    ) -> list[JournalEntry]:
        eligible = [
            journal
            for journal in self.daily_journals
            if journal.day < current_day
        ]
    
        return eligible[-limit:]
    
    def summarize_archived_memories(self, max_archive_size: int = 500) -> None:
        if len(self.memory_archive) <= max_archive_size:
            return
    
        oldest_memories = self.memory_archive[:-max_archive_size]
        self.memory_archive = self.memory_archive[-max_archive_size:]
    
        conversation_count = sum(
            1 for memory in oldest_memories
            if memory.type == "conversation"
        )
    
        event_count = sum(
            1 for memory in oldest_memories
            if memory.type == "daily_event"
        )
    
        positive_count = sum(
            1 for memory in oldest_memories
            if memory.sentiment > 0
        )
    
        negative_count = sum(
            1 for memory in oldest_memories
            if memory.sentiment < 0
        )
    
        summary_piece = (
            f"Archived {len(oldest_memories)} older memories: "
            f"{conversation_count} conversations, "
            f"{event_count} town events, "
            f"{positive_count} positive interactions, "
            f"{negative_count} negative interactions."
        )
    
        if self.memory_summary:
            self.memory_summary += " " + summary_piece
        else:
            self.memory_summary = summary_piece
    
    def prune_memory(self, active_memory_limit: int = 200) -> None:
        if len(self.memory) <= active_memory_limit:
            return
    
        # Sort memories so the most useful ones survive:
        # high importance first, then stronger memories, then newer memories.
        self.memory.sort(
            key=lambda memory: (
                memory.importance,
                memory.strength,
                memory.day,
                memory.hour,
            ),
            reverse=True,
        )
    
        active_memories = self.memory[:active_memory_limit]
        archived_memories = self.memory[active_memory_limit:]
    
        self.memory = active_memories
        self.memory_archive.extend(archived_memories)
    
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

    def remember(self, memory: Memory, active_memory_limit: int = 200) -> None:
        self.memory.append(memory)
        self.prune_memory(active_memory_limit=active_memory_limit)

    def speak_to(self, other: "Agent", relationship_label: str) -> str:
        if relationship_label == "close friends":
            return "It is good to catch up with you again."

        if relationship_label == "friendly":
            return "I am glad we ran into each other today."

        if relationship_label == "tense":
            return "I am not sure we see this the same way."

        if relationship_label == "enemies":
            return "I would rather keep this conversation short."

        return random.choice([
            "There is a lot happening around town today.",
            "This place feels more active than usual.",
            "I have been trying to keep up with everything going on.",
            "It seems like everyone has something to do today.",
            "The town has felt lively lately.",
        ])

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
                memory.strength,
                memory.day,
                memory.hour,
            ),
            reverse=True,
        )
    
        selected = memories[:limit]
    
        for memory in selected:
            memory.last_accessed_day = current_day
            memory.strength = min(10, memory.strength + 1)
    
        return selected

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

    
        
        