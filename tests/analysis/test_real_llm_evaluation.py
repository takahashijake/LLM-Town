import json
from pathlib import Path

from src.analysis.benchmark import BenchmarkConfig
from src.analysis.real_llm_evaluation import (
    run_real_llm_evaluation,
    write_real_llm_evaluation,
)
from src.llm.client import FakeLLMClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_real_llm_evaluation_writes_metrics_transcript_and_review(tmp_path):
    conversation_path = tmp_path / "seed-42" / "logs" / "conversations" / "conversations.jsonl"
    conversation_path.parent.mkdir(parents=True)
    rows = [
        {
            "day": 1,
            "hour": 8,
            "location": "library",
            "speaker": "Maya",
            "listener": "Ethan",
            "conversation": "Did those invoice totals match the notes we compared?",
            "action": "ask_for_help",
            "suggested_action": "ask_for_help",
            "parsed_action": "ask_for_help",
            "inferred_action": "ask_for_help",
            "action_source": "llm",
            "dialogue_source": "llm",
            "generation_error": "",
            "reputation_influenced": True,
            "rumor_transmission": {
                "target_agent": "Carlos",
                "dimension": "helpfulness",
            },
            "context": {
                "occupation": "journalist",
                "memories": ["Yesterday Ethan and Maya compared invoice totals."],
                "relationship_history": [],
                "journals": [],
                "goals": ["understand the invoices"],
                "speaker_intent": {"description": "Ask Ethan about invoice totals"},
                "daily_event": None,
                "daily_event_relevant": False,
                "town_arcs": [],
                "reputation": [
                    "The speaker believes Ethan is somewhat helpful."
                ],
                "reputation_rumor": "Carlos seems helpful.",
            },
        },
        {
            "day": 1,
            "hour": 12,
            "location": "cafe",
            "speaker": "Ethan",
            "listener": "Maya",
            "conversation": "The town feels busy today.",
            "action": "chat",
            "suggested_action": "compliment",
            "parsed_action": "chat",
            "inferred_action": "chat",
            "action_source": "fallback_bad_json",
            "dialogue_source": "agent_fallback_empty",
            "generation_error": "",
            "context": {},
        },
    ]
    conversation_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    metrics = {"intent_followthrough": {"action_compatibility_rate": 0.75}}
    benchmark = {
        "created_at": "2026-01-01T00:00:00+00:00",
        "revision": {"commit": "abc"},
        "environment": {"python": "3.test"},
        "configuration": {
            "model_name": "test/model",
            "max_new_tokens": 80,
            "temperature": 0.3,
            "top_p": 0.8,
            "days": 1,
            "hours": [8, 12],
        },
        "runs": [
            {
                "seed": 42,
                "artifacts": {
                    "conversations": "seed-42/logs/conversations/conversations.jsonl",
                    "simulation_output": "seed-42/simulation.log",
                },
                "metrics": metrics,
            }
        ],
    }

    document = write_real_llm_evaluation(benchmark, tmp_path)

    assert (tmp_path / "evaluation.json").is_file()
    assert (tmp_path / "metadata.json").is_file()
    assert (tmp_path / "metrics.json").is_file()
    assert (tmp_path / "transcript.txt").is_file()
    assert (tmp_path / "human_review_sample.json").is_file()
    assert (tmp_path / "review.md").is_file()
    assert (tmp_path / "strategy_adaptation_diagnostics.json").is_file()
    assert document["model"]["identifier"] == "test/model"
    health = document["dialogue_evaluation"]["response_health"]
    assert health["action_parsing_success_rate"] == 0.5
    assert health["malformed_responses"] == 1
    assert health["dialogue_fallbacks"] == 1
    written_metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert written_metrics["malformed_output"] == {"count": 1, "rate": 0.5}
    assert written_metrics["fallback"]["count"] == 1
    assert written_metrics["action_language_diagnostics"]["parser_inference_disagreements"] == 0
    assert written_metrics["strategy_adaptation_diagnostics"]["goals_reviewed"] == 0
    assert written_metrics["conversation_sessions"]["conversation_session_count"] == 2
    assert "=== Conversation Session 1" in (tmp_path / "transcript.txt").read_text()
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    assert metadata["git_commit"] == "abc"
    assert metadata["python_version"] == "3.test"
    assert metadata["days"] == 1
    assert metadata["hours"] == [8, 12]
    assert metadata["seed"] == 42
    sample = json.loads((tmp_path / "human_review_sample.json").read_text())
    assert sample["memory_grounded"][0]["dialogue"].startswith("Did those")
    assert sample["suspected_repetitive_or_generic"][0]["speaker"] == "Ethan"
    assert sample["malformed_or_fallback"][0]["speaker"] == "Ethan"
    assert sample["legitimate_rumor_transmission"][0]["speaker"] == "Maya"
    assert sample["behavior_influenced_by_reputation"][0]["speaker"] == "Maya"


def test_analysis_helpers_are_deterministic():
    from src.analysis.real_llm_evaluation import (
        analyze_real_llm_records,
        build_human_review_sample,
    )

    rows = [
        {
            "conversation": "I can help with the library records.",
            "action": "offer_help",
            "action_source": "llm",
            "dialogue_source": "llm",
            "speaker_intent_type": "investigate",
            "context": {"activity_display": "review library records"},
        }
    ]
    simulation = {"intent_followthrough": {"action_compatibility_rate": 0.0}}
    first_metrics, first_flags = analyze_real_llm_records(rows, simulation)
    second_metrics, second_flags = analyze_real_llm_records(rows, simulation)

    assert first_metrics == second_metrics
    assert first_flags == second_flags
    assert build_human_review_sample(rows, first_flags) == build_human_review_sample(
        rows, second_flags
    )
    assert build_human_review_sample(rows, first_flags)["activity_grounded"]
    assert build_human_review_sample(rows, first_flags)["intent_action_mismatch"]


def test_mocked_real_evaluation_isolated_from_ordinary_state_and_logs(
    tmp_path, monkeypatch
):
    from src.analysis import benchmark as benchmark_module

    ordinary_state = PROJECT_ROOT / "data" / "save_state.json"
    ordinary_logs = PROJECT_ROOT / "logs"
    state_before = ordinary_state.read_bytes() if ordinary_state.exists() else None
    logs_before = {
        path.relative_to(ordinary_logs): (path.stat().st_mtime_ns, path.stat().st_size)
        for path in ordinary_logs.rglob("*")
        if path.is_file()
    } if ordinary_logs.exists() else {}

    monkeypatch.setattr(benchmark_module, "_build_llm", lambda _config: FakeLLMClient())
    monkeypatch.setattr(
        benchmark_module, "_seed_random_generators", lambda *_args, **_kwargs: None
    )
    output_dir = tmp_path / "isolated-evaluation"
    config = BenchmarkConfig(
        days=1,
        seeds=(42,),
        hours=(8,),
        fake_llm=False,
        model_name="mock/real-model",
    )

    document = run_real_llm_evaluation(
        config, output_dir, project_root=PROJECT_ROOT
    )

    assert document["model_identifier"] == "mock/real-model"
    assert {
        "metadata.json", "metrics.json", "transcript.txt", "review.md"
    }.issubset(path.name for path in output_dir.iterdir())
    assert (ordinary_state.read_bytes() if ordinary_state.exists() else None) == state_before
    logs_after = {
        path.relative_to(ordinary_logs): (path.stat().st_mtime_ns, path.stat().st_size)
        for path in ordinary_logs.rglob("*")
        if path.is_file()
    } if ordinary_logs.exists() else {}
    assert logs_after == logs_before
