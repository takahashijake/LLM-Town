from dataclasses import asdict, dataclass, field


@dataclass
class JournalEntry:
    day: int
    summary: str
    important_people: list[str] = field(default_factory=list)
    important_locations: list[str] = field(default_factory=list)
    important_events: list[str] = field(default_factory=list)
    relationship_changes: dict[str, int] = field(default_factory=dict)
    completed_intents: list[str] = field(default_factory=list)
    unresolved_topics: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)