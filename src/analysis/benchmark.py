"""Programmatic simulation benchmark orchestration."""

from __future__ import annotations

import contextlib
import hashlib
import json
import platform
import random
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.analysis.quality_metrics import KPI_PATHS, aggregate_runs, analyze_run_files
from src.llm.client import FakeLLMClient, TransformersLLMClient
from src.simulation.engine import SimulationEngine


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BenchmarkConfig:
    days: int
    seeds: tuple[int, ...]
    hours: tuple[int, ...] = (8, 12, 18, 22)
    fake_llm: bool = False
    model_name: str = "Qwen/Qwen2.5-3B-Instruct"
    agents_path: str = "data/agents.json"
    locations_path: str = "data/locations.json"

    def validate(self) -> None:
        if self.days < 1:
            raise ValueError("days must be at least 1")
        if not self.seeds:
            raise ValueError("at least one seed is required")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("seeds must be unique")
        if not self.hours:
            raise ValueError("at least one hour is required")
        if list(self.hours) != sorted(set(self.hours)):
            raise ValueError("hours must be unique and in ascending order")
        if any(hour < 0 or hour > 23 for hour in self.hours):
            raise ValueError("hours must be between 0 and 23")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_sha256(project_root: Path) -> str:
    paths = [project_root / "main.py"]
    for directory in (project_root / "src", project_root / "scripts"):
        paths.extend(directory.rglob("*.py"))

    digest = hashlib.sha256()
    for path in sorted(path for path in paths if path.is_file()):
        digest.update(str(path.relative_to(project_root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _git_metadata(project_root: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
        )
        return result.stdout.rstrip() if result.returncode == 0 else "unknown"

    status_lines = [
        line
        for line in git("status", "--porcelain").splitlines()
        if "__pycache__" not in line and not line.rstrip().endswith(".pyc")
    ]
    return {
        "commit": git("rev-parse", "HEAD"),
        "commit_short": git("rev-parse", "--short", "HEAD"),
        "dirty": bool(status_lines),
        "dirty_paths": [line[3:] for line in status_lines],
        "source_sha256": _source_sha256(project_root),
    }


def _build_llm(config: BenchmarkConfig):
    if config.fake_llm:
        return FakeLLMClient()
    return TransformersLLMClient(model_name=config.model_name)


def _seed_random_generators(seed: int, *, fake_llm: bool) -> None:
    random.seed(seed)
    if fake_llm:
        return

    import torch

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _run_one(
    config: BenchmarkConfig,
    seed: int,
    run_dir: Path,
    project_root: Path,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=False)
    logs_dir = run_dir / "logs"
    state_path = run_dir / "save_state.json"
    simulation_output_path = run_dir / "simulation.log"

    _seed_random_generators(seed, fake_llm=config.fake_llm)
    started = time.perf_counter()
    with simulation_output_path.open("w", encoding="utf-8") as output:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            llm = _build_llm(config)
            engine = SimulationEngine(
                agents_path=str((project_root / config.agents_path).resolve()),
                locations_path=str((project_root / config.locations_path).resolve()),
                load_state=False,
                llm_client=llm,
                state_path=state_path,
                logs_dir=logs_dir,
            )
            engine.run(days=config.days, hours=list(config.hours))
    elapsed = time.perf_counter() - started

    conversations_path = logs_dir / "conversations" / "conversations.jsonl"
    events_path = logs_dir / "events" / "events.jsonl"
    arc_changes_path = logs_dir / "town_arc_changes.jsonl"
    metrics = analyze_run_files(
        conversations_path=conversations_path,
        state_path=state_path,
        events_path=events_path,
        arc_changes_path=arc_changes_path,
    )

    return {
        "seed": seed,
        "elapsed_seconds": round(elapsed, 6),
        "artifacts": {
            "run_directory": run_dir.name,
            "state": f"{run_dir.name}/save_state.json",
            "simulation_output": f"{run_dir.name}/simulation.log",
            "conversations": (
                f"{run_dir.name}/logs/conversations/conversations.jsonl"
            ),
            "events": f"{run_dir.name}/logs/events/events.jsonl",
            "town_arc_changes": f"{run_dir.name}/logs/town_arc_changes.jsonl",
        },
        "metrics": metrics,
    }


def run_benchmark(
    config: BenchmarkConfig,
    output_dir: str | Path,
    *,
    project_root: str | Path = ".",
) -> dict[str, Any]:
    """Run an isolated benchmark suite and write ``benchmark.json``.

    ``output_dir`` must not already exist. This prevents an experiment from
    silently mixing with or overwriting a previous one.
    """

    config.validate()
    project_root = Path(project_root).resolve()
    output_dir = Path(output_dir).resolve()

    agents_path = (project_root / config.agents_path).resolve()
    locations_path = (project_root / config.locations_path).resolve()
    if not agents_path.is_file():
        raise FileNotFoundError(f"Agents file does not exist: {agents_path}")
    if not locations_path.is_file():
        raise FileNotFoundError(f"Locations file does not exist: {locations_path}")
    output_dir.mkdir(parents=True, exist_ok=False)

    revision = _git_metadata(project_root)
    runs = []
    for seed in config.seeds:
        runs.append(
            _run_one(
                config=config,
                seed=seed,
                run_dir=output_dir / f"seed-{seed}",
                project_root=project_root,
            )
        )

    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": "llm-town-simulation-benchmark",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "revision": revision,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "configuration": {
            **asdict(config),
            "seeds": list(config.seeds),
            "hours": list(config.hours),
            "agents_sha256": _sha256(agents_path),
            "locations_sha256": _sha256(locations_path),
        },
        "runs": runs,
        "aggregate": aggregate_runs(runs),
    }
    (output_dir / "benchmark.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return document


def load_benchmark(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_dir():
        path = path / "benchmark.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported benchmark schema: {document.get('schema_version')!r}"
        )
    return document


def compare_benchmarks(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """Compare two suites, emphasizing explicit quality-check transitions."""

    comparable_fields = (
        "days",
        "hours",
        "seeds",
        "fake_llm",
        "model_name",
        "agents_sha256",
        "locations_sha256",
    )
    mismatches = {
        field: {
            "baseline": baseline["configuration"].get(field),
            "current": current["configuration"].get(field),
        }
        for field in comparable_fields
        if baseline["configuration"].get(field)
        != current["configuration"].get(field)
    }

    deltas = {}
    for path in KPI_PATHS:
        old = baseline["aggregate"]["kpis"][path]["mean"]
        new = current["aggregate"]["kpis"][path]["mean"]
        deltas[path] = {
            "baseline_mean": old,
            "current_mean": new,
            "absolute_change": new - old,
        }

    improved_checks = []
    regressed_checks = []
    unchanged_checks = []
    all_checks = sorted(
        set(baseline["aggregate"]["quality_checks"])
        | set(current["aggregate"]["quality_checks"])
    )
    for name in all_checks:
        old = baseline["aggregate"]["quality_checks"].get(name, {}).get(
            "pass_rate", 0.0
        )
        new = current["aggregate"]["quality_checks"].get(name, {}).get(
            "pass_rate", 0.0
        )
        if new > old:
            improved_checks.append(name)
        elif new < old:
            regressed_checks.append(name)
        else:
            unchanged_checks.append(name)

    changed_kpis = [
        path
        for path, values in deltas.items()
        if abs(values["absolute_change"]) > 1e-12
    ]

    if mismatches:
        verdict = "incomparable"
    elif improved_checks and not regressed_checks:
        verdict = "better"
    elif regressed_checks and not improved_checks:
        verdict = "worse"
    elif improved_checks or regressed_checks:
        verdict = "mixed"
    elif changed_kpis:
        verdict = "different"
    else:
        verdict = "unchanged"

    return {
        "verdict": verdict,
        "basis": (
            "Verdict uses per-check pass-rate transitions across identical seeds. "
            "KPI deltas without check transitions are classified as different."
        ),
        "configuration_mismatches": mismatches,
        "improved_checks": improved_checks,
        "regressed_checks": regressed_checks,
        "unchanged_checks": unchanged_checks,
        "changed_kpis": changed_kpis,
        "kpi_deltas": deltas,
    }


def default_output_dir(project_root: str | Path = ".") -> Path:
    project_root = Path(project_root).resolve()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return project_root / "outputs" / "benchmarks" / f"benchmark-{timestamp}"


def print_summary(document: dict[str, Any], output_dir: str | Path) -> None:
    print("LLM-Town simulation benchmark")
    print("seed  conversations  repetition  event use  intent/action  checks")
    for run in document["runs"]:
        metrics = run["metrics"]
        quality = metrics["quality"]
        print(
            f"{run['seed']:>4}  "
            f"{metrics['conversations']['total']:>13}  "
            f"{metrics['conversations']['repetition_rate']:>10.1%}  "
            f"{metrics['conversations']['daily_event_rate']:>9.1%}  "
            f"{metrics['intent_followthrough']['action_compatibility_rate']:>13.1%}  "
            f"{quality['passed']}/{quality['applicable']}"
        )
    print(f"\nStructured result: {Path(output_dir).resolve() / 'benchmark.json'}")


def write_comparison(
    current: dict[str, Any],
    baseline_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    comparison = compare_benchmarks(current, load_benchmark(baseline_path))
    path = Path(output_dir).resolve() / "comparison.json"
    path.write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Comparison verdict: {comparison['verdict']}")
    print(f"Comparison result: {path}")
    return comparison
