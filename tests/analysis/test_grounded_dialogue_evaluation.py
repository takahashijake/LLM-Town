import json

from src.analysis.grounded_dialogue_evaluation import evaluate_cached_fixture, evaluate_grounded_dialogue


def test_counterfactual_grounded_dialogue_evaluation_passes():
    result = evaluate_grounded_dialogue()
    assert result["passed"]
    assert result["metrics"]["scenario_count"] == 15
    assert result["metrics"]["invariants_passed"] == result["metrics"]["invariant_count"]
    assert result["metrics"]["private_information_leakage"] == 0
    assert result["metrics"]["authority_boundary_violations"] == 0


def test_cached_fixture_requires_reproducibility_metadata(tmp_path):
    assert not evaluate_cached_fixture({"metrics": {}})["valid"]
    fixture = json.loads((tmp_path / "fixture.json").read_text()) if False else {
        "model": "fixture", "model_configuration": {}, "commit_sha": "abc", "seed": 42,
        "scenario_version": "v1", "prompt_context_hash": "hash", "timestamp": "2026-09-22T00:00:00Z",
        "parser_version": "v1", "validator_version": "v1", "metrics": {},
    }
    assert evaluate_cached_fixture(fixture)["valid"]
