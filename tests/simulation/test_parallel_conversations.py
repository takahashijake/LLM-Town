import time
import json

import pytest

from src.llm.client import FakeLLMClient
from src.llm.generation import ConversationGenerationResult
from src.simulation.conversation_execution import (
    BatchedConversationExecutionBackend,
    ConcurrentConversationExecutionBackend,
    ConversationRealizationJob,
)
from src.simulation.conversation_scheduler import ConversationScheduler
from src.simulation.engine import SimulationEngine
from src.simulation.social_snapshot import ConversationTickSnapshot


def build_engine(tmp_path, *, execution="serial", workers=4):
    engine = SimulationEngine(
        agents_path="data/agents.json", locations_path="data/locations.json",
        llm_client=FakeLLMClient(), state_path=tmp_path / "state.json",
        logs_dir=tmp_path / "logs", max_conversation_turns=1,
        conversation_execution=execution, conversation_workers=workers,
        conversation_batch_size=4,
        simulation_seed=42,
    )
    engine.relationship_updater.get_relationship_change = lambda *args, **kwargs: 0
    return engine


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


class WaveRecordingClient(FakeLLMClient):
    def __init__(self, *, early_schedule_index=None, reverse=False):
        self.early_schedule_index = early_schedule_index
        self.reverse = reverse
        self.batches = []

    def generate_conversation_batch(self, requests):
        self.batches.append(list(requests))
        results = []
        for request in requests:
            closes = (
                request.request_kind == "primary"
                and request.turn_index == 0
                and request.schedule_index == self.early_schedule_index
            )
            phrases = (
                "The orchard harvest looks calm",
                "Library records need careful review",
                "River weather may change tomorrow",
            )
            output = json.dumps({
                "dialogue": "Goodbye" if closes else (
                    f"{phrases[request.turn_index % len(phrases)]} "
                    f"private-{request.schedule_index}"
                ),
                "action": "storm_off" if closes else "chat",
            })
            results.append(ConversationGenerationResult(request.request_id, output))
        return list(reversed(results)) if self.reverse else results


def build_batched_engine(tmp_path, client, *, turns=3, batch_size=4):
    engine = SimulationEngine(
        agents_path="data/agents.json", locations_path="data/locations.json",
        llm_client=client, state_path=tmp_path / "state.json",
        logs_dir=tmp_path / "logs", max_conversation_turns=turns,
        conversation_execution="batched",
        conversation_batch_size=batch_size,
        simulation_seed=42,
    )
    for agent, location in zip(
        engine.agents, ["market", "market", "library", "library"],
    ):
        agent.location_id = location
    engine.relationship_updater.get_relationship_change = lambda *args, **kwargs: 0
    return engine


def test_batched_sessions_advance_by_waves_and_drop_early_termination(tmp_path):
    client = WaveRecordingClient(early_schedule_index=0)
    engine = build_batched_engine(tmp_path, client)
    engine.generate_conversations(1, 8)

    waves = [[
        (request.schedule_index, request.turn_index, request.request_kind)
        for request in batch
    ] for batch in client.batches]
    assert waves == [
        [(0, 0, "primary"), (1, 0, "primary")],
        [(1, 1, "primary")],
        [(1, 2, "primary")],
    ]
    assert engine.last_social_tick["active_session_count_by_wave"] == [2, 1, 1]
    assert engine.last_social_tick["generation_batch_count"] == 3


def test_batch_results_demultiplex_by_request_identity_and_keep_context_private(tmp_path):
    client = WaveRecordingClient(reverse=True)
    engine = build_batched_engine(tmp_path, client, turns=2)
    engine.generate_conversations(1, 8)

    first_wave = client.batches[0]
    second_wave = client.batches[1]
    assert [row.schedule_index for row in first_wave] == [0, 1]
    assert len({row.context["conversation_snapshot_id"] for row in first_wave}) == 1
    for request in second_wave:
        transcript = request.context["session_transcript"]
        assert len(transcript) == 1
        assert f"private-{request.schedule_index}" in transcript[0]["dialogue"]
        assert all(
            f"private-{other.schedule_index}" not in transcript[0]["dialogue"]
            for other in second_wave if other.session_id != request.session_id
        )
    assert engine.last_social_tick["commit_order"] == (
        engine.last_social_tick["schedule_order"]
    )


class SelectiveRepairClient(WaveRecordingClient):
    is_deterministic_fake = False

    def __init__(self, *, repair_succeeds=True):
        super().__init__()
        self.repair_succeeds = repair_succeeds

    def generate_conversation_batch(self, requests):
        self.batches.append(list(requests))
        results = []
        for request in requests:
            if request.request_kind == "primary" and request.schedule_index == 0:
                dialogue = "Remember when we played cards?"
            elif request.request_kind == "grounding_retry":
                dialogue = (
                    "What have you been working on?" if self.repair_succeeds
                    else "Remember when we opened the Willow Garden shop?"
                )
            else:
                dialogue = "The town is quiet today."
            results.append(ConversationGenerationResult(
                request.request_id,
                json.dumps({"dialogue": dialogue, "action": "chat"}),
            ))
        return results


def test_invalid_row_repairs_without_regenerating_valid_rows(tmp_path):
    client = SelectiveRepairClient()
    engine = build_batched_engine(tmp_path, client, turns=1)
    engine.generate_conversations(1, 8)
    assert [[row.request_kind for row in batch] for batch in client.batches] == [
        ["primary", "primary"], ["grounding_retry"],
    ]
    assert engine.last_social_tick["generation_request_count"] == 3
    assert engine.last_social_tick["repair_batch_count"] == 1


def test_repair_is_bounded_and_fallback_is_per_session(tmp_path):
    client = SelectiveRepairClient(repair_succeeds=False)
    engine = build_batched_engine(tmp_path, client, turns=1)
    engine.generate_conversations(1, 8)
    assert sum(len(batch) for batch in client.batches) == 3
    assert engine.last_social_tick["repair_count"] == 0
    assert engine.last_social_tick["fallback_count"] == 1
    rows = [
        json.loads(line) for line in engine.logger.conversations_file.read_text().splitlines()
    ]
    repaired = next(row for row in rows if row["regenerated_for_grounding"])
    assert repaired["dialogue_source"] == "policy_fallback_unsupported_grounding"
    assert repaired["generation_attempt_count"] == 2


class AtomicFailureClient(FakeLLMClient):
    def __init__(self):
        self.engine = None
        self.observed_scores = []

    def generate_conversation_batch(self, requests):
        self.observed_scores.append(dict(self.engine.relationships.scores))
        raise RuntimeError("atomic model failure")


def test_atomic_batch_failure_does_not_mutate_before_barrier(tmp_path):
    client = AtomicFailureClient()
    engine = build_batched_engine(tmp_path, client, turns=2)
    client.engine = engine
    before = dict(engine.relationships.scores)
    engine.generate_conversations(1, 8)
    assert client.observed_scores == [before]
    assert engine.last_social_tick["failed_generation_requests"] == 2
    assert engine.last_social_tick["generation_batch_count"] == 1


def test_batched_configuration_validation_and_unsupported_client(tmp_path):
    with pytest.raises(ValueError, match="positive integer"):
        BatchedConversationExecutionBackend(0)

    class SingleOnlyClient:
        def generate_conversation(self, context):
            return "{}"

    with pytest.raises(TypeError, match="generate_conversation_batch"):
        SimulationEngine(
            agents_path="data/agents.json", locations_path="data/locations.json",
            llm_client=SingleOnlyClient(), state_path=tmp_path / "state.json",
            logs_dir=tmp_path / "logs", conversation_execution="batched",
        )


def test_batched_fake_runs_are_reproducible_and_batch_size_is_bounded(tmp_path):
    recordings = []
    for name in ("first", "second"):
        client = WaveRecordingClient()
        engine = build_batched_engine(
            tmp_path / name, client, turns=2, batch_size=1,
        )
        engine.generate_conversations(1, 8)
        recordings.append([
            (request.request_id, request.seed, request.session_id,
             request.turn_index, request.request_kind)
            for batch in client.batches for request in batch
        ])
        assert max(engine.last_social_tick["batch_sizes"]) == 1
    assert recordings[0] == recordings[1]


def test_save_contains_no_transient_batch_state(tmp_path):
    engine = build_batched_engine(tmp_path, WaveRecordingClient(), turns=2)
    engine.generate_conversations(1, 8)
    engine.state.save(engine, 1, 8)
    saved = engine.state.path.read_text().lower()
    for transient in (
        "request_id", "generated_token_count", "tensor", "future",
        "private replica", "active_session_count_by_wave",
    ):
        assert transient not in saved
