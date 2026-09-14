import json
from copy import deepcopy
from pathlib import Path

import pytest

from src.analysis.benchmark import (
    BenchmarkConfig,
    compare_benchmarks,
    run_benchmark,
)
from src.analysis.quality_metrics import KPI_PATHS


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_benchmark_runs_are_isolated_and_reproducible(tmp_path, monkeypatch):
    ordinary_root = tmp_path / "ordinary"
    ordinary_state = ordinary_root / "data" / "save_state.json"
    ordinary_log = ordinary_root / "logs" / "conversations" / "conversations.jsonl"
    ordinary_state.parent.mkdir(parents=True)
    ordinary_log.parent.mkdir(parents=True)
    ordinary_state.write_text("ordinary state", encoding="utf-8")
    ordinary_log.write_text("ordinary log", encoding="utf-8")
    monkeypatch.chdir(ordinary_root)

    config = BenchmarkConfig(
        days=2,
        seeds=(2,),
        hours=(8, 12),
        fake_llm=True,
    )
    first = run_benchmark(config, tmp_path / "suite-one", project_root=PROJECT_ROOT)
    second = run_benchmark(config, tmp_path / "suite-two", project_root=PROJECT_ROOT)

    assert first["runs"][0]["metrics"] == second["runs"][0]["metrics"]
    assert ordinary_state.read_text(encoding="utf-8") == "ordinary state"
    assert ordinary_log.read_text(encoding="utf-8") == "ordinary log"
    assert not (ordinary_root / "logs" / "town_arc_changes.jsonl").exists()

    run_dir = tmp_path / "suite-one" / "seed-2"
    assert (run_dir / "save_state.json").is_file()
    assert (run_dir / "simulation.log").is_file()
    assert (run_dir / "logs" / "events" / "events.jsonl").is_file()
    assert (run_dir / "logs" / "conversations" / "conversations.jsonl").is_file()
    assert (run_dir / "logs" / "town_arc_changes.jsonl").is_file()

    saved = json.loads((tmp_path / "suite-one" / "benchmark.json").read_text())
    assert saved["schema_version"] == 1
    assert saved["configuration"]["seeds"] == [2]
    assert saved["aggregate"]["run_count"] == 1


def test_benchmark_refuses_to_reuse_an_output_directory(tmp_path):
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    config = BenchmarkConfig(days=1, seeds=(1,), hours=(8,), fake_llm=True)

    with pytest.raises(FileExistsError):
        run_benchmark(config, output_dir, project_root=PROJECT_ROOT)


def test_comparison_distinguishes_quality_improvement_from_metric_change():
    baseline = {
        "configuration": {
            "days": 1,
            "hours": [8],
            "seeds": [1],
            "fake_llm": True,
            "model_name": "fake",
            "agents_sha256": "a",
            "locations_sha256": "b",
        },
        "aggregate": {
            "kpis": {
                path: {"mean": 0.0}
                for path in KPI_PATHS
            },
            "quality_checks": {
                "repetition_rate": {"pass_rate": 0.0},
            },
        },
    }
    current = deepcopy(baseline)
    current["aggregate"]["quality_checks"]["repetition_rate"]["pass_rate"] = 1.0

    comparison = compare_benchmarks(current, baseline)

    assert comparison["verdict"] == "better"
    assert comparison["improved_checks"] == ["repetition_rate"]
