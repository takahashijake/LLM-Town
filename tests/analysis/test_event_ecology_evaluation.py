from src.analysis.event_ecology_evaluation import evaluate_event_ecology


def test_event_ecology_evaluation_passes():
    result = evaluate_event_ecology()
    assert result["passed"], result["diagnostics"]
