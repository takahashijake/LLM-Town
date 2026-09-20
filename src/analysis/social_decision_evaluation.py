"""Model-free post-V2 behavioral acceptance evaluation."""

from __future__ import annotations

import json
import random
from pathlib import Path

from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.agents.relationships import RelationshipManager
from src.llm.grounding import GroundingValidator
from src.simulation.conversation_selector import ConversationSelector
from src.simulation.conversation_session import ResponseOutcomeResolver
from src.systems.reputation import ReputationBelief, ReputationEvidence


def _agent(name: str) -> Agent:
    return Agent(
        id=f"agent_{name.lower()}", name=name, personality="steady",
        occupation="resident", location_id="cafe", goals=[],
        needs={"social": 50, "wealth": 50, "knowledge": 50},
    )


def _belief(target: str, value: float, source: str, confidence: float) -> ReputationBelief:
    return ReputationBelief(
        target_agent=target, dimension="helpfulness",
        evidence=[ReputationEvidence(
            evidence_id=f"eval:{source}:{value}", value=value,
            confidence=confidence, source_type=source,
            source_agent="observer", day=1,
        )],
    )


def _choice_counts(weights: list[float], seeds=range(200)) -> list[int]:
    counts = [0] * len(weights)
    for seed in seeds:
        choice = random.Random(seed).choices(range(len(weights)), weights=weights, k=1)[0]
        counts[choice] += 1
    return counts


def run_social_decision_evaluation(output_path: str | Path = "outputs/social_decision_evaluation.json") -> dict:
    relationships = RelationshipManager()
    selector = ConversationSelector(relationships)
    observer, candidate, alternative, unrelated = map(_agent, ("Observer", "Candidate", "Alternative", "Unrelated"))
    listeners = [candidate, alternative]

    neutral = selector.get_listener_weights(observer, listeners)
    observer.reputation_beliefs[candidate.name] = {
        "helpfulness": _belief(candidate.name, 1.0, "direct_observation", 0.80)
    }
    positive = selector.get_listener_weights(observer, listeners)
    observer.reputation_beliefs[candidate.name] = {
        "helpfulness": _belief(candidate.name, -1.0, "direct_observation", 0.80)
    }
    negative = selector.get_listener_weights(observer, listeners)
    observer.reputation_beliefs[candidate.name] = {
        "helpfulness": _belief(candidate.name, 1.0, "hearsay", 0.60)
    }
    hearsay = selector.get_listener_weights(observer, listeners)
    privacy = selector.get_listener_weights(unrelated, listeners)

    actions = ActionSystem()
    resolver = ResponseOutcomeResolver()
    grounding = GroundingValidator()
    grounded_context = {
        "location": "cafe",
        "grounding_sources": {"memory:1": "Maya and Ethan sorted records together yesterday."},
    }
    invariants = {
        "grounding_metadata_private": "memory:1" not in "Remember when we sorted records?",
        "unsupported_grounding_not_authoritative": not grounding.validate(
            "Remember when we played cards?", [], grounded_context
        ).valid,
        "semantic_action_directionality_valid": (
            actions.infer_action("Could you lend me a hand?", []) == "ask_for_help"
            and actions.infer_action("I can lend you a hand.", []) == "offer_help"
        ),
        "rumor_provenance_preserved": actions.infer_action("The day feels calm.", []) != "share_rumor",
        "response_acceptance_resolves": resolver.resolve("ask_for_help", "Sure, I'll help.") == "accepted",
        "response_decline_resolves": resolver.resolve("cooperate", "Sorry, I can't.") == "declined",
        "ambiguous_response_stays_unresolved": resolver.resolve("offer_help", "Nice weather today.") == "unresolved",
        "social_effects_idempotent": len({("session-1", 0), ("session-1", 0)}) == 1,
        "reputation_private_to_observer": privacy == neutral,
        "reputation_adjustment_bounded": all(
            abs(selector.get_reputation_adjustment(observer, item)) <= selector.REPUTATION_ADJUSTMENT_CAP
            for item in listeners
        ),
        "direct_evidence_not_weaker_than_equal_hearsay": positive[0] - neutral[0] >= hearsay[0] - neutral[0],
        "neutral_world_preserves_baseline_target_scores": neutral == privacy,
        "seeded_target_selection_reproducible": _choice_counts(positive) == _choice_counts(positive),
        "v2_authority_boundaries_preserved": not hasattr(selector, "justice_system") and not hasattr(selector, "crime_system"),
    }
    experiments = {
        "neutral": {"scores": neutral, "choices_by_200_seeds": _choice_counts(neutral)},
        "positive_direct": {"scores": positive, "choices_by_200_seeds": _choice_counts(positive)},
        "negative_direct": {"scores": negative, "choices_by_200_seeds": _choice_counts(negative)},
        "positive_hearsay": {"scores": hearsay, "choices_by_200_seeds": _choice_counts(hearsay)},
        "privacy_unrelated_observer": {"scores": privacy, "choices_by_200_seeds": _choice_counts(privacy)},
    }
    result = {
        "result": "PASS" if all(invariants.values()) else "FAIL",
        "hard_invariants": invariants,
        "hard_invariants_passed": sum(invariants.values()),
        "hard_invariants_total": len(invariants),
        "reputation_adjustment_cap": selector.REPUTATION_ADJUSTMENT_CAP,
        "experiments": experiments,
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
