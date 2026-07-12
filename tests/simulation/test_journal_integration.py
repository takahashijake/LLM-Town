import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from src.agents.journal_entry import JournalEntry
from src.simulation.persistence import SimulationPersistence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAVE_PATH = PROJECT_ROOT / "data" / "save_state.json"


@contextmanager
def preserve_save_state():
    original_contents = (
        SAVE_PATH.read_bytes()
        if SAVE_PATH.exists()
        else None
    )

    try:
        SAVE_PATH.unlink(missing_ok=True)
        yield
    finally:
        if original_contents is None:
            SAVE_PATH.unlink(missing_ok=True)
        else:
            SAVE_PATH.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            SAVE_PATH.write_bytes(
                original_contents
            )


def run_main(
    *args: str,
    cwd: Path = PROJECT_ROOT,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "main.py",
        "--fake-llm",
        "--no-clear",
        *args,
    ]

    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def assert_command_succeeded(
    result: subprocess.CompletedProcess[str],
) -> None:
    assert result.returncode == 0, (
        "main.py failed.\n\n"
        f"Command stdout:\n{result.stdout}\n\n"
        f"Command stderr:\n{result.stderr}"
    )


def load_saved_state() -> dict:
    assert SAVE_PATH.exists(), (
        f"Expected save file at {SAVE_PATH}"
    )

    return json.loads(
        SAVE_PATH.read_text(
            encoding="utf-8"
        )
    )


def assert_journals_are_valid(
    agent_data: dict,
    expected_days: list[int],
) -> None:
    journals = agent_data.get(
        "daily_journals",
        [],
    )

    journal_days = [
        journal["day"]
        for journal in journals
    ]

    assert journal_days == expected_days

    assert len(journal_days) == len(
        set(journal_days)
    )

    assert all(
        journal["summary"].strip()
        for journal in journals
    )


@pytest.mark.integration
def test_main_entry_point_completes_three_day_fake_run():
    with preserve_save_state():
        result = run_main(
            "--days",
            "3",
            "--hours",
            "8",
            "--seed",
            "12345",
        )

        assert_command_succeeded(result)

        saved_state = load_saved_state()

        assert saved_state["current_day"] == 3
        assert saved_state["current_hour"] == 8
        assert saved_state["agents"]

        for agent_data in saved_state["agents"]:
            assert_journals_are_valid(
                agent_data,
                expected_days=[1, 2, 3],
            )


@pytest.mark.integration
def test_main_run_journals_can_be_reconstructed():
    with preserve_save_state():
        result = run_main(
            "--days",
            "3",
            "--hours",
            "8",
            "--seed",
            "12345",
        )

        assert_command_succeeded(result)

        saved_state = load_saved_state()

        agents = (
            SimulationPersistence()
            .load_agents_from_state(
                saved_state
            )
        )

        assert agents

        for agent in agents:
            assert len(
                agent.daily_journals
            ) == 3

            assert all(
                isinstance(
                    journal,
                    JournalEntry,
                )
                for journal
                in agent.daily_journals
            )

            assert [
                journal.day
                for journal
                in agent.daily_journals
            ] == [1, 2, 3]


@pytest.mark.integration
def test_main_run_uses_one_journal_per_agent_per_day():
    with preserve_save_state():
        result = run_main(
            "--days",
            "5",
            "--hours",
            "8",
            "12",
            "--seed",
            "12345",
        )

        assert_command_succeeded(result)

        saved_state = load_saved_state()

        for agent_data in saved_state["agents"]:
            assert_journals_are_valid(
                agent_data,
                expected_days=[
                    1,
                    2,
                    3,
                    4,
                    5,
                ],
            )


@pytest.mark.integration
def test_main_run_creates_agent_specific_journal_summaries():
    with preserve_save_state():
        result = run_main(
            "--days",
            "3",
            "--hours",
            "8",
            "12",
            "18",
            "22",
            "--seed",
            "12345",
        )

        assert_command_succeeded(result)

        saved_state = load_saved_state()

        for agent_data in saved_state["agents"]:
            agent_name = agent_data["name"]

            journals = agent_data[
                "daily_journals"
            ]

            assert journals

            assert all(
                agent_name in journal["summary"]
                for journal in journals
            )


@pytest.mark.integration
def test_save_resume_preserves_existing_journals_without_duplicates():
    with preserve_save_state():
        first_run = run_main(
            "--days",
            "3",
            "--hours",
            "8",
            "--seed",
            "12345",
        )

        assert_command_succeeded(first_run)

        first_state = load_saved_state()

        first_journal_days = {
            agent_data["name"]: [
                journal["day"]
                for journal
                in agent_data[
                    "daily_journals"
                ]
            ]
            for agent_data
            in first_state["agents"]
        }

        resume_run = run_main(
            "--days",
            "3",
            "--hours",
            "8",
            "--seed",
            "12345",
            "--load-state",
        )

        assert_command_succeeded(
            resume_run
        )

        resumed_state = load_saved_state()

        for agent_data in resumed_state["agents"]:
            journal_days = [
                journal["day"]
                for journal
                in agent_data[
                    "daily_journals"
                ]
            ]

            assert len(journal_days) == len(
                set(journal_days)
            )

            assert set(
                first_journal_days[
                    agent_data["name"]
                ]
            ).issubset(
                set(journal_days)
            )


@pytest.mark.slow
def test_twenty_day_fake_run_has_unique_journals_and_bounded_memory():
    with preserve_save_state():
        result = run_main(
            "--days",
            "20",
            "--hours",
            "8",
            "12",
            "18",
            "22",
            "--seed",
            "12345",
        )

        assert_command_succeeded(result)

        saved_state = load_saved_state()

        assert saved_state["current_day"] == 20
        assert saved_state["current_hour"] == 22

        for agent_data in saved_state["agents"]:
            assert_journals_are_valid(
                agent_data,
                expected_days=list(
                    range(1, 21)
                ),
            )

            active_memories = agent_data[
                "memory"
            ]

            archived_memories = agent_data[
                "memory_archive"
            ]

            # This threshold can be tightened once
            # the expected daily memory volume is
            # measured. The critical behavior is
            # that active memory does not grow with
            # every simulated day indefinitely.
            assert len(active_memories) < 250

            assert len(
                archived_memories
            ) > 0

            oldest_active_day = min(
                memory["day"]
                for memory in active_memories
            )

            assert oldest_active_day >= 13


@pytest.mark.slow
def test_twenty_day_run_can_reload_all_journals():
    with preserve_save_state():
        result = run_main(
            "--days",
            "20",
            "--hours",
            "8",
            "12",
            "18",
            "22",
            "--seed",
            "12345",
        )

        assert_command_succeeded(result)

        saved_state = load_saved_state()

        agents = (
            SimulationPersistence()
            .load_agents_from_state(
                saved_state
            )
        )

        for agent in agents:
            assert len(
                agent.daily_journals
            ) == 20

            assert [
                journal.day
                for journal
                in agent.daily_journals
            ] == list(
                range(1, 21)
            )