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
        ...

    def create_journals_for_day(
        self,
        agents: list,
        day: int,
        activity_records: list[dict],
        relationship_events: list,
        intent_history: list,
        town_arc_change_records: list[dict],
    ) -> None:
        ...

    def compress_old_memories(
        self,
        agent,
        current_day: int,
        raw_memory_retention_days: int = 7,
    ) -> int:
        ...