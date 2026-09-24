"""Immutable identity and diagnostics for conversation-visible tick state."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class ConversationTickSnapshot:
    day: int
    hour: int
    snapshot_id: str
    snapshot_version: int
    participants: tuple[str, ...]
    locations: tuple[tuple[str, tuple[str, ...]], ...]
    agent_names: Mapping[str, str]

    @classmethod
    def capture(cls, engine, day: int, hour: int) -> "ConversationTickSnapshot":
        agents = sorted(engine.agents, key=lambda agent: str(agent.id))
        locations: dict[str, list[str]] = {}
        names = {}
        for agent in agents:
            agent_id = str(agent.id)
            names[agent_id] = agent.name
            locations.setdefault(str(agent.location_id), []).append(agent_id)
        frozen_locations = tuple(
            (location, tuple(sorted(ids)))
            for location, ids in sorted(locations.items())
        )
        # The identifier describes the boundary, not mutable object identity.
        payload = {
            "version": 1,
            "day": day,
            "hour": hour,
            "locations": frozen_locations,
            "agents": [(str(agent.id), agent.name) for agent in agents],
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
        return cls(
            day=day,
            hour=hour,
            snapshot_id=f"social-v1-d{day}-h{hour:02d}-{digest}",
            snapshot_version=1,
            participants=tuple(str(agent.id) for agent in agents),
            locations=frozen_locations,
            agent_names=MappingProxyType(names),
        )

