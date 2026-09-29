"""Deterministic acceptance evaluation for V4 Phase 6 delegation."""

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.agents.goal import Goal
from src.agents.memory import Memory
from src.behavior.goal_planner import StrategyCandidate
from src.behavior.goal_strategy_contracts import strategy_contract
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.plans import PLAN_SCHEMA_VERSION, PlanSystem
from src.town.daily_event import DailyEvent


STRATEGY = "request_research_help"
TASK_CODE = "goal_research_help"


class _AcceptingFakeLLM(FakeLLMClient):
    def generate_conversation(self, context: dict) -> str:
        if context.get("session_transcript"):
            return json.dumps({
                "dialogue": "Yes, I can help with that tomorrow.",
                "action": "offer_help",
            })
        return super().generate_conversation(context)


@contextmanager
def _isolated_random_state(seed: int = 0):
    state = random.getstate()
    random.seed(seed)
    try:
        yield
    finally:
        random.setstate(state)


def _engine(root: Path, name: str, *, accepting=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=False,
        llm_client=_AcceptingFakeLLM() if accepting else FakeLLMClient(),
        state_path=root / f"{name}.json", logs_dir=root / f"{name}-logs",
    )


def _bind(engine, goal_id: str):
    owner, helper = engine.agents[:2]
    goal = Goal(
        id=goal_id, agent_name=owner.name, description="Investigate with research help",
        category="investigate", priority=5, created_day=1, review_day=7,
        progress_target=3, target_locations=["library"],
    )
    owner.goals = [goal]
    candidate = StrategyCandidate(
        STRATEGY, "investigate", 5.0, target_agent=helper.name,
        target_location="library", required_action="ask_for_help", score=5.0,
    )
    original = engine.goal_planner.select_strategy
    with patch.object(
        engine.goal_planner, "select_strategy",
        side_effect=lambda selected, agent, world: (
            candidate if selected.id == goal.id else original(selected, agent, world)
        ),
    ):
        engine.update_agent_intents(1)
    return owner, helper, goal, engine.plan_system.get_goal_plan(goal.id)


def _provenance(engine):
    request = engine.plan_system.delegation_requests()[0]
    keys = (
        "owner_id", "source_goal_id", "plan_id", "revision", "strategy",
        "helper_id", "task_code", "target_location", "request_id",
    )
    return {key: request[key] for key in keys}


def _respond(engine, owner, helper, outcome="accepted"):
    proof = _provenance(engine)
    engine.plan_system.record_delegation_request(
        proof, day=1, tick=8, session_id="evaluation-session",
    )
    item = engine.commitment_system.process_response(
        proposer_id=owner.id, counterpart_id=helper.id,
        proposal_text="Could you help me with research at the library tomorrow?",
        response_text="Yes, I can help." if outcome == "accepted" else "No.",
        outcome=outcome, day=1, tick=8, session_id="evaluation-session",
        proposal_turn=0, response_turn=1, bounded_goal_delegation=proof,
    )
    engine.plan_system.link_delegation_commitment(
        proof, item, day=1, tick=8,
    )
    return item


def _fulfill(engine, owner, helper, item, *, consume=True):
    owner.location_id = helper.location_id = "library"
    engine.plan_system.ensure_commitment_plans(2)
    opportunity = next(row for row in engine.plan_system.opportunities_for_agent(
        helper.id, day=2, tick=8,
    ) if row.commitment_id == item.id)
    activity = engine.activity_planner.create_commitment_activity(helper, opportunity)
    record = {"activity_id": activity.id, "location": activity.location_id}
    execution = engine.commitment_system.execute_activity(
        commitment_id=item.id, agent_id=helper.id, day=2, tick=8,
        activity_record=record,
    )
    engine.plan_system.record_execution(
        opportunity.plan_id, opportunity.step_id, day=2, tick=8,
        execution_key=execution["event_key"], source_commitment_id=item.id,
        action_type=activity.id,
    )
    outcomes = (engine.plan_system.consume_delegation_outcomes(day=2, tick=8)
                if consume else [])
    return opportunity, activity, execution, outcomes


def _trace(root: Path, name: str):
    engine = _engine(root, name)
    owner, helper, goal, plan = _bind(engine, "trace-goal")
    item = _respond(engine, owner, helper)
    opportunity, activity, execution, outcomes = _fulfill(
        engine, owner, helper, item,
    )
    return (
        plan.strategy_name, plan.delegation.helper_id, item.commitment_type,
        opportunity.action_type, activity.id, execution["event_key"],
        goal.progress, len(outcomes), tuple(plan.processed_evidence_keys),
    )


def evaluate_goal_delegation() -> dict:
    scenarios: dict[str, bool] = {}
    diagnostics = {}
    engines = []
    with _isolated_random_state(), TemporaryDirectory() as directory:
        root = Path(directory)

        selectable = _engine(root, "selectable")
        engines.append(selectable)
        actor = selectable.agents[0]
        selection_goal = Goal(
            id="selection", agent_name=actor.name, description="Learn",
            category="increase_knowledge", priority=5, created_day=1,
            review_day=7, target_locations=["library"],
        )
        candidates = selectable.goal_planner.generate_strategies(
            selection_goal, actor, selectable,
        )
        candidate = next(row for row in candidates if row.name == STRATEGY)
        expected_helper = selectable.goal_planner._best_social_target(
            actor, selectable,
            [agent.name for agent in selectable.agents if agent.id != actor.id],
        )
        scenarios["delegation_strategy_is_finite_and_selectable"] = (
            strategy_contract(STRATEGY) is not None and candidate.feasible
        )
        scenarios["helper_selection_is_deterministic"] = (
            candidate.target_agent == expected_helper
        )

        accepted = _engine(root, "accepted")
        engines.append(accepted)
        owner, helper, goal, plan = _bind(accepted, "accepted-goal")
        request = _provenance(accepted)
        accepted.plan_system.record_delegation_request(
            request, day=1, tick=8, session_id="issued",
        )
        scenarios["request_action_alone_gives_zero_progress"] = goal.progress == 0
        accepted.plan_system.mark_delegation_waiting(request, day=1, tick=8)
        scenarios["unaccepted_request_gives_zero_progress"] = goal.progress == 0
        # Restore a fresh world because issued requests deliberately cannot retry.
        accepted = _engine(root, "accepted-real")
        engines.append(accepted)
        owner, helper, goal, plan = _bind(accepted, "accepted-real-goal")
        item = _respond(accepted, owner, helper)
        scenarios["accepted_request_creates_exactly_one_help_commitment"] = (
            len(accepted.commitment_system.commitments) == 1
            and item.commitment_type == "help"
        )
        scenarios["commitment_orientation_is_requester_to_obligated_helper"] = (
            item.proposer_id == owner.id and item.counterpart_id == helper.id
        )
        binding_keys = set(vars(plan.delegation))
        scenarios["goal_plan_stores_only_bounded_linkage"] = (
            "evidence" not in binding_keys and "metadata" not in binding_keys
            and plan.delegation.linked_commitment_id == item.id
        )
        accepted.plan_system.ensure_commitment_plans(2)
        helper_ops = accepted.plan_system.opportunities_for_agent(
            helper.id, day=2, tick=8,
        )
        scenarios["helper_receives_normal_v3_opportunity"] = (
            len(helper_ops) == 1 and helper_ops[0].action_type == "commitment_help"
        )
        scenarios["requester_cannot_fulfill_helper_obligation"] = (
            accepted.plan_system.opportunities_for_agent(owner.id, day=2, tick=8) == []
        )
        scenarios["accepted_but_unfulfilled_gives_zero_progress"] = goal.progress == 0
        relationship_before = accepted.relationships.get_score(owner.name, helper.name)
        opportunity, activity, execution, outcomes = _fulfill(
            accepted, owner, helper, item,
        )
        scenarios["helper_executes_normal_commitment_help"] = (
            activity.id == "commitment_help"
            and execution["source_commitment_id"] == item.id
        )
        scenarios["fulfillment_advances_requester_goal_once"] = (
            item.status == "fulfilled" and goal.progress == 1 and len(outcomes) == 1
        )
        scenarios["duplicate_fulfillment_observation_cannot_double_progress"] = (
            accepted.plan_system.consume_delegation_outcomes(day=2, tick=9) == []
            and goal.progress == 1
        )
        duplicate = accepted.commitment_system.process_response(
            proposer_id=owner.id, counterpart_id=helper.id,
            proposal_text="Could you help me with research at the library tomorrow?",
            response_text="Yes", outcome="accepted", day=1, tick=8,
            session_id="evaluation-session", proposal_turn=0, response_turn=1,
            bounded_goal_delegation=item.metadata["goal_delegation"],
        )
        scenarios["duplicate_response_cannot_create_duplicate_commitment"] = (
            duplicate.id == item.id and len(accepted.commitment_system.commitments) == 1
        )
        scenarios["v3_relationship_effect_occurs_exactly_once"] = (
            accepted.relationships.get_score(owner.name, helper.name)
            == relationship_before + 1 and item.consequence_applied
        )
        accepted.plan_system.consume_delegation_outcomes(day=3, tick=8)
        scenarios["goal_integration_does_not_duplicate_social_effects"] = (
            accepted.relationships.get_score(owner.name, helper.name)
            == relationship_before + 1
        )

        runtime = _engine(root, "normal-runtime")
        engines.append(runtime)
        r_owner, r_helper, r_goal, r_plan = _bind(runtime, "normal-runtime-goal")
        r_item = _respond(runtime, r_owner, r_helper)
        r_owner.location_id = r_helper.location_id = "library"
        runtime.current_daily_event = DailyEvent(
            "research_day", "Research day", "Residents study together.",
            "library", ["learning"],
        )
        with patch("random.random", return_value=0.1):
            runtime.run_agent_activities(2, 8)
        r_record = next(row for row in runtime.activity_records
                        if row["day"] == 2 and row["hour"] == 8
                        and row["agent"] == r_helper.name)
        scenarios["normal_runtime_completes_full_vertical_slice"] = (
            r_record["activity_id"] == "commitment_help"
            and r_item.status == "fulfilled" and r_goal.progress == 1
            and len(r_plan.evidence_records) == 1
        )

        restored = PlanSystem.from_dict(
            deepcopy(accepted.plan_system.to_dict()),
            commitment_system=accepted.commitment_system, agents=accepted.agents,
            outcome_memory=accepted.outcome_memory, materials=accepted.materials,
        )
        scenarios["save_resume_after_acceptance_retains_binding"] = (
            restored.get_goal_plan(goal.id).delegation.linked_commitment_id == item.id
        )
        restored.get_goal_plan(goal.id).delegation.status = "accepted"
        scenarios["save_resume_rechecks_real_commitment_authority"] = (
            restored.refresh_goal_delegation(
                restored.get_goal_plan(goal.id), day=3, tick=8,
            ) == "fulfilled"
        )
        scenarios["save_resume_after_fulfillment_cannot_replay_progress"] = (
            restored.consume_delegation_outcomes(day=3, tick=8) == []
            and goal.progress == 1
        )

        for status in ("declined", "failed", "expired", "cancelled"):
            world = _engine(root, f"terminal-{status}")
            engines.append(world)
            term_owner, term_helper, term_goal, term_plan = _bind(
                world, f"terminal-{status}-goal",
            )
            terminal = _respond(
                world, term_owner, term_helper,
                outcome="declined" if status == "declined" else "accepted",
            )
            if status != "declined":
                world.commitment_system.transition(
                    terminal.id, status, day=2, tick=8, reason=f"evaluation_{status}",
                    evidence=({"session_id": "cancel", "turn_index": 0}
                              if status == "cancelled" else None),
                )
            scenarios[f"{status}_commitment_gives_no_progress"] = (
                world.plan_system.consume_delegation_outcomes(day=2, tick=8) == []
                and term_goal.progress == 0
            )
            if status == "declined":
                old_revision = term_plan.revision
                world.update_agent_intents(2)
                scenarios["terminal_failure_permits_bounded_adaptation"] = (
                    term_plan.revision == old_revision + 1
                    and not (
                        term_plan.strategy_name == STRATEGY
                        and term_plan.target_agent == term_helper.name
                    )
                )

        stale = _engine(root, "stale")
        engines.append(stale)
        stale_owner, stale_helper, stale_goal, stale_plan = _bind(stale, "stale-goal")
        stale_item = _respond(stale, stale_owner, stale_helper)
        replacement = next(row for row in stale.goal_planner.generate_strategies(
            stale_goal, stale_owner, stale,
        ) if row.name == "seek_information_at_location")
        stale.plan_system.adapt_goal_plan(
            stale_plan, replacement, day=2, trigger="evaluation",
            preserved_progress=0, goal_planner=stale.goal_planner,
        )
        _fulfill(stale, stale_owner, stale_helper, stale_item, consume=False)
        scenarios["stale_revision_fulfillment_does_not_cross_credit"] = (
            stale.plan_system.consume_delegation_outcomes(day=2, tick=8) == []
            and stale_goal.progress == 0 and stale_item.status == "fulfilled"
        )

        provenance_world = _engine(root, "provenance")
        engines.append(provenance_world)
        p_owner, p_helper, p_goal, _p_plan = _bind(
            provenance_world, "provenance-goal",
        )
        base = _provenance(provenance_world)
        for scenario, field, value in (
            ("cross_goal_commitment_does_not_cross_credit", "source_goal_id", "other"),
            ("cross_plan_commitment_does_not_cross_credit", "plan_id", "other"),
            ("cross_owner_commitment_does_not_cross_credit", "owner_id", "agent_999"),
            ("wrong_helper_does_not_cross_credit", "helper_id", "agent_003"),
            ("wrong_task_does_not_cross_credit", "task_code", "wrong"),
        ):
            forged = dict(base)
            forged[field] = value
            scenarios[scenario] = not provenance_world.plan_system.record_delegation_request(
                forged, day=1, tick=8, session_id="forged",
            )
        ordinary = provenance_world.commitment_system.create(
            proposer_id=p_owner.id, counterpart_id=p_helper.id,
            commitment_type="help", status="accepted", day=1, due_day=2,
            metadata={"task": "help with research", "location": "library"},
        )
        _fulfill(provenance_world, p_owner, p_helper, ordinary, consume=False)
        scenarios["ordinary_help_commitment_does_not_cross_credit"] = (
            provenance_world.plan_system.consume_delegation_outcomes(
                day=2, tick=8,
            ) == [] and p_goal.progress == 0
        )
        p_owner.remember(Memory(
            day=2, hour=8, type="conversation", description="Help was fulfilled.",
            participants=[p_owner.name], location="library", importance=3,
            sentiment=1, tags=["claim"],
        ))
        scenarios["generated_dialogue_cannot_fabricate_fulfillment"] = p_goal.progress == 0
        scenarios["memory_cannot_substitute_for_commitment_authority"] = p_goal.progress == 0

        forged_world = _engine(root, "forged-execution")
        engines.append(forged_world)
        f_owner, f_helper, f_goal, _ = _bind(forged_world, "forged-execution-goal")
        f_item = _respond(forged_world, f_owner, f_helper)
        forged_world.commitment_system.transition(
            f_item.id, "fulfilled", day=2, tick=8, reason="forged",
            evidence={"activity_event_key": "forged"},
        )
        scenarios["forged_activity_record_cannot_progress_goal"] = (
            forged_world.plan_system.consume_delegation_outcomes(day=2, tick=8) == []
            and f_goal.progress == 0
        )

        concurrency = _engine(root, "conversation", accepting=True)
        engines.append(concurrency)
        c_owner, c_helper, c_goal, c_plan = _bind(concurrency, "conversation-goal")
        c_owner.location_id = c_helper.location_id = "library"
        concurrency.agents[2].location_id = "town_square"
        concurrency.agents[3].location_id = "market"
        concurrency.conversation_runner.max_turns = 2
        concurrency.generate_conversations(1, 8)
        linked = [row for row in concurrency.commitment_system.commitments
                  if row.metadata.get("task_code") == TASK_CODE]
        scenarios["real_conversation_bridge_creates_one_commitment"] = len(linked) == 1
        log_text = concurrency.logger.events_file.read_text()
        scenarios["unrelated_residents_receive_no_private_plan_provenance"] = (
            "goal-delegation:" not in log_text and "source_goal_id" not in log_text
        )
        scenarios["conversation_snapshot_and_commit_order_remain_stable"] = (
            concurrency.last_social_tick["worker_failures"] == []
            and concurrency.last_social_tick["commit_order"]
            == concurrency.last_social_tick["schedule_order"]
        )

        priority = _engine(root, "priority")
        engines.append(priority)
        pr_owner, pr_helper, _pr_goal, _ = _bind(priority, "priority-goal")
        pr_item = _respond(priority, pr_owner, pr_helper)
        pr_owner.location_id = pr_helper.location_id = "library"
        priority.plan_system.ensure_commitment_plans(2)
        pr_op = priority.plan_system.opportunities_for_agent(
            pr_helper.id, day=2, tick=8,
        )[0]
        with patch("random.random", return_value=0.5):
            chosen = priority.activity_planner.choose_activity(
                pr_helper, [row.id for row in priority.locations], 2, 8,
                current_intent=priority.agent_intents.get(pr_helper.name),
                commitment_opportunities=[pr_op],
            )
        scenarios["v3_commitment_priority_and_arbitration_are_unchanged"] = (
            chosen.id == "commitment_help"
        )
        scenarios["urgent_commitment_can_preempt_ordinary_behavior"] = (
            chosen.source_commitment_id == pr_item.id
        )
        scenarios["helper_own_goal_survives_pending_commitment"] = (
            bool(pr_helper.get_active_goals()) and pr_item.status == "accepted"
        )

        v6 = deepcopy(priority.plan_system.to_dict())
        v6["schema_version"] = 6
        v6["goal_plans"] = [
            row for row in v6["goal_plans"]
            if row.get("strategy_name") != STRATEGY
        ]
        for row in v6["goal_plans"]:
            row.pop("delegation", None)
        migrated = PlanSystem.from_dict(
            v6, commitment_system=priority.commitment_system,
            agents=priority.agents, outcome_memory=priority.outcome_memory,
            materials=priority.materials,
        )
        scenarios["schema_six_migrates_without_fabricated_delegation"] = (
            all(row.delegation is None for row in migrated.goal_plans)
        )
        scenarios["deterministic_repeated_runs_are_equivalent"] = (
            _trace(root, "repeat-a") == _trace(root, "repeat-b")
        )

        from src.analysis.commitment_execution_evaluation import (
            run_commitment_execution_evaluation,
        )
        from src.analysis.commitment_semantics_evaluation import (
            run_commitment_semantics_evaluation,
        )
        scenarios["existing_v3_commitment_evaluators_still_pass"] = all((
            run_commitment_semantics_evaluation()["result"] == "PASS",
            run_commitment_execution_evaluation(root / "v3-execution")["passed"],
        ))

        invariants = {
            "schema_version_is_seven": PLAN_SCHEMA_VERSION == 7,
            "delegation_histories_are_bounded": all(
                plan.delegation is None or len(plan.delegation.transitions) <= 20
                for world in engines for plan in world.plan_system.goal_plans
            ),
            "one_binding_has_at_most_one_commitment": all(
                plan.delegation is None or isinstance(
                    plan.delegation.linked_commitment_id, (str, type(None)),
                ) for world in engines for plan in world.plan_system.goal_plans
            ),
            "commitment_execution_keys_are_unique": all(
                len({row["event_key"] for row in world.commitment_system.execution_records})
                == len(world.commitment_system.execution_records)
                for world in engines
            ),
            "goal_evidence_keys_are_unique": all(
                len(plan.processed_evidence_keys) == len(set(plan.processed_evidence_keys))
                for world in engines for plan in world.plan_system.goal_plans
            ),
            "commitment_invariants_hold": all(
                all(world.commitment_system.validate_invariants().values())
                for world in engines
            ),
            "plan_invariants_hold": all(
                all(world.plan_system.validate_invariants(world.goal_planner).values())
                for world in engines
            ),
            "outcome_memory_invariants_hold": all(
                all(world.outcome_memory.validate().values()) for world in engines
            ),
        }

    for name, passed in {**scenarios, **invariants}.items():
        if not passed:
            diagnostics[name] = "deterministic goal delegation check failed"
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
