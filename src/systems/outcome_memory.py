"""Projection of authoritative outcomes into bounded private knowledge.

This module never changes world state. Callers must first complete an
authoritative transition and explicitly identify each legitimate recipient.
"""

from dataclasses import dataclass

from src.agents.memory import Memory


KNOWLEDGE_BASES = {
    "self_action", "participant", "counterparty", "direct_observer",
    "victim_discovery", "public_event", "explicit_transmission",
}


@dataclass(frozen=True)
class KnowledgeRecipient:
    owner_id: str
    knowledge_basis: str
    description: str
    counterpart_ids: tuple[str, ...] = ()
    sentiment: int = 0
    importance: int = 4
    location: str | None = None


class OutcomeMemorySystem:
    """Idempotent, owner-scoped adapter from truth to private memory."""

    def __init__(self, agents):
        self.agents = {agent.id: agent for agent in agents}
        self.authorities = {}

    def bind_authorities(self, **authorities) -> None:
        """Attach read-only source registries after engine construction."""
        self.authorities = authorities

    def source_exists(self, memory: Memory) -> bool:
        authority = self.authorities.get(memory.source_system)
        if authority is None:
            return False
        if memory.source_system == "commitments":
            records = authority.commitments
        elif memory.source_system == "plans":
            records = authority.plans
        elif memory.source_system == "crime":
            records = [*authority.incidents, *authority.evidence]
        elif memory.source_system == "justice":
            records = [*authority.adjudications, *authority.restitutions]
        elif memory.source_system == "materials":
            records = authority.exchanges
        else:
            return False
        return any(record.id == memory.source_id for record in records)

    @staticmethod
    def memory_id(owner_id: str, source_system: str, source_id: str,
                  event_type: str) -> str:
        return f"memory:{owner_id}:{source_system}:{source_id}:{event_type}"

    def project(self, *, source_system: str, source_id: str, event_type: str,
                day: int, hour: int | None, recipients: list[KnowledgeRecipient]) -> list[Memory]:
        if not source_system or not source_id or not event_type:
            raise ValueError("causal memory requires complete source provenance")
        created = []
        for recipient in recipients:
            if recipient.knowledge_basis not in KNOWLEDGE_BASES:
                raise ValueError("unsupported causal-memory knowledge basis")
            owner = self.agents.get(recipient.owner_id)
            if owner is None:
                # Authority may deliberately model an absent participant. No
                # epistemic state exists to receive the projection.
                continue
            memory_id = self.memory_id(
                owner.id, source_system, source_id, event_type
            )
            if any(item.id == memory_id for item in owner.memory + owner.memory_archive):
                continue
            counterparts = [
                self.agents[item].name for item in recipient.counterpart_ids
                if item in self.agents and item != owner.id
            ]
            memory = Memory(
                id=memory_id, day=int(day), hour=int(hour or 0),
                type=event_type, event_type=event_type,
                description=recipient.description,
                participants=[owner.name, *counterparts],
                location=recipient.location or owner.location_id,
                importance=max(1, min(5, int(recipient.importance))),
                sentiment=max(-2, min(2, int(recipient.sentiment))),
                tags=["causal_outcome", event_type,
                      f"source_system:{source_system}", f"source_id:{source_id}"],
                source_system=source_system, source_id=source_id,
                knowledge_basis=recipient.knowledge_basis, owner_id=owner.id,
                counterpart_ids=list(recipient.counterpart_ids), causal=True,
            )
            owner.remember(memory)
            created.append(memory)
        return created

    def validate(self) -> dict[str, bool]:
        all_memories = [
            memory for agent in self.agents.values()
            for memory in agent.memory + agent.memory_archive if memory.causal
        ]
        ids = [memory.id for memory in all_memories]
        return {
            "stable_causal_ids": all(
                memory.id == self.memory_id(
                    memory.owner_id, memory.source_system,
                    memory.source_id, memory.event_type,
                ) for memory in all_memories if memory.has_authoritative_provenance
            ),
            "unique_causal_memory_per_owner_source_event": len(ids) == len(set(ids)),
            "complete_causal_provenance": all(
                memory.has_authoritative_provenance for memory in all_memories
            ),
            "known_owners": all(memory.owner_id in self.agents for memory in all_memories),
            "known_knowledge_bases": all(
                memory.knowledge_basis in KNOWLEDGE_BASES for memory in all_memories
            ),
            "causal_sources_exist": all(self.source_exists(memory) for memory in all_memories),
        }
