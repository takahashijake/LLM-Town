from dataclasses import dataclass, field 
import random 
from src.agents.journal_entry import JournalEntry
from src.agents.goal import Goal
from src.agents.memory import Memory
from src.agents.relationships import RelationshipState, SocialMemory
from src.systems.reputation import ReputationBelief

@dataclass
class Agent:
    id: str 
    name: str 
    personality: str 
    location_id: str 
    occupation: str = "unemployed"
    goals: list[Goal | str] = field(default_factory=list)
    needs: dict[str, int] = field(default_factory=dict)
    memory: list[Memory] = field(default_factory=list)
    memory_archive: list[Memory] = field(default_factory=list) 
    memory_summary: str = ""
    recent_topics: list[str] = field(default_factory=list)
    relationships: dict[str, int] = field(default_factory=dict)
    relationship_states: dict[str, RelationshipState] = field(default_factory=dict)
    social_memories: dict[str, list[SocialMemory]] = field(default_factory=dict)
    reputation_beliefs: dict[str, dict[str, ReputationBelief]] = field(
        default_factory=dict
    )
    current_activity: str = "idle" 
    current_activity_reason: str = ""
    current_activity_tags: list[str] = field(default_factory=list)
    daily_journals: list[JournalEntry] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.goals = [
            goal if isinstance(goal, Goal) else (
                Goal.from_dict(goal) if isinstance(goal, dict)
                else Goal.from_legacy(self.name, str(goal), index)
            )
            for index, goal in enumerate(self.goals)
        ]
        self.relationship_states = {
            counterpart: (
                state if isinstance(state, RelationshipState)
                else RelationshipState.from_dict(state)
            )
            for counterpart, state in self.relationship_states.items()
        }
        self.social_memories = {
            counterpart: [
                memory if isinstance(memory, SocialMemory)
                else SocialMemory.from_dict(memory)
                for memory in memories
            ]
            for counterpart, memories in self.social_memories.items()
        }

    def get_active_goals(self) -> list[Goal]:
        return [goal for goal in self.goals if isinstance(goal, Goal) and goal.is_active()]

    def get_goal(self, goal_id: str | None) -> Goal | None:
        return next(
            (goal for goal in self.goals if isinstance(goal, Goal) and goal.id == goal_id),
            None,
        )

    def goal_descriptions(self) -> list[str]:
        return [str(goal) for goal in self.goals]

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

        # Reserve one fifth of the fixed archive for high-value causal history;
        # fill the rest by recency. The union is deterministic and remains hard
        # bounded even over multi-thousand-day runs.
        salient_limit = max(1, max_archive_size // 5)
        ordered = sorted(
            (memory for memory in self.memory_archive
             if memory.causal or memory.importance >= 4),
            key=lambda memory: (
                bool(memory.causal), memory.importance, memory.strength,
                memory.day, memory.hour, memory.id,
            ), reverse=True,
        )
        salient = ordered[:salient_limit]
        salient_ids = {memory.id for memory in salient}
        recent = sorted(
            (memory for memory in self.memory_archive if memory.id not in salient_ids),
            key=lambda memory: (memory.day, memory.hour, memory.id), reverse=True,
        )[:max_archive_size - len(salient)]
        retained_ids = {memory.id for memory in salient + recent}
        oldest_memories = [
            memory for memory in self.memory_archive if memory.id not in retained_ids
        ]
        self.memory_archive = sorted(
            salient + recent, key=lambda memory: (memory.day, memory.hour, memory.id)
        )
    
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
        # This text is itself a lossy synopsis, not another unbounded archive.
        # Keep the newest complete summaries within a fixed storage budget.
        if len(self.memory_summary) > 2000:
            pieces = self.memory_summary.split("Archived ")
            kept = []
            for piece in reversed([item for item in pieces if item]):
                candidate = " ".join(reversed(kept + ["Archived " + piece]))
                if len(candidate) > 2000:
                    break
                kept.append("Archived " + piece)
            self.memory_summary = " ".join(reversed(kept))
    
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
        # Keep the archive's hard bound true at the mutation boundary. The
        # journal pass also enforces this, but callers may remember many items
        # between journal runs (or save immediately after remembering one).
        self.summarize_archived_memories()
    
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

    def get_relationship_state(self, other_name: str) -> RelationshipState:
        """Return a neutral private state for an unseen counterpart."""
        if other_name not in self.relationship_states:
            self.relationship_states[other_name] = RelationshipState()
        return self.relationship_states[other_name]

    def remember_social_episode(
        self,
        memory: SocialMemory,
        per_counterpart_limit: int = 8,
    ) -> None:
        episodes = self.social_memories.setdefault(memory.counterpart, [])
        episodes.append(memory)
        self.social_memories[memory.counterpart] = episodes[-per_counterpart_limit:]

    def get_social_memories(
        self,
        other_name: str,
        limit: int = 3,
    ) -> list[SocialMemory]:
        return self.social_memories.get(other_name, [])[-limit:][::-1]

    def get_reputation_belief(
        self,
        target_agent: str,
        dimension: str,
    ) -> ReputationBelief | None:
        return self.reputation_beliefs.get(target_agent, {}).get(dimension)
        
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
