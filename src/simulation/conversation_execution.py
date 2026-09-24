"""Realization execution backends; neither backend commits world effects."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Protocol

from src.simulation.conversation_scheduler import PlannedConversationSession
from src.simulation.conversation_session import ConversationSession


@dataclass(frozen=True)
class ConversationRealizationJob:
    plan: PlannedConversationSession
    realize: Callable[[], ConversationSession]


@dataclass(frozen=True)
class ConversationSessionResult:
    plan: PlannedConversationSession
    session: ConversationSession | None
    error: str = ""


class ConversationExecutionBackend(Protocol):
    name: str

    def realize(self, jobs: list[ConversationRealizationJob]) -> list[ConversationSessionResult]: ...


def _run_job(job: ConversationRealizationJob) -> ConversationSessionResult:
    try:
        return ConversationSessionResult(job.plan, job.realize())
    except Exception as error:  # A worker failure is data, never partial commit.
        return ConversationSessionResult(
            job.plan, None, f"{type(error).__name__}: {error}",
        )


class SerialConversationExecutionBackend:
    name = "serial"

    def realize(self, jobs: list[ConversationRealizationJob]) -> list[ConversationSessionResult]:
        return [_run_job(job) for job in jobs]


class ConcurrentConversationExecutionBackend:
    name = "concurrent"

    def __init__(self, max_workers: int = 4):
        self.max_workers = max(1, int(max_workers))

    def realize(self, jobs: list[ConversationRealizationJob]) -> list[ConversationSessionResult]:
        if not jobs:
            return []
        results = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(jobs))) as pool:
            futures = {pool.submit(_run_job, job): job.plan for job in jobs}
            for future in as_completed(futures):
                results.append(future.result())
        return results
