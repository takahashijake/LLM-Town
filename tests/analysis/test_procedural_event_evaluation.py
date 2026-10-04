from src.analysis.procedural_event_evaluation import evaluate_procedural_events


def test_procedural_event_acceptance_gate():
    result = evaluate_procedural_events()
    assert result["passed"], result["diagnostics"]
