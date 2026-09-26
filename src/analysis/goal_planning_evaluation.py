"""Deterministic acceptance evaluation for V4 bounded goal planning."""

from contextlib import contextmanager
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.agents.goal import Goal
from src.behavior.goal_planner import StrategyCandidate
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


@contextmanager
def _isolated_random_state(seed: int = 0):
    state = random.getstate()
    random.seed(seed)
    try:
        yield
    finally:
        random.setstate(state)


def _engine(root: Path, name: str, *, load: bool = False) -> SimulationEngine:
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs",
    )


def _knowledge_goal(engine: SimulationEngine, goal_id: str,
                    *, target: int = 3) -> Goal:
    agent = engine.agents[0]
    goal = Goal(
        id=goal_id, agent_name=agent.name,
        description="Build useful knowledge about town activity",
        category="increase_knowledge", priority=5, created_day=1,
        review_day=7, progress_target=target, target_locations=["library"],
    )
    agent.goals = [goal]
    return goal


def evaluate_goal_planning() -> dict:
    scenarios: dict[str, bool] = {}
    diagnostics: dict[str, str] = {}
    with _isolated_random_state(), TemporaryDirectory() as directory:
        root = Path(directory)

        stable = _engine(root, "stable")
        goal = _knowledge_goal(stable, "goal-stable")
        stable.update_agent_intents(1)
        plan = stable.plan_system.get_goal_plan(goal.id)
        first_intent = stable.agent_intents[stable.agents[0].name]
        stable.plan_system.ensure_goal_plan(
            goal, stable.agents[0], stable, stable.goal_planner, 1,
        )
        scenarios["stable_plan_creation"] = (
            plan.id == f"plan:goal:{stable.agents[0].id}:{goal.id}"
            and plan.active
        )
        scenarios["repeated_planning_idempotent"] = (
            len([item for item in stable.plan_system.goal_plans
                 if item.source_goal_id == goal.id]) == 1
        )
        candidates = stable.goal_planner.generate_strategies(
            goal, stable.agents[0], stable,
        )
        scenarios["real_goal_planner_strategy"] = any(
            candidate.name == plan.strategy_name for candidate in candidates
        )
        scenarios["bounded_inspectable_metadata"] = (
            plan.strategy_name and plan.selected_day == 1
            and isinstance(plan.score_at_selection, float)
            and len(plan.transitions) == 1
            and not hasattr(plan, "memory_snapshot")
        )

        first_intent.expires_day = 1
        stable.update_agent_intents(2)
        successor = stable.agent_intents[stable.agents[0].name]
        scenarios["strategy_survives_intent_expiration"] = (
            first_intent.status == "expired"
            and plan.strategy_name == first_intent.strategy
        )
        scenarios["successor_continues_strategy"] = (
            successor.strategy == first_intent.strategy
            and successor.source_goal_plan_id == plan.id
            and successor.source_goal_plan_revision == plan.revision
        )
        stable.intent_system.update_intent_after_activity(
            day=2, agent=stable.agents[0], location_id="library",
            activity_name="Inspect town records",
        )
        scenarios["target_location_evidence_advances_goal"] = (
            goal.progress == 1 and len(plan.evidence_records) == 1
            and plan.evidence_records[0]["type"] == "activity"
        )
        progress_projection = stable.plan_system.to_dict()
        stable.state.save(stable, 2, 8)
        resumed = _engine(root, "stable", load=True)
        scenarios["save_resume_after_progress"] = (
            resumed.plan_system.to_dict() == progress_projection
            and resumed.agents[0].get_goal(goal.id).progress == 1
        )
        scenarios["save_resume_before_execution"] = all(
            item.source_goal_id for item in resumed.plan_system.goal_plans
        )
        resumed_goal = resumed.agents[0].get_goal(goal.id)
        key = resumed_goal.processed_evidence_keys[0]
        before = resumed_goal.progress
        replayed = resumed_goal.add_progress(
            1, 2, {"evidence_key": key, "intent_id": successor.id},
        )
        scenarios["evidence_replay_idempotent"] = (
            replayed is False and resumed_goal.progress == before
        )

        social = _engine(root, "social")
        maya, ethan = social.agents[:2]
        social_goal = Goal(
            id="goal-social", agent_name=maya.name,
            description=f"Build friendship with {ethan.name}",
            category="build_friendship", priority=5, created_day=1,
            review_day=7, progress_target=4, target_agents=[ethan.name],
        )
        maya.goals = [social_goal]
        social.update_agent_intents(1)
        social_plan = social.plan_system.get_goal_plan(social_goal.id)
        social_intent = social.agent_intents[maya.name]
        text_accepted = social.plan_system.observe_goal_evidence(
            social_goal, evidence_key="generated-claim", day=1,
            intent_id=social_intent.id, evidence_type="social_action",
            details={"dialogue": "We are friends now."},
        )
        scenarios["social_text_alone_cannot_advance"] = (
            not text_accepted and social_goal.progress == 0
            and not social_plan.evidence_records
        )
        social.update_intents_after_conversation(
            day=1, location_id="cafe", speaker=maya, listener=ethan,
            action="cooperate", relationship_change=1, new_score=1,
            conversation_tags=["cooperate"],
            evidence_key="conversation:evaluation:turn:0",
        )
        scenarios["authoritative_social_evidence_advances"] = (
            social_goal.progress == 1
            and social_plan.processed_evidence_keys
            == ["conversation:evaluation:turn:0"]
        )

        adapting = _engine(root, "adapting")
        maya, ethan = adapting.agents[:2]
        adapting_goal = Goal(
            id="goal-adapting", agent_name=maya.name,
            description=f"Build friendship with {ethan.name}",
            category="build_friendship", priority=5, created_day=1,
            review_day=7, progress=1, progress_target=4,
            target_agents=[ethan.name],
        )
        maya.goals = [adapting_goal]
        adapting.update_agent_intents(1)
        old_intent = adapting.agent_intents[maya.name]
        old_strategy = old_intent.strategy
        adapting.update_intents_after_conversation(
            day=1, location_id="cafe", speaker=maya, listener=ethan,
            action="argue", relationship_change=-3, new_score=-3,
            conversation_tags=["argue"], evidence_key="hostile-turn",
        )
        adapting.relationships.change_score(maya.name, ethan.name, -3)
        adapting.update_agent_intents(2)
        adapting_plan = adapting.plan_system.get_goal_plan(adapting_goal.id)
        transition = next(
            row for row in adapting_plan.transitions if row["type"] == "adapted"
        )
        scenarios["strategy_adaptation_explicit"] = (
            transition["old_strategy"] == old_strategy
            and transition["new_strategy"] == adapting_plan.strategy_name
            and transition["trigger"] == "relationship"
        )
        scenarios["progress_survives_adaptation"] = (
            adapting_goal.progress == 1
            and transition["preserved_progress"] == 1
        )
        adapting.state.save(adapting, 2, 8)
        adapting_projection = adapting.plan_system.to_dict()
        adapting_resumed = _engine(root, "adapting", load=True)
        scenarios["save_resume_after_adaptation"] = (
            adapting_resumed.plan_system.to_dict() == adapting_projection
        )

        budget = _engine(root, "budget")
        budget_goal = _knowledge_goal(budget, "goal-budget")
        budget_plan = budget.plan_system.ensure_goal_plan(
            budget_goal, budget.agents[0], budget, budget.goal_planner, 1,
        )
        for day, name in enumerate((
            "observe_relevant_activity", "seek_information_at_location",
            "observe_relevant_activity",
        ), 2):
            budget.plan_system.adapt_goal_plan(
                budget_plan,
                StrategyCandidate(name, "investigate", 4.0,
                                  target_location="library", score=4.0),
                day=day, trigger="hard_constraint", preserved_progress=0,
                goal_planner=budget.goal_planner,
            )
        fourth = budget.plan_system.adapt_goal_plan(
            budget_plan,
            StrategyCandidate("seek_information_at_location", "investigate", 4.0,
                              target_location="library", score=4.0),
            day=5, trigger="hard_constraint", preserved_progress=0,
            goal_planner=budget.goal_planner,
        )
        scenarios["adaptation_is_bounded"] = (
            not fourth and budget_plan.status == "blocked"
            and budget_plan.revision == budget.plan_system.MAX_GOAL_ADAPTATIONS
        )

        unsupported = _engine(root, "unsupported")
        unsupported_goal = _knowledge_goal(unsupported, "goal-unsupported")
        unsupported_plan = unsupported.plan_system.ensure_goal_plan(
            unsupported_goal, unsupported.agents[0], unsupported,
            unsupported.goal_planner, 1,
        )
        unsupported_result = unsupported.plan_system.adapt_goal_plan(
            unsupported_plan,
            StrategyCandidate("low_risk_chat", "socialize", 1.0,
                              required_action="invent_action", score=1.0),
            day=2, trigger="hard_constraint", preserved_progress=0,
            goal_planner=unsupported.goal_planner,
        )
        scenarios["unsupported_strategy_fails_closed"] = (
            not unsupported_result and unsupported_plan.status == "blocked"
            and unsupported_plan.no_plan_reason == "unsupported_required_action"
        )

        complete = _engine(root, "complete")
        complete_goal = _knowledge_goal(complete, "goal-complete", target=1)
        complete.update_agent_intents(1)
        complete.intent_system.update_intent_after_activity(
            day=1, agent=complete.agents[0], location_id="library",
            activity_name="Read records",
        )
        complete_plan = complete.plan_system.get_goal_plan(complete_goal.id)
        scenarios["goal_achievement_completes_plan"] = (
            complete_goal.status == "achieved"
            and complete_plan.status == "completed"
        )
        complete.plan_system.ensure_goal_plan(
            complete_goal, complete.agents[0], complete,
            complete.goal_planner, 2,
        )
        scenarios["terminal_plan_does_not_reopen"] = (
            len([item for item in complete.plan_system.goal_plans
                 if item.source_goal_id == complete_goal.id]) == 1
            and complete_plan.status == "completed"
        )

        terminal = _engine(root, "terminal")
        blocked_goal = _knowledge_goal(terminal, "goal-blocked")
        blocked_plan = terminal.plan_system.ensure_goal_plan(
            blocked_goal, terminal.agents[0], terminal,
            terminal.goal_planner, 1,
        )
        blocked_goal.status = "blocked"
        terminal.plan_system.synchronize_goal_plan(blocked_goal, day=2)
        abandoned_goal = Goal(
            id="goal-abandoned", agent_name=terminal.agents[1].name,
            description="Maintain social contact", category="socialize",
            priority=4, created_day=1, review_day=7,
            target_locations=["cafe"],
        )
        terminal.agents[1].goals = [abandoned_goal]
        abandoned_plan = terminal.plan_system.ensure_goal_plan(
            abandoned_goal, terminal.agents[1], terminal,
            terminal.goal_planner, 1,
        )
        abandoned_goal.status = "abandoned"
        terminal.plan_system.synchronize_goal_plan(abandoned_goal, day=2)
        scenarios["blocked_abandoned_terminalize"] = (
            blocked_plan.status == "blocked"
            and abandoned_plan.status == "abandoned"
        )

        coexist = _engine(root, "coexist")
        coexist.update_agent_intents(1)
        item = coexist.commitment_system.create(
            proposer_id="agent_002", counterpart_id="agent_001",
            commitment_type="meet", day=1, due_day=1,
            metadata={"location": "cafe"}, status="proposed",
        )
        coexist.commitment_system.transition(
            item.id, "accepted", day=1, reason="evaluation_acceptance",
        )
        with patch("src.behavior.planner.random.random", return_value=0.0):
            coexist.activity_system.run_agent_activities(
                [coexist.agents[0]], [place.id for place in coexist.locations],
                1, 8, None, coexist.agent_intents,
            )
        scenarios["commitment_and_goal_plans_coexist"] = (
            bool(coexist.plan_system.plans and coexist.plan_system.goal_plans)
        )
        scenarios["due_commitment_priority_preserved"] = (
            coexist.activity_records[-1]["source_commitment_id"] == item.id
            and item.status == "fulfilled"
        )
        scenarios["v3_commitment_behavior_unchanged"] = (
            coexist.plan_system.plans[0].status == "completed"
            and all(coexist.commitment_system.validate_invariants().values())
        )
        private_context = coexist.prepare_conversation_context(
            "cafe", coexist.agents[1], coexist.agents[0], 1,
        )["context"]
        scenarios["private_plan_mechanics_do_not_leak"] = not any(
            plan.id in json.dumps(private_context)
            for plan in coexist.plan_system.goal_plans
        )

        systems = [stable, social, adapting, budget, unsupported,
                   complete, terminal, coexist]
        invariant_sets = [
            engine.plan_system.validate_invariants(engine.goal_planner)
            for engine in systems
        ]
        invariants = {
            "stable_unique_plan_ids": all(
                checks["unique_goal_plan_ids"] for checks in invariant_sets
            ),
            "at_most_one_plan_per_goal": all(
                checks["one_goal_plan_per_source"] for checks in invariant_sets
            ),
            "real_owner_and_goal": all(
                checks["valid_goal_sources"] for checks in invariant_sets
            ),
            "active_plan_has_active_goal": all(
                checks["active_goal_plan_has_active_source"]
                for checks in invariant_sets
            ),
            "finite_strategy_vocabulary": all(
                checks["known_goal_strategies"] for checks in invariant_sets
            ),
            "unsupported_actions_not_executable": scenarios[
                "unsupported_strategy_fails_closed"
            ],
            "processed_evidence_unique": all(
                checks["goal_evidence_unique"] for checks in invariant_sets
            ),
            "terminal_plans_cannot_execute": all(
                not plan.active for plan in (
                    budget_plan, unsupported_plan, complete_plan,
                    blocked_plan, abandoned_plan,
                )
            ),
            "save_resume_projection_idempotent": scenarios[
                "save_resume_after_progress"
            ] and scenarios["save_resume_after_adaptation"],
            "commitment_plan_invariants": all(
                value for key, value in coexist.plan_system.validate_invariants().items()
                if not key.startswith("goal_")
            ),
            "bounded_audit_state": all(
                checks["bounded_goal_plan_audit"] for checks in invariant_sets
            ),
        }

        for name, passed in {**scenarios, **invariants}.items():
            if not passed:
                diagnostics[name] = "deterministic contract check failed"

    return {
        "passed": all(scenarios.values()) and all(invariants.values()),
        "scenario_count": len(scenarios),
        "scenarios_passed": sum(scenarios.values()),
        "scenarios": scenarios,
        "invariant_count": len(invariants),
        "invariants_passed": sum(invariants.values()),
        "invariants": invariants,
        "diagnostics": diagnostics,
    }
