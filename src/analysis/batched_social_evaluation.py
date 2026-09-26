"""Model-free acceptance evaluation for batched social realization."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from src.llm.client import FakeLLMClient
from src.llm.generation import ConversationGenerationResult
from src.simulation.engine import SimulationEngine


class _EvaluationClient(FakeLLMClient):
    def __init__(self, mode: str = "waves"):
        self.mode = mode
        self.batches = []
        self.engine = None
        self.pre_barrier_scores = []

    def generate_conversation_batch(self, requests):
        self.batches.append(list(requests))
        if self.engine is not None:
            self.pre_barrier_scores.append(dict(self.engine.relationships.scores))
        if self.mode == "atomic_failure":
            raise RuntimeError("evaluation batch failure")
        results = []
        phrases = (
            "The orchard harvest is calm",
            "Library records deserve review",
            "River weather may change tomorrow",
        )
        for request in requests:
            closes = (
                self.mode == "waves" and request.schedule_index == 0
                and request.turn_index == 0
            )
            dialogue = "Goodbye" if closes else (
                f"{phrases[request.turn_index % len(phrases)]} "
                f"private-{request.schedule_index}"
            )
            results.append(ConversationGenerationResult(
                request.request_id,
                json.dumps({"dialogue": dialogue, "action": "chat"}),
            ))
        return list(reversed(results))


class _RepairEvaluationClient(_EvaluationClient):
    is_deterministic_fake = False

    def __init__(self, repair_succeeds: bool = True):
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


def _engine(root: Path, client, *, turns: int = 3, batch_size: int = 8):
    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        llm_client=client,
        state_path=root / "state.json",
        logs_dir=root / "logs",
        max_conversation_turns=turns,
        conversation_execution="batched",
        conversation_batch_size=batch_size,
        simulation_seed=42,
    )
    for agent, location in zip(
        engine.agents, ("market", "market", "library", "library"),
    ):
        agent.location_id = location
    engine.relationship_updater.get_relationship_change = lambda *args, **kwargs: 0
    return engine


def _run(engine):
    with redirect_stdout(io.StringIO()):
        engine.generate_conversations(1, 8)


def evaluate_batched_social() -> dict:
    checks = {}
    details = {}
    with TemporaryDirectory(prefix="llm-town-batched-eval-") as temporary:
        root = Path(temporary)

        wave_client = _EvaluationClient("waves")
        wave_engine = _engine(root / "waves", wave_client)
        before = dict(wave_engine.relationships.scores)
        wave_client.engine = wave_engine
        _run(wave_engine)
        wave_shapes = [[
            (row.schedule_index, row.turn_index) for row in batch
        ] for batch in wave_client.batches]
        telemetry = wave_engine.last_social_tick
        checks.update({
            "turn_waves": wave_shapes == [[(0, 0), (1, 0)], [(1, 1)], [(1, 2)]],
            "uneven_termination": telemetry["active_session_count_by_wave"] == [2, 1, 1],
            "snapshot_isolation": len({
                row.context["conversation_snapshot_id"]
                for batch in wave_client.batches for row in batch
            }) == 1,
            "pre_barrier_isolation": all(
                scores == before for scores in wave_client.pre_barrier_scores
            ),
            "ordered_commit": telemetry["commit_order"] == telemetry["schedule_order"],
            "result_identity_mapping": all(
                f"private-{row.schedule_index}" in row.context["session_transcript"][0]["dialogue"]
                for row in wave_client.batches[1]
            ),
        })
        details["waves"] = wave_shapes

        repair_client = _RepairEvaluationClient()
        repair_engine = _engine(root / "repair", repair_client, turns=1)
        _run(repair_engine)
        repair_shapes = [[row.request_kind for row in batch]
                         for batch in repair_client.batches]
        checks["selective_bounded_repair"] = repair_shapes == [
            ["primary", "primary"], ["grounding_retry"],
        ]
        details["repair_batches"] = repair_shapes

        fallback_client = _RepairEvaluationClient(repair_succeeds=False)
        fallback_engine = _engine(root / "fallback", fallback_client, turns=1)
        _run(fallback_engine)
        fallback_rows = [
            json.loads(line)
            for line in fallback_engine.logger.conversations_file.read_text().splitlines()
        ]
        checks["bounded_safe_fallback"] = (
            sum(len(batch) for batch in fallback_client.batches) == 3
            and sum(row["regenerated_for_grounding"] for row in fallback_rows) == 1
            and any(
                row["dialogue_source"] == "policy_fallback_unsupported_grounding"
                for row in fallback_rows
            )
        )

        failure_client = _EvaluationClient("atomic_failure")
        failure_engine = _engine(root / "failure", failure_client, turns=2)
        failure_before = dict(failure_engine.relationships.scores)
        failure_client.engine = failure_engine
        _run(failure_engine)
        checks["atomic_failure_isolated"] = (
            failure_client.pre_barrier_scores == [failure_before]
            and failure_engine.last_social_tick["failed_generation_requests"] == 2
        )

        reproducibility = []
        for name in ("repro-a", "repro-b"):
            client = _EvaluationClient("repro")
            engine = _engine(root / name, client, turns=2, batch_size=1)
            _run(engine)
            reproducibility.append([
                (row.request_id, row.seed, row.session_id, row.turn_index)
                for batch in client.batches for row in batch
            ])
        checks["fixed_configuration_reproducible"] = (
            reproducibility[0] == reproducibility[1]
        )

        scaling = {}
        from types import SimpleNamespace
        from src.simulation.conversation_scheduler import ConversationScheduler
        from src.simulation.social_snapshot import ConversationTickSnapshot
        for count in (4, 16, 32, 64):
            agents = [SimpleNamespace(
                id=f"a{index:03d}", name=f"Agent{index}",
                location_id=f"location-{index // 8}",
            ) for index in range(count)]
            snapshot = ConversationTickSnapshot.capture(
                SimpleNamespace(agents=agents), 2, 8,
            )
            plans = ConversationScheduler(42).schedule(snapshot)
            participants = [value for plan in plans for value in plan.participant_ids]
            scaling[str(count)] = {
                "sessions": len(plans),
                "double_bookings": len(participants) - len(set(participants)),
            }
        checks["scale_pairing"] = all(
            row["double_bookings"] == 0 for row in scaling.values()
        )

    return {
        "passed": all(checks.values()),
        "invariants": f"{sum(checks.values())}/{len(checks)} PASS",
        "checks": checks,
        "details": details,
        "scaling": scaling,
    }
