from src.analysis.social_decision_evaluation import run_social_decision_evaluation


def test_social_decision_evaluation_passes_and_writes_artifact(tmp_path):
    path = tmp_path / "social.json"
    result = run_social_decision_evaluation(path)
    assert result["result"] == "PASS"
    assert result["hard_invariants_passed"] == result["hard_invariants_total"] == 14
    assert path.is_file()
    experiments = result["experiments"]
    assert experiments["positive_direct"]["scores"][0] > experiments["neutral"]["scores"][0]
    assert experiments["negative_direct"]["scores"][0] < experiments["neutral"]["scores"][0]
