from dataclasses import dataclass, asdict, field
import uuid


@dataclass
class Memory:
    day: int
    hour: int
    type: str
    description: str
    participants: list[str]
    location: str
    importance: int
    sentiment: int
    tags: list[str]

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    last_accessed_day: int | None = None
    strength: int = 1
    # Optional structured epistemic provenance. Legacy conversational memories
    # intentionally leave these fields empty.
    source_system: str | None = None
    source_id: str | None = None
    event_type: str | None = None
    knowledge_basis: str | None = None
    owner_id: str | None = None
    counterpart_ids: list[str] = field(default_factory=list)
    causal: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def has_authoritative_provenance(self) -> bool:
        return bool(
            self.causal and self.source_system and self.source_id
            and self.event_type and self.knowledge_basis and self.owner_id
        )
