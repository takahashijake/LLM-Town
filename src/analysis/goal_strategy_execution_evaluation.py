"""Deterministic acceptance evaluation for V4 strategy execution fidelity."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.agents.goal import Goal
from src.behavior.goal_planner import StrategyCandidate
from src.behavior.goal_strategy_contracts import (
    ACTIVITY_EXECUTION,
    GOAL_STRATEGY_EXECUTION_CONTRACTS,
    SOCIAL_EXECUTION,
    strategy_contract,
)
from src.llm.client import FakeLLMClient
from src.simulation.conversation_runner import ConversationRunner
from src.simulation.engine import SimulationEngine


@contextmanager
def _isolated_random_state(seed: int = 0):
    state = random.getstate()
    random.seed(seed)
    try:
        yield
    finally:
        random.setstate(state)


def _engine(root: Path, name: str, load: bool = False) -> SimulationEngine:
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs",
    )


def _bind(engine, strategy, *, target=None, location=None, goal_id=None):
    actor = engine.agents[0]
    contract = strategy_contract(strategy)
    category = (
        "repair_relationship" if strategy in {
            "direct_cooperation", "apologize_directly", "offer_help",
        } else "investigate" if strategy.startswith("ask_")
        or strategy in {"seek_information_at_location", "observe_relevant_activity"}
        else "socialize"
    )
    goal = Goal(
        id=goal_id or f"goal-{strategy}", agent_name=actor.name,
        description=f"Evaluate {strategy}", category=category, priority=5,
        created_day=1, review_day=7, progress_target=5,
        target_agents=[target] if target else [],
        target_locations=[location] if location else [],
    )
    actor.goals = [goal]
    candidate = StrategyCandidate(
        strategy, category, 5.0, target_agent=target,
        target_location=location, required_action=contract.required_social_action,
        score=5.0,
    )
    with patch.object(engine.goal_planner, "select_strategy", return_value=candidate):
        engine.update_agent_intents(1)
    intent = engine.agent_intents[actor.name]
    return actor, goal, intent, engine.plan_system.get_goal_plan(goal.id)


def _social(engine, actor, listener, action, key):
    return engine.update_intents_after_conversation(
        1, "cafe", actor, listener, action, 1, 1, [action], key,
    )


def _activity(engine, actor, day=1, hour=8):
    intent = engine.agent_intents[actor.name]
    activity = engine.activity_planner.create_intent_activity(intent)
    engine.activity_system.log_activity_event(day, hour, actor, activity)
    return engine.activity_records[-1]


def evaluate_goal_strategy_execution() -> dict:
    scenarios: dict[str, bool] = {}
    diagnostics: dict[str, str] = {}
    engines = []
    with _isolated_random_state(), TemporaryDirectory() as directory:
        root = Path(directory)
        social_exact = social_wrong = target_exact = target_wrong = True
        social_strategies = [
            name for name, contract in GOAL_STRATEGY_EXECUTION_CONTRACTS.items()
            if contract.execution_mode == SOCIAL_EXECUTION
        ]
        for index, strategy in enumerate(social_strategies):
            engine = _engine(root, f"social-{index}")
            engines.append(engine)
            actor, selected, wrong = engine.agents[:3]
            contract = strategy_contract(strategy)
            target = None if strategy == "low_risk_chat" else selected.name
            actor, goal, _intent, plan = _bind(engine, strategy, target=target)
            _social(engine, actor, selected, "share_rumor", f"wrong:{strategy}")
            social_wrong &= goal.progress == 0 and not plan.evidence_records
            if target:
                _social(engine, actor, wrong, contract.required_social_action,
                        f"wrong-target:{strategy}")
                target_wrong &= goal.progress == 0
            _social(engine, actor, selected, contract.required_social_action,
                    f"exact:{strategy}")
            social_exact &= goal.progress > 0 and len(plan.evidence_records) == 1
            target_exact &= (
                not target or plan.evidence_records[0]["target_agent"] == target
            )
        scenarios["exact_social_action_proof"] = social_exact
        scenarios["wrong_social_action_rejection"] = social_wrong
        scenarios["wrong_target_rejection"] = target_wrong and target_exact

        location_exact = location_presence = cross_strategy = True
        location_strategies = [
            name for name, contract in GOAL_STRATEGY_EXECUTION_CONTRACTS.items()
            if contract.execution_mode == ACTIVITY_EXECUTION
        ]
        for index, strategy in enumerate(location_strategies):
            engine = _engine(root, f"location-{index}")
            engines.append(engine)
            actor, goal, _intent, plan = _bind(
                engine, strategy, location="library",
            )
            generic = {
                "type": "activity", "day": 1, "hour": 7,
                "agent": actor.name, "activity_id": "learn",
                "activity_name": "Generic library activity", "location": "library",
                "tags": ["knowledge"],
            }
            engine.intent_system.update_intent_after_activity(
                day=1, agent=actor, activity_record=generic,
            )
            location_presence &= goal.progress == 0
            record = _activity(engine, actor)
            if strategy == "observe_relevant_activity":
                crossed = dict(record)
                other = strategy_contract("seek_information_at_location")
                crossed.update({
                    "activity_id": other.activity_id,
                    "source_goal_strategy": other.strategy,
                    "tags": list(other.required_activity_tags),
                })
                engine.intent_system.update_intent_after_activity(
                    day=1, agent=actor, activity_record=crossed,
                )
                cross_strategy &= goal.progress == 0
            engine.intent_system.update_intent_after_activity(
                day=1, agent=actor, activity_record=record,
            )
            location_exact &= goal.progress == 1 and len(plan.evidence_records) == 1
        scenarios["location_strategy_distinction"] = location_exact and location_presence
        scenarios["cross_strategy_rejection"] = cross_strategy

        revision = _engine(root, "revision")
        engines.append(revision)
        actor, target = revision.agents[:2]
        actor, goal, old_intent, plan = _bind(
            revision, "direct_cooperation", target=target.name,
        )
        replacement = StrategyCandidate(
            "apologize_directly", "repair_relationship", 4.0,
            target_agent=target.name, required_action="apologize", score=4.0,
        )
        revision.plan_system.adapt_goal_plan(
            plan, replacement, day=2, trigger="relationship",
            preserved_progress=0, goal_planner=revision.goal_planner,
        )
        _social(revision, actor, target, "cooperate", "delayed-r0")
        social_revision_isolated = (
            goal.progress == 0 and old_intent.source_goal_plan_revision == 0
            and plan.revision == 1
        )
        revision_activity = _engine(root, "revision-activity")
        engines.append(revision_activity)
        actor, goal, _intent, plan = _bind(
            revision_activity, "seek_information_at_location", location="library",
        )
        stale_record = _activity(revision_activity, actor)
        revision_activity.plan_system.adapt_goal_plan(
            plan,
            StrategyCandidate(
                "observe_relevant_activity", "investigate", 4.0,
                target_location="library", score=4.0,
            ),
            day=2, trigger="hard_constraint", preserved_progress=0,
            goal_planner=revision_activity.goal_planner,
        )
        revision_activity.intent_system.update_intent_after_activity(
            day=2, agent=actor, activity_record=stale_record,
        )
        scenarios["plan_revision_isolation"] = (
            social_revision_isolated and goal.progress == 0
            and not plan.evidence_records
        )

        isolation = _engine(root, "isolation")
        engines.append(isolation)
        actor, goal, _intent, plan = _bind(
            isolation, "seek_information_at_location", location="library",
        )
        record = _activity(isolation, actor)
        wrong_goal = dict(record, source_goal_id="goal-other")
        isolation.intent_system.update_intent_after_activity(
            day=1, agent=actor, activity_record=wrong_goal,
        )
        wrong_plan = dict(record, source_goal_plan_id="plan:goal:other:other")
        isolation.intent_system.update_intent_after_activity(
            day=1, agent=actor, activity_record=wrong_plan,
        )
        scenarios["goal_plan_source_isolation"] = goal.progress == 0

        replay = _engine(root, "replay")
        engines.append(replay)
        actor, goal, _intent, plan = _bind(
            replay, "seek_information_at_location", location="library",
        )
        record = _activity(replay, actor)
        replay.intent_system.update_intent_after_activity(
            day=1, agent=actor, activity_record=record,
        )
        replay.intent_system.update_intent_after_activity(
            day=1, agent=actor, activity_record=record,
        )
        scenarios["evidence_replay"] = goal.progress == 1 and len(plan.evidence_records) == 1
        replay.state.save(replay, 1, 8)
        resumed = _engine(root, "replay", load=True)
        engines.append(resumed)
        resumed.intent_system.update_intent_after_activity(
            day=1, agent=resumed.agents[0],
            activity_record=resumed.activity_records[-1],
        )
        scenarios["save_resume_replay"] = (
            resumed.agents[0].get_goal(goal.id).progress == 1
            and len(resumed.plan_system.get_goal_plan(goal.id).evidence_records) == 1
        )

        terminal = _engine(root, "terminal")
        engines.append(terminal)
        actor, target = terminal.agents[:2]
        actor, goal, intent, plan = _bind(
            terminal, "direct_cooperation", target=target.name,
        )
        text_accepted = terminal.plan_system.observe_goal_evidence(
            goal, evidence_key="model-claim", day=1, intent_id=intent.id,
            evidence_type="social_action", details={"dialogue": "I cooperated."},
        )
        goal.status = "blocked"
        terminal.plan_system.synchronize_goal_plan(goal, day=2)
        _social(terminal, actor, target, "cooperate", "after-terminal")
        scenarios["terminal_plan_rejection"] = (
            not text_accepted and goal.progress == 0 and plan.status == "blocked"
        )
        scenarios["authority_independence"] = not text_accepted

        commitment = _engine(root, "commitment")
        engines.append(commitment)
        actor, goal, _intent, plan = _bind(
            commitment, "direct_participation", location="cafe",
        )
        item = commitment.commitment_system.create(
            proposer_id="agent_002", counterpart_id=actor.id,
            commitment_type="meet", day=1, due_day=1,
            metadata={"location": "cafe"}, status="proposed",
        )
        commitment.commitment_system.transition(
            item.id, "accepted", day=1, reason="accepted",
        )
        with patch("src.behavior.planner.random.random", return_value=0.0):
            commitment.run_agent_activities(1, 8)
        actor_record = next(
            row for row in commitment.activity_records
            if row["day"] == 1 and row["hour"] == 8 and row["agent"] == actor.name
        )
        scenarios["commitment_preemption"] = (
            actor_record["source_commitment_id"] == item.id
            and goal.progress == 0 and not plan.evidence_records
        )

        authority = _engine(root, "authority")
        engines.append(authority)
        actor, target = authority.agents[:2]
        actor, goal, _intent, _plan = _bind(
            authority, "direct_cooperation", target=target.name,
        )
        before = {
            "relationships": deepcopy(authority.relationships.scores),
            "economy": authority.economy.to_dict(),
            "materials": authority.materials.to_dict(),
            "commitments": authority.commitment_system.to_dict(),
            "crime": authority.crime.to_dict(),
            "justice": authority.justice.to_dict(),
            "memory": [len(agent.memory) for agent in authority.agents],
        }
        _social(authority, actor, target, "cooperate", "authority-proof")
        after = {
            "relationships": deepcopy(authority.relationships.scores),
            "economy": authority.economy.to_dict(),
            "materials": authority.materials.to_dict(),
            "commitments": authority.commitment_system.to_dict(),
            "crime": authority.crime.to_dict(),
            "justice": authority.justice.to_dict(),
            "memory": [len(agent.memory) for agent in authority.agents],
        }
        scenarios["existing_world_authorities_unchanged"] = before == after

        replica = ConversationRunner._make_realization_replica(authority)
        invariant_sets = [
            engine.plan_system.validate_invariants(engine.goal_planner)
            for engine in engines
        ]
        invariants = {
            "strategy_execution_requires_matching_contract": social_exact and location_exact,
            "wrong_action_does_not_advance": social_wrong,
            "wrong_target_does_not_advance": target_wrong,
            "location_presence_alone_is_not_proof": location_presence,
            "strategy_proof_cannot_cross_credit": cross_strategy,
            "stale_revision_proof_is_rejected": scenarios["plan_revision_isolation"],
            "evidence_replay_is_idempotent": scenarios["evidence_replay"],
            "save_resume_replay_is_idempotent": scenarios["save_resume_replay"],
            "goal_remains_progress_authority": all(
                not hasattr(plan, "add_progress")
                for engine in engines for plan in engine.plan_system.goal_plans
            ),
            "plan_cannot_invent_goal_evidence": not text_accepted,
            "llm_text_is_not_execution_proof": not text_accepted,
            "commitment_preemption_does_not_cross_credit": scenarios["commitment_preemption"],
            "terminal_plans_do_not_reopen": scenarios["terminal_plan_rejection"],
            "parallel_workers_have_no_plan_mutation_authority": replica.plan_system is None,
            "existing_world_authorities_are_unchanged": scenarios[
                "existing_world_authorities_unchanged"
            ],
            "finite_contract_covers_all_strategies": len(
                GOAL_STRATEGY_EXECUTION_CONTRACTS
            ) == 10,
            "plan_invariants_hold": all(all(checks.values()) for checks in invariant_sets),
        }

    for name, passed in {**scenarios, **invariants}.items():
        if not passed:
            diagnostics[name] = "deterministic strategy-execution check failed"
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
