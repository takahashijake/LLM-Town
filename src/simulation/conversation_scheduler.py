"""Deterministic, disjoint conversation scheduling."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random

from src.simulation.social_snapshot import ConversationTickSnapshot


def derive_conversation_seed(global_seed: int, day: int, hour: int,
                             session_id: str, turn_index: int = 0,
                             generation_attempt: int = 0, *,
                             schedule_index: int = 0,
                             request_kind: str = "conversation") -> int:
    value = "|".join(map(str, (
        global_seed, day, hour, session_id, schedule_index, turn_index,
        generation_attempt, request_kind,
    )))
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big")


@dataclass(frozen=True)
class PlannedConversationSession:
    session_id: str
    day: int
    hour: int
    location_id: str
    participant_ids: tuple[str, str]
    initiating_agent_id: str
    snapshot_id: str
    schedule_index: int
    request_seed: int
    simulation_seed: int = 0


class ConversationScheduler:
    """Pair every eligible resident at most once using stable local RNGs."""

    def __init__(self, seed: int = 0):
        self.seed = int(seed)

    def schedule(self, snapshot: ConversationTickSnapshot) -> list[PlannedConversationSession]:
        pending = []
        index = 0
        for location_id, participant_ids in snapshot.locations:
            ids = list(participant_ids)
            location_seed = derive_conversation_seed(
                self.seed, snapshot.day, snapshot.hour,
                f"location:{location_id}",
            )
            random.Random(location_seed).shuffle(ids)
            for offset in range(0, len(ids) - 1, 2):
                first, second = ids[offset:offset + 2]
                first_name = snapshot.agent_names[first]
                second_name = snapshot.agent_names[second]
                base = (
                    f"d{snapshot.day}-h{snapshot.hour:02d}-"
                    f"{'-'.join(location_id.lower().split())}-"
                    f"{first_name.lower()}-{second_name.lower()}"
                )
                session_id = base if offset == 0 else f"{base}-p{offset // 2}"
                pending.append(PlannedConversationSession(
                    session_id=session_id,
                    day=snapshot.day,
                    hour=snapshot.hour,
                    location_id=location_id,
                    participant_ids=(first, second),
                    initiating_agent_id=first,
                    snapshot_id=snapshot.snapshot_id,
                    schedule_index=index,
                    request_seed=derive_conversation_seed(
                        self.seed, snapshot.day, snapshot.hour, session_id,
                    ),
                    simulation_seed=self.seed,
                ))
                index += 1
        return pending
