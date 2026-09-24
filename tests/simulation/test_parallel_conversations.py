import time

from src.llm.client import FakeLLMClient
from src.simulation.conversation_execution import (
    ConcurrentConversationExecutionBackend,
    ConversationRealizationJob,
)
from src.simulation.conversation_scheduler import ConversationScheduler
from src.simulation.engine import SimulationEngine
from src.simulation.social_snapshot import ConversationTickSnapshot


def build_engine(tmp_path, *, execution="serial", workers=4):
    return SimulationEngine(
        agents_path="data/agents.json", locations_path="data/locations.json",
        llm_client=FakeLLMClient(), state_path=tmp_path / "state.json",
        logs_dir=tmp_path / "logs", max_conversation_turns=1,
        conversation_execution=execution, conversation_workers=workers,
        simulation_seed=42,
    )


def test_scheduler_builds_two_locations_and_shared_snapshot(tmp_path):
    engine = build_engine(tmp_path)
    for agent, location in zip(engine.agents, ["market", "market", "library", "library"]):
        agent.location_id = location
    snapshot = ConversationTickSnapshot.capture(engine, 1, 8)
    plans = ConversationScheduler(42).schedule(snapshot)
    assert len(plans) == 2
    assert {plan.snapshot_id for plan in plans} == {snapshot.snapshot_id}
    assert len({item for plan in plans for item in plan.participant_ids}) == 4


def test_scheduler_pairs_four_or_six_at_one_location_without_double_booking(tmp_path):
    engine = build_engine(tmp_path)
    for agent in engine.agents:
        agent.location_id = "market"
    plans = ConversationScheduler(42).schedule(
        ConversationTickSnapshot.capture(engine, 1, 8)
    )
    assert len(plans) == 2
    participants = [item for plan in plans for item in plan.participant_ids]
    assert len(participants) == len(set(participants))


def test_scheduler_odd_population_leaves_one_and_ignores_agent_order(tmp_path):
    engine = build_engine(tmp_path)
    engine.agents = engine.agents[:3]
    for agent in engine.agents:
        agent.location_id = "market"
    first = ConversationScheduler(7).schedule(ConversationTickSnapshot.capture(engine, 2, 12))
    engine.agents.reverse()
    second = ConversationScheduler(7).schedule(ConversationTickSnapshot.capture(engine, 2, 12))
    assert len(first) == 1
    assert first == second


def test_concurrent_completion_order_does_not_change_returned_commit_sort_key():
    backend = ConcurrentConversationExecutionBackend(max_workers=3)
    snapshot_id = "snapshot"
    from src.simulation.conversation_scheduler import PlannedConversationSession
    from src.simulation.conversation_session import ConversationSession

    jobs = []
    for index, delay in enumerate([0.03, 0.02, 0.0]):
        plan = PlannedConversationSession(
            f"s{index}", 1, 8, "market", (str(index), str(index + 10)),
            str(index), snapshot_id, index, index,
        )
        jobs.append(ConversationRealizationJob(
            plan,
            lambda plan=plan, delay=delay: (
                time.sleep(delay) or ConversationSession(
                    plan.session_id, 1, 8, "market", [], "",
                )
            ),
        ))
    results = backend.realize(jobs)
    assert [row.plan.schedule_index for row in sorted(
        results, key=lambda row: row.plan.schedule_index
    )] == [0, 1, 2]


def test_barrier_isolation_and_serial_concurrent_equivalence(tmp_path):
    serial = build_engine(tmp_path / "serial", execution="serial")
    concurrent = build_engine(tmp_path / "concurrent", execution="concurrent")
    for engine in (serial, concurrent):
        for agent, location in zip(engine.agents, ["market", "market", "library", "library"]):
            agent.location_id = location
        engine.generate_conversations(1, 8)
    assert serial.relationships.scores == concurrent.relationships.scores
    assert serial.recent_actions == concurrent.recent_actions
    assert serial.last_social_tick["commit_order"] == concurrent.last_social_tick["commit_order"]
    assert serial.last_social_tick["scheduled_session_count"] == 2


def test_failed_worker_is_isolated():
    from src.simulation.conversation_scheduler import PlannedConversationSession
    plan0 = PlannedConversationSession("bad", 1, 8, "a", ("1", "2"), "1", "x", 0, 1)
    plan1 = PlannedConversationSession("good", 1, 8, "b", ("3", "4"), "3", "x", 1, 2)
    from src.simulation.conversation_session import ConversationSession
    results = ConcurrentConversationExecutionBackend(2).realize([
        ConversationRealizationJob(plan0, lambda: (_ for _ in ()).throw(RuntimeError("boom"))),
        ConversationRealizationJob(plan1, lambda: ConversationSession("good", 1, 8, "b", [], "")),
    ])
    assert sum(result.session is not None for result in results) == 1
    assert sum(bool(result.error) for result in results) == 1

