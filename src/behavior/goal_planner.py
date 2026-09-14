"""Deterministic goal selection and small, explicit strategy menus."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.agents.goal import Goal
from src.systems.reputation import ReputationBelief


@dataclass(frozen=True)
class StrategyCandidate:
    name: str
    intent_type: str
    expected_progress: float
    target_agent: str | None = None
    target_location: str | None = None
    required_action: str | None = None
    social_risk_factor: float = 0.0
    reputation_risk_factor: float = 0.0
    opportunity_relevance: float = 0.0
    feasible: bool = True
    infeasible_reason: str = ""
    score: float = 0.0
    relationship_influenced: bool = False
    relationship_reason: str = ""
    relationship_snapshot: dict = field(default_factory=dict)
    relevant_social_memories: tuple[str, ...] = ()


class GoalPlanner:
    """Own durable objectives; delegate only tactic construction to IntentPlanner."""

    MAX_ACTIVE_GOALS = 2
    MIN_COMMITMENT_DAYS = 1
    ADAPTATION_MARGIN = 0.75

    def ensure_goals(self, agent, engine, current_day: int) -> None:
        if len(agent.get_active_goals()) >= self.MAX_ACTIVE_GOALS:
            return
        candidates: list[tuple[str, str, int, list[str], list[str]]] = []
        others = [other for other in engine.agents if other.name != agent.name]
        if others:
            weakest = min(
                others,
                key=lambda other: (
                    engine.relationships.get_score(agent.name, other.name), other.name
                ),
            )
            weak_score = engine.relationships.get_score(agent.name, weakest.name)
            if weak_score <= -2:
                candidates.append((
                    "repair_relationship",
                    f"Repair the relationship with {weakest.name}",
                    5,
                    [weakest.name],
                    [],
                ))
        need = agent.get_primary_need()
        if need == "knowledge":
            category, description, location = (
                "increase_knowledge", "Build useful knowledge about town activity", "library"
            )
        elif need == "wealth":
            category, description, location = (
                "seek_work", "Find a useful work opportunity", "market"
            )
        else:
            category, description, location = (
                "socialize", "Maintain supportive social contact", "cafe"
            )
        candidates.append((category, description, 2, [], [location]))

        for category, description, priority, targets, locations in candidates:
            if len(agent.get_active_goals()) >= self.MAX_ACTIVE_GOALS:
                break
            duplicate = any(
                goal.category == category and goal.target_agents == targets
                for goal in agent.goals if isinstance(goal, Goal)
            )
            if duplicate:
                continue
            ordinal = len(agent.goals)
            goal = Goal.from_legacy(agent.name, description, ordinal)
            goal.category = category
            goal.priority = priority
            goal.created_day = current_day
            goal.review_day = current_day + 7
            goal.target_agents = targets
            goal.target_locations = locations
            agent.goals.append(goal)

    def choose_primary_goal(self, agent, engine, current_day: int) -> Goal | None:
        ranked = []
        for goal in agent.get_active_goals():
            candidates = self.generate_strategies(goal, agent, engine)
            feasible = [candidate for candidate in candidates if candidate.feasible]
            if not feasible:
                continue
            need_name = {
                "investigate": "knowledge", "increase_knowledge": "knowledge",
                "seek_work": "wealth",
            }.get(goal.category, "social")
            pressure = (100 - agent.needs.get(need_name, 50)) / 50
            urgency = 1.0 if current_day >= goal.review_day else 0.0
            opportunity = max(candidate.opportunity_relevance for candidate in feasible)
            progress = goal.progress / goal.progress_target
            value = goal.priority * 2 + pressure + urgency + opportunity + progress * 0.5
            ranked.append((value, goal.id, goal))
        return max(ranked, default=(0, "", None), key=lambda item: (item[0], item[1]))[2]

    def _relationship_rank(self, agent, engine, name: str) -> tuple[float, int]:
        state = agent.get_relationship_state(name)
        return (
            state.decision_value(),
            engine.relationships.get_score(agent.name, name),
        )

    def _best_social_target(
        self,
        agent,
        engine,
        names: list[str],
    ) -> str | None:
        return max(
            sorted(names),
            key=lambda name: self._relationship_rank(agent, engine, name),
            default=None,
        )

    def _goal_target(self, goal: Goal, agent, engine) -> str | None:
        available_names = {other.name for other in engine.agents if other.name != agent.name}
        if goal.target_agents:
            return goal.target_agents[0]
        if goal.category not in {"build_friendship", "repair_relationship"}:
            return None
        if not available_names:
            return None
        chooser = max if goal.category == "build_friendship" else min
        target = chooser(sorted(available_names), key=lambda name: (
            agent.get_relationship_state(name).decision_value(),
            engine.relationships.get_score(agent.name, name),
        ))
        goal.target_agents = [target]
        return target

    def reputation_risk(self, agent, target_agent: str | None) -> float:
        if not target_agent:
            return 0.0
        risk = 0.0
        directions = {
            "trustworthiness": -1,
            "helpfulness": -1,
            "cooperativeness": -1,
            "hostility": 1,
        }
        for dimension, belief in agent.reputation_beliefs.get(target_agent, {}).items():
            if not isinstance(belief, ReputationBelief) or belief.confidence < 0.25:
                continue
            adverse = max(0.0, directions.get(dimension, 0) * belief.score)
            source_weight = 1.0 if belief.source_type in {
                "direct_interaction", "direct_observation"
            } else 0.45
            risk += adverse * belief.confidence * source_weight
        return round(risk, 4)

    def _score(
        self,
        candidate: StrategyCandidate,
        relationship: int,
        risk: float,
        relationship_state=None,
    ) -> float:
        social_cost = max(0, -relationship) * candidate.social_risk_factor * 0.35
        relationship_bonus = max(0, relationship) * (
            0.15 if candidate.name in {"direct_cooperation", "ask_target_directly"} else 0.05
        )
        direct_value = relationship_state.decision_value() if relationship_state else 0.0
        direct_bonus = direct_value * (
            2.4 if candidate.required_action in {"ask_for_help", "cooperate"} else 1.0
        )
        return round(
            candidate.expected_progress - social_cost
            - risk * candidate.reputation_risk_factor
            + candidate.opportunity_relevance + relationship_bonus + direct_bonus,
            4,
        )

    def generate_strategies(self, goal: Goal, agent, engine) -> list[StrategyCandidate]:
        target = self._goal_target(goal, agent, engine)
        available_agents = sorted(
            other.name for other in engine.agents if other.name != agent.name
        )
        available_locations = {location.id for location in engine.locations}
        intent_type = {
            "increase_knowledge": "investigate",
            "improve_social_support": "socialize",
        }.get(goal.category, goal.category)

        raw: list[StrategyCandidate] = []
        if goal.category in {"build_friendship", "repair_relationship"}:
            raw = [
                StrategyCandidate("direct_cooperation", intent_type, 6.0, target,
                                  required_action="cooperate", social_risk_factor=0.8,
                                  reputation_risk_factor=2.5, opportunity_relevance=0.5),
                StrategyCandidate("apologize_directly", intent_type, 5.2, target,
                                  required_action="apologize", social_risk_factor=0.25,
                                  reputation_risk_factor=0.35, opportunity_relevance=0.4),
                StrategyCandidate("offer_help", intent_type, 5.0, target,
                                  required_action="offer_help", social_risk_factor=0.45,
                                  reputation_risk_factor=0.7, opportunity_relevance=0.4),
                StrategyCandidate("low_risk_chat", intent_type, 4.4, target,
                                  required_action="chat", social_risk_factor=0.1,
                                  reputation_risk_factor=0.2, opportunity_relevance=0.3),
            ]
        elif goal.category in {"investigate", "increase_knowledge"}:
            location = (goal.target_locations or ["library"])[0]
            alternate = self._best_social_target(
                agent, engine, [name for name in available_agents if name != target]
            )
            raw = [
                StrategyCandidate("ask_target_directly", intent_type, 5.5, target,
                                  required_action="ask_for_help", social_risk_factor=0.5,
                                  reputation_risk_factor=0.9, opportunity_relevance=0.5,
                                  feasible=bool(target),
                                  infeasible_reason="goal has no direct target" if not target else ""),
                StrategyCandidate("ask_informed_agent", intent_type, 4.8, alternate,
                                  required_action="ask_for_help", social_risk_factor=0.2,
                                  reputation_risk_factor=0.1, opportunity_relevance=0.4),
                StrategyCandidate("seek_information_at_location", intent_type, 4.6,
                                  target_location=location, opportunity_relevance=0.7),
                StrategyCandidate("observe_relevant_activity", intent_type, 3.8,
                                  target_location=location, opportunity_relevance=0.5),
            ]
        else:
            location = (goal.target_locations or [
                "market" if goal.category == "seek_work" else "cafe"
            ])[0]
            raw = [
                StrategyCandidate(
                    "ask_reliable_partner", intent_type, 4.9,
                    target_agent=self._best_social_target(agent, engine, available_agents),
                    required_action="ask_for_help", social_risk_factor=0.45,
                    reputation_risk_factor=0.6, opportunity_relevance=0.4,
                    feasible=bool(available_agents),
                    infeasible_reason="no social partner is available" if not available_agents else "",
                ),
                StrategyCandidate("direct_participation", intent_type, 5.0,
                                  target_location=location, opportunity_relevance=0.7),
                StrategyCandidate("low_risk_chat", intent_type, 4.2,
                                  required_action="chat", reputation_risk_factor=0.15,
                                  opportunity_relevance=0.4),
            ]

        scored = []
        for candidate in raw:
            feasible = candidate.feasible
            reason = candidate.infeasible_reason
            if candidate.target_agent and candidate.target_agent not in available_agents:
                feasible, reason = False, "target agent is unavailable"
            if candidate.target_location and candidate.target_location not in available_locations:
                feasible, reason = False, "target location is unavailable"
            candidate_relationship = (
                engine.relationships.get_score(agent.name, candidate.target_agent)
                if candidate.target_agent else 0
            )
            candidate_state = (
                agent.get_relationship_state(candidate.target_agent)
                if candidate.target_agent else None
            )
            candidate_risk = self.reputation_risk(agent, candidate.target_agent)
            if candidate.required_action and candidate.target_agent:
                allowed = engine.actions.get_allowed_actions_for_relationship(
                    candidate_relationship
                )
                if candidate.required_action not in allowed:
                    feasible, reason = False, "relationship rules disallow required action"
            score = self._score(
                candidate, candidate_relationship, candidate_risk, candidate_state
            )
            direct_value = candidate_state.decision_value() if candidate_state else 0.0
            relationship_reason = ""
            if candidate_state and abs(direct_value) > 0.0001:
                direction = "supports" if direct_value > 0 else "discourages"
                relationship_reason = (
                    f"Direct history with {candidate.target_agent} {direction} this tactic "
                    f"(decision value {direct_value:+.3f})."
                )
            scored.append(StrategyCandidate(**{
                **candidate.__dict__, "feasible": feasible,
                "infeasible_reason": reason, "score": score,
                "relationship_influenced": bool(relationship_reason),
                "relationship_reason": relationship_reason,
                "relationship_snapshot": (
                    candidate_state.to_dict() if candidate_state else {}
                ),
                "relevant_social_memories": tuple(
                    memory.summary
                    for memory in agent.get_social_memories(
                        candidate.target_agent, limit=3
                    )
                ) if candidate.target_agent else (),
            }))
        return sorted(scored, key=lambda item: (-item.score, item.name))

    def select_strategy(self, goal: Goal, agent, engine) -> StrategyCandidate | None:
        return next(
            (candidate for candidate in self.generate_strategies(goal, agent, engine)
             if candidate.feasible),
            None,
        )

    def should_adapt(self, goal: Goal, intent, agent, engine, current_day: int):
        candidates = self.generate_strategies(goal, agent, engine)
        best = next((candidate for candidate in candidates if candidate.feasible), None)
        current = next((
            candidate for candidate in candidates
            if candidate.name == intent.strategy
            and candidate.target_agent == intent.target_agent
        ), None)
        if best is None:
            return None, "hard_constraint"
        if current is None or not current.feasible:
            target_still_available = (
                not intent.target_agent
                or any(
                    other.name == intent.target_agent
                    for other in engine.agents
                    if other.name != agent.name
                )
            )
            trigger = (
                "relationship"
                if (
                    (current and "relationship rules" in current.infeasible_reason)
                    or (current is None and target_still_available and any(
                        candidate.name == intent.strategy
                        for candidate in candidates
                    ))
                )
                else "hard_constraint"
            )
            return best, trigger
        committed = current_day - (goal.strategy_started_day or intent.created_day)
        if committed < self.MIN_COMMITMENT_DAYS:
            return None, "commitment_period"
        target = intent.target_agent or (
            goal.target_agents[0] if goal.target_agents else None
        )
        relationship = engine.relationships.get_score(agent.name, target) if target else 0
        risk = self.reputation_risk(agent, target)
        reputation_changed = abs(risk - goal.last_reputation_risk) >= 0.75
        relationship_changed = (
            goal.last_relationship_score is not None
            and (relationship // 3) != (goal.last_relationship_score // 3)
        )
        snapshot = getattr(intent, "relationship_snapshot", {}) or {}
        prior_direct_value = (
            snapshot.get("trust", 0) * 0.3
            + snapshot.get("affinity", 0) * 0.15
            + snapshot.get("cooperation", 0) * 0.2
            + snapshot.get("helpfulness", 0) * 0.25
            - snapshot.get("hostility", 0) * 0.35
        )
        current_direct_value = (
            agent.get_relationship_state(intent.target_agent).decision_value()
            if intent.target_agent else 0.0
        )
        direct_history_changed = abs(current_direct_value - prior_direct_value) >= 0.15
        strategy_changed = (
            best.name != current.name
            or best.target_agent != intent.target_agent
        )
        if strategy_changed and best.score >= current.score + self.ADAPTATION_MARGIN:
            if reputation_changed:
                return best, "reputation"
            if (
                relationship_changed
                or direct_history_changed
                or (
                    best.target_agent != intent.target_agent
                    and best.relationship_influenced
                )
            ):
                return best, "relationship"
        return None, "stable"

    def goal_is_complete(self, goal: Goal, agent, engine) -> tuple[bool, str]:
        target = goal.target_agents[0] if goal.target_agents else None
        score = engine.relationships.get_score(agent.name, target) if target else 0
        if goal.category == "build_friendship" and target and score >= 3:
            return True, f"Relationship with {target} reached friendly status."
        if goal.category == "repair_relationship":
            if target and score >= 0 and goal.progress >= 2:
                return True, f"Relationship with {target} recovered to neutral."
            return False, ""
        if goal.progress >= goal.progress_target:
            return True, f"Deterministic {goal.category} progress target reached."
        return False, ""
