from types import SimpleNamespace

from src.simulation.simulation_loop import SimulationLoop


class RecordingJournalSystem:
    def __init__(self, calls):
        self.calls = calls

    def create_journals_for_day(self, **kwargs):
        self.calls.append(
            (
                "create_journals",
                kwargs["day"],
            )
        )

    def compress_old_memories(
        self,
        agent,
        current_day,
        raw_memory_retention_days,
    ):
        self.calls.append(
            (
                "compress",
                agent.name,
                current_day,
                raw_memory_retention_days,
            )
        )

        return 0


class RecordingState:
    def __init__(self, calls):
        self.calls = calls

    def save(
        self,
        engine,
        day,
        hour,
    ):
        self.calls.append(
            (
                "save",
                day,
                hour,
            )
        )


def build_engine(calls):
    return SimpleNamespace(
        agents=[
            SimpleNamespace(name="Maya"),
            SimpleNamespace(name="Ethan"),
        ],
        activity_records=[],
        relationship_events=[],
        intent_history=[],
        town_arc_change_records=[],
        journal_system=RecordingJournalSystem(
            calls
        ),
        state=RecordingState(calls),
    )


def test_finish_day_creates_journals_before_compression_and_save():
    calls = []
    engine = build_engine(calls)

    SimulationLoop().finish_day(
        engine=engine,
        day=3,
        final_hour=22,
    )

    assert calls == [
        (
            "create_journals",
            3,
        ),
        (
            "compress",
            "Maya",
            3,
            7,
        ),
        (
            "compress",
            "Ethan",
            3,
            7,
        ),
        (
            "save",
            3,
            22,
        ),
    ]


def test_finish_day_saves_with_supplied_final_hour():
    calls = []
    engine = build_engine(calls)

    SimulationLoop().finish_day(
        engine=engine,
        day=4,
        final_hour=18,
    )

    assert calls[-1] == (
        "save",
        4,
        18,
    )