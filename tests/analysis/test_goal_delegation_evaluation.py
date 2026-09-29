from src.analysis.goal_delegation_evaluation import evaluate_goal_delegation


def test_goal_delegation_evaluation_passes_with_named_coverage():
    result = evaluate_goal_delegation()
    assert result["passed"], result["diagnostics"]
    assert result["scenario_count"] >= 40
    assert result["invariant_count"] >= 8
    assert result["scenarios"]["real_conversation_bridge_creates_one_commitment"]
    assert result["scenarios"]["fulfillment_advances_requester_goal_once"]
    assert result["scenarios"]["stale_revision_fulfillment_does_not_cross_credit"]
    assert result["invariants"]["plan_invariants_hold"]
