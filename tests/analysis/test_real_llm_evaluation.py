import json

from src.analysis.real_llm_evaluation import write_real_llm_evaluation


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
    assert (tmp_path / "transcript.md").is_file()
    assert (tmp_path / "human_review_sample.json").is_file()
    assert (tmp_path / "human_review_sample.md").is_file()
    assert document["model"]["identifier"] == "test/model"
    health = document["dialogue_evaluation"]["response_health"]
    assert health["action_parsing_success_rate"] == 0.5
    assert health["malformed_responses"] == 1
    sample = json.loads((tmp_path / "human_review_sample.json").read_text())
    assert sample["memory_grounded"][0]["dialogue"].startswith("Did those")
    assert sample["suspected_repetitive_or_generic"][0]["speaker"] == "Ethan"
