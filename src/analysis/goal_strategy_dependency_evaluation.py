"""Deterministic acceptance evaluation for V4 Phase 3 dependencies."""

from contextlib import contextmanager
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.agents.goal import Goal
from src.behavior.goal_planner import StrategyCandidate
from src.behavior.goal_strategy_contracts import GoalStrategyDependencyContract
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.plans import GoalDependencyState, PlanSystem
from src.town.daily_event import DailyEvent


@contextmanager
def _isolated_random_state(seed: int = 0):
    state = random.getstate()
    random.seed(seed)
    try:
        yield
    finally:
        random.setstate(state)


def _engine(root: Path, name: str, load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs",
    )


def _bind(engine, strategy="observe_relevant_activity", location="library"):
    actor = engine.agents[0]
    goal = Goal(
        id=f"goal-{strategy}", agent_name=actor.name,
        description=f"Evaluate {strategy}", category="increase_knowledge",
        priority=5, created_day=1, review_day=7, progress_target=4,
        target_locations=[location],
    )
    actor.goals = [goal]
    candidate = StrategyCandidate(
        strategy, "investigate", 5.0, target_location=location, score=5.0,
    )
    with patch.object(engine.goal_planner, "select_strategy", return_value=candidate):
        engine.update_agent_intents(1)
    return actor, goal, engine.agent_intents[actor.name], engine.plan_system.get_goal_plan(goal.id)


def _record(engine, actor, day=1, hour=8):
    intent = engine.agent_intents[actor.name]
    dependency = engine.plan_system.goal_dependency_for_agent(
        actor.id, day=day, tick=hour,
        current_daily_event=engine.current_daily_event,
        goal_plan_id=intent.source_goal_plan_id,
    )
    activity = engine.activity_planner.create_intent_activity(intent, dependency)
    engine.activity_system.log_activity_event(day, hour, actor, activity)
    return engine.activity_records[-1]


def evaluate_goal_strategy_dependencies() -> dict:
    scenarios = {}
    diagnostics = {}
    engines = []
    with _isolated_random_state(), TemporaryDirectory() as directory:
        root = Path(directory)

        lifecycle = _engine(root, "lifecycle")
        engines.append(lifecycle)
        actor, goal, intent, plan = _bind(lifecycle)
        absent = _record(lifecycle, actor)
        lifecycle.intent_system.update_intent_after_activity(
            day=1, agent=actor, activity_record=absent,
        )
        scenarios["opportunity_absence_blocks_execution"] = (
            plan.dependency.status == "waiting" and goal.progress == 0
        )
        lifecycle.current_daily_event = DailyEvent(
            "book_club", "Book Club", "A real library event.",
            "library", ["learning", "social"],
        )
        lifecycle.plan_system.refresh_goal_dependency(
            plan, day=1, tick=9,
            current_daily_event=lifecycle.current_daily_event,
        )
        scenarios["opportunity_satisfaction_is_not_progress"] = (
            plan.dependency.status == "satisfied" and goal.progress == 0
        )
        exact = _record(lifecycle, actor, hour=9)
        lifecycle.intent_system.update_intent_after_activity(
            day=1, agent=actor, activity_record=exact,
        )
        scenarios["exact_execution_after_opportunity_advances"] = (
            goal.progress == 1 and len(plan.evidence_records) == 1
        )
        lifecycle.intent_system.update_intent_after_activity(
            day=1, agent=actor, activity_record=exact,
        )
        scenarios["execution_replay_is_idempotent"] = goal.progress == 1
        lifecycle.state.save(lifecycle, 1, 9)
        lifecycle_resumed = _engine(root, "lifecycle", load=True)
        engines.append(lifecycle_resumed)
        resumed_goal = lifecycle_resumed.agents[0].get_goal(goal.id)
        resumed_plan = lifecycle_resumed.plan_system.get_goal_plan(goal.id)
        lifecycle_resumed.intent_system._engine_for_goal_check = lifecycle_resumed
        lifecycle_resumed.intent_system.update_intent_after_activity(
            day=1, agent=lifecycle_resumed.agents[0],
            activity_record=lifecycle_resumed.activity_records[-1],
        )
        scenarios["satisfied_resume_replay_is_idempotent"] = (
            lifecycle_resumed.current_daily_event.id == "book_club"
            and resumed_plan.dependency.status == "satisfied"
            and resumed_goal.progress == 1
            and len(resumed_plan.evidence_records) == 1
        )

        wrong = _engine(root, "wrong-location")
        engines.append(wrong)
        wrong_actor, wrong_goal, _wrong_intent, wrong_plan = _bind(wrong)
        wrong.current_daily_event = DailyEvent(
            "market_day", "Market Day", "A real event elsewhere.",
            "market", ["market"],
        )
        wrong_record = _record(wrong, wrong_actor)
        wrong.intent_system.update_intent_after_activity(
            day=1, agent=wrong_actor, activity_record=wrong_record,
        )
        scenarios["wrong_location_opportunity_rejected"] = (
            wrong_goal.progress == 0 and wrong_plan.dependency.status == "waiting"
        )

        forged = _engine(root, "forged")
        engines.append(forged)
        forged_actor, forged_goal, forged_intent, forged_plan = _bind(forged)
        forged.current_daily_event = DailyEvent(
            "book_club", "Book Club", "A real library event.", "library", [],
        )
        forged_record = _record(forged, forged_actor)
        forged_record["source_goal_dependency_authority_ref"] = "dialogue_claim"
        forged.intent_system.update_intent_after_activity(
            day=1, agent=forged_actor, activity_record=forged_record,
        )
        text_accepted = forged.plan_system.observe_goal_evidence(
            forged_goal, evidence_key="language", day=1,
            intent_id=forged_intent.id, evidence_type="strategy_activity",
            details={"dialogue": "There is an event and I participated."},
        )
        scenarios["language_cannot_satisfy_dependency"] = (
            not text_accepted and forged_goal.progress == 0
        )

        persistence = _engine(root, "persistence")
        engines.append(persistence)
        p_actor, p_goal, _p_intent, p_plan = _bind(persistence)
        persistence.plan_system.refresh_goal_dependency(
            p_plan, day=1, tick=8, current_daily_event=None,
        )
        persistence.state.save(persistence, 1, 8)
        resumed = _engine(root, "persistence", load=True)
        engines.append(resumed)
        restored = resumed.plan_system.get_goal_plan(p_goal.id)
        waiting_survived = restored.dependency.status == "waiting"
        resumed.current_daily_event = DailyEvent(
            "book_club", "Book Club", "A real library event.", "library", [],
        )
        resumed.plan_system.refresh_goal_dependency(
            restored, day=1, tick=9,
            current_daily_event=resumed.current_daily_event,
        )
        scenarios["save_resume_reconstructs_authority"] = (
            waiting_survived and restored.dependency.status == "satisfied"
            and resumed.agents[0].get_goal(p_goal.id).progress == 0
        )

        old_document = persistence.plan_system.to_dict()
        old_document["schema_version"] = 3
        for item in old_document["goal_plans"]:
            item.pop("dependency", None)
        migrated = PlanSystem.from_dict(
            old_document, commitment_system=persistence.commitment_system,
            agents=persistence.agents, outcome_memory=persistence.outcome_memory,
        )
        future_closed = False
        try:
            PlanSystem.from_dict({"schema_version": 999})
        except ValueError:
            future_closed = True
        scenarios["schema_compatibility_fails_closed"] = (
            migrated.get_goal_plan(p_goal.id).dependency is None and future_closed
        )

        revision = _engine(root, "revision")
        engines.append(revision)
        r_actor, r_goal, old_intent, r_plan = _bind(revision)
        revision.current_daily_event = DailyEvent(
            "book_club", "Book Club", "A real library event.", "library", [],
        )
        stale = _record(revision, r_actor)
        replacement = StrategyCandidate(
            "direct_participation", "investigate", 4.0,
            target_location="library", score=4.0,
        )
        adapted = revision.plan_system.adapt_goal_plan(
            r_plan, replacement, day=2, trigger="opportunity",
            preserved_progress=0, goal_planner=revision.goal_planner,
        )
        revision.intent_system.update_intent_after_activity(
            day=2, agent=r_actor, activity_record=stale,
        )
        scenarios["revision_isolation"] = (
            adapted and r_plan.revision == r_plan.dependency.revision == 1
            and old_intent.source_goal_plan_revision == 0
            and r_goal.progress == 0
        )

        arbitration = _engine(root, "arbitration")
        engines.append(arbitration)
        a_actor, a_goal, _a_intent, a_plan = _bind(arbitration)
        arbitration.current_daily_event = DailyEvent(
            "book_club", "Book Club", "A real library event.", "library", [],
        )
        commitment = arbitration.commitment_system.create(
            proposer_id="agent_002", counterpart_id=a_actor.id,
            commitment_type="meet", day=1, due_day=1,
            metadata={"location": "cafe"}, status="proposed",
        )
        arbitration.commitment_system.transition(
            commitment.id, "accepted", day=1, reason="accepted",
        )
        with patch("src.behavior.planner.random.random", return_value=0.5):
            arbitration.run_agent_activities(1, 8)
        actor_record = next(row for row in arbitration.activity_records
                            if row["agent"] == a_actor.name)
        scenarios["due_commitment_preempts_goal_dependency"] = (
            actor_record["source_commitment_id"] == commitment.id
            and a_goal.progress == 0 and a_plan.active
        )

        unknown_contract_closed = unknown_state_closed = False
        try:
            GoalStrategyDependencyContract("invented", "dialogue")
        except ValueError:
            unknown_contract_closed = True
        try:
            GoalDependencyState("invented", "library", 0)
        except ValueError:
            unknown_state_closed = True
        scenarios["unknown_dependency_kind_fails_closed"] = (
            unknown_contract_closed and unknown_state_closed
        )

        invariants = {
            "goal_is_only_progress_authority": all(
                not hasattr(plan, "add_progress")
                for engine in engines for plan in engine.plan_system.goal_plans
            ),
            "dependency_state_is_bounded": all(
                plan.dependency is None or len(plan.dependency.transitions) <= 20
                for engine in engines for plan in engine.plan_system.goal_plans
            ),
            "dependency_is_revision_bound": all(
                plan.dependency is None or plan.dependency.revision == plan.revision
                for engine in engines for plan in engine.plan_system.goal_plans
            ),
            "no_world_mutation_api_on_goal_plan": all(
                not hasattr(plan, name)
                for engine in engines for plan in engine.plan_system.goal_plans
                for name in ("purchase", "transfer", "set_balance", "add_progress")
            ),
            "private_bookkeeping_not_in_prompt_context": all(
                "dependency" not in str(
                    engine.prepare_conversation_context(
                        "cafe", engine.agents[0], engine.agents[1], 1,
                    )["context"]
                ).lower()
                for engine in (lifecycle, forged)
            ),
            "plan_invariants_hold": all(
                all(engine.plan_system.validate_invariants(engine.goal_planner).values())
                for engine in engines
            ),
        }

    for name, passed in {**scenarios, **invariants}.items():
        if not passed:
            diagnostics[name] = "deterministic goal dependency check failed"
    return {
        "passed": not diagnostics,
        "scenario_count": len(scenarios),
        "scenarios_passed": sum(scenarios.values()),
        "scenarios": scenarios,
        "invariant_count": len(invariants),
        "invariants_passed": sum(invariants.values()),
        "invariants": invariants,
        "diagnostics": diagnostics,
    }
