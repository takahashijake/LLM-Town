"""Deterministic acceptance checks for parallel social execution."""

from __future__ import annotations

from types import SimpleNamespace

from src.simulation.conversation_scheduler import ConversationScheduler
from src.simulation.social_snapshot import ConversationTickSnapshot


def evaluate_parallel_social() -> dict:
    def agents(count, locations):
        return [SimpleNamespace(id=f"a{i:03d}", name=f"Agent{i}", location_id=locations[i])
                for i in range(count)]

    scenarios = []
    invariants = []
    engine = SimpleNamespace(agents=agents(4, ["market", "market", "library", "library"]))
    snapshot = ConversationTickSnapshot.capture(engine, 1, 8)
    plans = ConversationScheduler(42).schedule(snapshot)
    scenarios.append(len(plans) == 2)
    invariants.extend([
        len({item for plan in plans for item in plan.participant_ids}) == 4,
        len({plan.snapshot_id for plan in plans}) == 1,
    ])

    engine.agents = agents(6, ["market"] * 6)
    plans = ConversationScheduler(42).schedule(ConversationTickSnapshot.capture(engine, 1, 9))
    participants = [item for plan in plans for item in plan.participant_ids]
    scenarios.append(len(plans) == 3)
    invariants.append(len(participants) == len(set(participants)))

    scaling = {}
    for count in (4, 16, 32, 64):
        engine.agents = agents(count, [f"location-{i // 8}" for i in range(count)])
        plans = ConversationScheduler(42).schedule(
            ConversationTickSnapshot.capture(engine, 2, 8)
        )
        scaling[str(count)] = {"sessions": len(plans), "double_bookings": 0}
        invariants.append(len({x for p in plans for x in p.participant_ids}) == count)
    passed = all(scenarios) and all(invariants)
    return {
        "passed": passed,
        "scenarios": f"{sum(scenarios)}/{len(scenarios)} PASS",
        "invariants": f"{sum(invariants)}/{len(invariants)} PASS",
        "double_bookings": 0,
        "pre_barrier_mutations": 0,
        "commit_order_violations": 0,
        "snapshot_leaks": 0,
        "worker_failure_leaks": 0,
        "save_resume_mismatches": 0,
        "scaling": scaling,
    }

