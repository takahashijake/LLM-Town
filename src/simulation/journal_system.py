from collections import Counter 
from src.agents.journal_entry import JournalEntry 

class JournalSystem:
    def create_daily_journal(
        self,
        agent,
        day: int,
        activity_records: list[dict],
        relationship_events: list,
        intent_history: list,
        town_arc_change_records: list[dict],
    ) -> JournalEntry:
        day_memories = [
            memory
            for memory in agent.memory
            if memory.day == day
        ]
        
        day_activities = [
            record
            for record in activity_records
            if record.get("day") == day
            and record.get("agent") == agent.name
        ]
        
        day_relationship_events = [
            event
            for event in relationship_events
            if event.day == day
            and agent.name in {
                event.agent_a,
                event.agent_b,
            }
        ]
        
        day_intents = [
            intent
            for intent in intent_history
            if intent.agent_name == agent.name
            and intent.completed_day == day
        ]
        
        day_arc_changes = [
            record
            for record in town_arc_change_records
            if record.get("day") == day
            and agent.name in {
                record.get("speaker"),
                record.get("listener"),
            }
        ]

        people_counter = Counter()

        for memory in day_memories:
            for participant in memory.participants:
                if participant != agent.name:
                    people_counter[participant] += 1
        
        important_people = [
            person
            for person, _count in people_counter.most_common(5)
        ]

        important_locations = list(dict.fromkeys(
            [
                record["location"]
                for record in day_activities
                if record.get("location")
            ]
            + [
                memory.location
                for memory in day_memories
                if memory.location
            ]
        ))[:5]

        important_events = [
            memory.description
            for memory in day_memories
            if memory.type in {
                "daily_event",
                "town_arc",
                "town_arc_participation",
            }
        ][:5]

        relationship_changes: dict[str, int] = {}

        for event in day_relationship_events:
            other_name = (
                event.agent_b
                if event.agent_a == agent.name
                else event.agent_a
            )
        
            relationship_changes[other_name] = (
                relationship_changes.get(other_name, 0)
                + event.relationship_change
            )

        completed_intents = [
            (
                f"{intent.intent_type}: {intent.status}. "
                f"{intent.completion_reason}"
            )
            for intent in day_intents
        ]

        ignored_tags = {
            "conversation",
            "chat",
            "neutral",
            "friendly",
            "tense",
            "enemies",
            "close friends",
        }
        
        journal_tags = list(dict.fromkeys(
            tag
            for memory in day_memories
            for tag in memory.tags
            if tag not in ignored_tags
        ))[:10]
        
        unresolved_topics = journal_tags[:5]

        summary_parts = []

        activity_names = list(dict.fromkeys(
            record["activity_name"]
            for record in day_activities
            if record.get("activity_name")
        ))
        
        if activity_names:
            summary_parts.append(
                f"{agent.name} spent the day "
                + ", then ".join(activity_names[:3])
                + "."
            )
        
        if important_people:
            summary_parts.append(
                "Important interactions involved "
                + ", ".join(important_people)
                + "."
            )
        
        for other_name, change in relationship_changes.items():
            if change > 0:
                direction = "improved"
            elif change < 0:
                direction = "worsened"
            else:
                direction = "did not substantially change"
        
            summary_parts.append(
                f"The relationship with {other_name} {direction}."
            )
        
        if completed_intents:
            summary_parts.append(
                "Intent outcomes: "
                + " ".join(completed_intents[:2])
            )
        
        arc_names = list(dict.fromkeys(
            record["arc_name"]
            for record in day_arc_changes
            if record.get("arc_name")
        ))
        
        if arc_names:
            summary_parts.append(
                "The agent participated in "
                + ", ".join(arc_names)
                + "."
            )
        
        if not summary_parts:
            summary_parts.append(
                f"{agent.name} had a quiet day with no major recorded events."
        )

        return JournalEntry(
            day=day,
            summary=" ".join(summary_parts),
            important_people=important_people,
            important_locations=important_locations,
            important_events=important_events,
            relationship_changes=relationship_changes,
            completed_intents=completed_intents,
            unresolved_topics=unresolved_topics,
            tags=journal_tags,
        )
    
    def create_journals_for_day(
        self,
        agents: list,
        day: int,
        activity_records: list[dict],
        relationship_events: list,
        intent_history: list,
        town_arc_change_records: list[dict],
    ) -> None:
        for agent in agents:
            journal = self.create_daily_journal(
                agent=agent,
                day=day,
                activity_records=activity_records,
                relationship_events=relationship_events,
                intent_history=intent_history,
                town_arc_change_records=town_arc_change_records,
            )

            agent.upsert_daily_journal(journal)

    def compress_old_memories(
        self,
        agent,
        current_day: int,
        raw_memory_retention_days: int = 7,
    ) -> int:
        cutoff_day = current_day - raw_memory_retention_days
    
        retained_memories = []
        archived_memories = []
    
        for memory in agent.memory:
            if memory.day <= cutoff_day:
                archived_memories.append(memory)
            else:
                retained_memories.append(memory)
    
        existing_archive_ids = {
            memory.id
            for memory in agent.memory_archive
        }
    
        new_archived_memories = [
            memory
            for memory in archived_memories
            if memory.id not in existing_archive_ids
        ]
    
        agent.memory = retained_memories
        agent.memory_archive.extend(new_archived_memories)
        # Compression runs after the tick-level maintenance pass. Enforce the
        # durable archive bound here too so end-of-day saves cannot exceed it.
        agent.summarize_archived_memories(max_archive_size=500)
    
        return len(new_archived_memories)
