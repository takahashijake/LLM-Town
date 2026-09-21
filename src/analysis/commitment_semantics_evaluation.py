"""Deterministic golden evaluation for bounded commitment semantics."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from src.simulation.conversation_session import ResponseOutcomeResolver
from src.simulation.social_semantics import classify_commitment_relation, semantic_action_compatibility
from src.systems.commitments import CommitmentSystem, SocialCommitment


LABELS = ("accepted", "declined", "unresolved")


def run_commitment_semantics_evaluation(project_root: str | Path = ".") -> dict:
    root = Path(project_root)
    corpus = json.loads((root / "data/commitment_semantics_golden.json").read_text())
    resolver = ResponseOutcomeResolver()
    recognizer = CommitmentSystem()
    goods = {"reference_book": "reference book", "trade_materials": "trade materials"}
    matrix = {expected: {actual: 0 for actual in LABELS} for expected in LABELS}
    failures = []
    for case in corpus:
        proposal = recognizer.recognize_proposal(case["proposal"], day=1, known_goods=goods)
        semantic_action = "cooperate" if case["target"] == "meet" else "ask_for_help"
        actual, reason = resolver.resolve_with_reason(
            semantic_action, case["response"], proposal=proposal,
            parsed_action=case["action"], social_response=None,
        )
        matrix[case["label"]][actual] += 1
        if actual != case["label"]:
            failures.append({**case, "actual": actual, "reason": reason})

    accepted_tp = matrix["accepted"]["accepted"]
    predicted_accepted = sum(matrix[label]["accepted"] for label in LABELS)
    clear = [case for case in corpus if case.get("clear_acceptance")]
    clear_misses = [failure for failure in failures if failure.get("clear_acceptance")]
    counter = [case for case in corpus if case.get("counteroffer")]
    class_counts = Counter(case["label"] for case in corpus)

    compatibility_cases = [
        ("cooperate", "Maybe we could team up on some projects soon.", True),
        ("offer_help", "I can help you carry those boxes.", True),
        ("compliment", "Your work on the stall is impressive.", True),
        ("ask_for_help", "Could you help me check these records?", True),
        ("chat", "How has your morning been?", True),
        ("compliment", "Can you help me with this?", False),
    ]
    compatibility_results = []
    for action, dialogue, expected in compatibility_cases:
        actual, reason = semantic_action_compatibility(action, dialogue)
        compatibility_results.append({"action": action, "dialogue": dialogue, "expected": expected, "actual": actual, "reason": reason})

    relation_cases = [
        ({"id":"commitment-00000001","status":"expired"}, "I've been thinking about our last meeting.", "contradiction"),
        ({"id":"commitment-00000002","status":"expired"}, "I already brought you the book.", "contradiction"),
        ({"id":"commitment-00000003","status":"expired"}, "I couldn't get the book yesterday. I can try again today.", "state_consistent"),
        ({"id":"commitment-00000004","status":"fulfilled"}, "How's the material I brought you?", "state_consistent"),
    ]
    relation_results = []
    for commitment, dialogue, expected in relation_cases:
        result = classify_commitment_relation(commitment, dialogue)
        relation_results.append({"dialogue": dialogue, "expected": expected, **result})

    agents = [SimpleNamespace(id="a", name="Maya"), SimpleNamespace(id="b", name="Carlos")]
    system = CommitmentSystem(agents=agents)
    contexts = []
    for kind, metadata, status in (
        ("meet", {"location":"cafe"}, "expired"),
        ("transfer", {"good_id":"reference_book", "quantity":1}, "fulfilled"),
        ("help", {"task":"repair the fence"}, "accepted"),
    ):
        item = SocialCommitment(
            id=f"commitment-{len(contexts)+1:08d}", proposer_id="a", counterpart_id="b",
            commitment_type=kind, status=status, created_day=1, due_day=2,
            metadata=metadata, resolution_day=2 if status != "accepted" else None,
        )
        contexts.append(system._format_context(item, "b"))

    false_positive = predicted_accepted - accepted_tp
    checks_pass = (
        not failures
        and all(x["actual"] == x["expected"] for x in compatibility_results)
        and all(x["classification"] == x["expected"] for x in relation_results)
    )
    result = {
        "result": "PASS" if checks_pass else "FAIL",
        "corpus": {"examples": len(corpus), "class_distribution": dict(sorted(class_counts.items()))},
        "confusion_matrix": matrix,
        "metrics": {
            "commitment_creation_precision": accepted_tp / predicted_accepted if predicted_accepted else 1.0,
            "clear_acceptance_recall": (len(clear) - len(clear_misses)) / len(clear),
            "decline_accuracy": matrix["declined"]["declined"] / class_counts["declined"],
            "unresolved_accuracy": matrix["unresolved"]["unresolved"] / class_counts["unresolved"],
            "counteroffer_accuracy": sum(1 for case in counter if not any(f["id"] == case["id"] for f in failures)) / len(counter),
            "false_commitment_creation_rate": false_positive / max(1, class_counts["declined"] + class_counts["unresolved"]),
            "false_negative_clear_acceptance_rate": len(clear_misses) / len(clear),
        },
        "failures": failures,
        "semantic_action_compatibility": compatibility_results,
        "state_consistency": relation_results,
        "natural_context_rendering": contexts,
    }
    return result


def write_commitment_semantics_evaluation(result: dict, output: str | Path) -> None:
    Path(output).write_text(json.dumps(result, indent=2) + "\n")
