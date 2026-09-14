import json

from src.analysis.relationship_evaluation import run_relationship_evaluation


def test_prompt5_evaluation_writes_semantic_artifacts(tmp_path):
    output = tmp_path / "prompt5"
    result = run_relationship_evaluation(output, project_root=".")

    assert result["metrics"]["relationship_conditioned_decision_rate"] == 1.0
    assert result["metrics"]["preferred_target_consistency"] == 1.0
    assert result["metrics"]["memory_retrieval_correctness"] == 1.0
    assert result["metrics"]["valid_relationship_diagnostics_rate"] == 1.0
    assert result["metrics"]["repair_deescalation_preferred"] == 1.0
    assert result["target_choice"]["relationship_influenced"] is True
    assert result["metrics"]["relationship_attributed_strategy_adaptation"] == 1.0
    assert result["strategy_adaptation"]["trigger"] == "relationship"
    assert all(
        "refused my request" in memory
        for memory in result["strategy_adaptation"]["prior_counterpart_memories"]
    )
    expected = {
        "metrics.json", "summary.md", "transcripts.json",
        "relationship_state_diagnostics.json", "paired_scenario_outcomes.json",
        "strategy_adaptation_diagnostics.json", "failure_cases.json",
    }
    assert expected.issubset(path.name for path in output.iterdir())
    written = json.loads((output / "metrics.json").read_text())
    assert written == result["metrics"]
