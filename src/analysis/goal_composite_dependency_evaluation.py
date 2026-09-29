"""Deterministic acceptance evaluation for V4 Phase 5 composite prerequisites."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.agents.goal import Goal
from src.behavior.goal_planner import StrategyCandidate
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.materials import MaterialError
from src.systems.plans import PlanSystem
from src.town.daily_event import DailyEvent


STRATEGY = "study_reference_material_at_active_location"
FINAL_ACTIVITY = "goal_study_reference_material_at_active_location"


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


def _bind(engine, goal_id: str):
    actor = engine.agents[0]
    goal = Goal(
        id=goal_id, agent_name=actor.name,
        description="Study owned reference material at a currently active location",
        category="increase_knowledge", priority=5, created_day=1,
        review_day=7, progress_target=4, target_locations=["library"],
    )
    actor.goals = [goal]
    candidate = StrategyCandidate(
        STRATEGY, "investigate", 5.0, target_location="library", score=6.0,
    )
    with patch.object(engine.goal_planner, "select_strategy", return_value=candidate):
        engine.update_agent_intents(1)
    return (
        actor, goal, engine.agent_intents[actor.name],
        engine.plan_system.get_goal_plan(goal.id),
    )


def _event(engine, event_id="book_club", location="library"):
    engine.current_daily_event = DailyEvent(
        event_id, "Current gathering", "A real current gathering.", location,
        ["learning"],
    )


def _grant(engine, actor, key: str):
    seller = engine.materials.sellers["seller:market_stall"]
    return engine.materials.transfer_good(
        seller.inventory_id, engine.materials.inventory_for_agent(actor.id).id,
        "reference_book", 1, day=1, hour=7, reason="authorized evaluation transfer",
        authorization_type="evaluation", authorization_id=key, event_key=key,
    )


def _prepare(engine, actor, day=1, hour=8):
    engine.activity_system.run_agent_activities(
        [actor], [item.id for item in engine.locations], day, hour,
        engine.current_daily_event, engine.agent_intents,
    )
    return engine.activity_records[-1]


def _proof(engine, actor, day=1, hour=9):
    intent = engine.agent_intents[actor.name]
    opportunity = engine.plan_system.goal_dependency_for_agent(
        actor.id, day=day, tick=hour,
        current_daily_event=engine.current_daily_event,
        goal_plan_id=intent.source_goal_plan_id,
    )
    activity = engine.activity_planner.create_intent_activity(intent, opportunity)
    engine.activity_system.log_activity_event(day, hour, actor, activity)
    return engine.activity_records[-1]


def _accept(engine, actor, record, day=1):
    engine.intent_system._engine_for_goal_check = engine
    return engine.intent_system.update_intent_after_activity(
        day=day, agent=actor, activity_record=record,
    )


def _deterministic_trace(root: Path, name: str) -> tuple:
    engine = _engine(root, name)
    actor, goal, intent, plan = _bind(engine, f"trace-{name}")
    record = _prepare(engine, actor)
    statuses = tuple(item.status for item in plan.dependencies)
    _event(engine)
    final = _proof(engine, actor, day=2, hour=8)
    _accept(engine, actor, final, day=2)
    return (
        record["activity_id"], statuses, final["activity_id"],
        goal.progress, intent.progress,
        tuple((item.kind, item.subject_id) for item in plan.dependencies),
    )


def evaluate_goal_composite_dependencies() -> dict:
    scenarios = {}
    diagnostics = {}
    engines = []
    with _isolated_random_state(), TemporaryDirectory() as directory:
        root = Path(directory)

        selectable = _engine(root, "selectable")
        engines.append(selectable)
        selectable_actor = selectable.agents[0]
        _grant(selectable, selectable_actor, "selectable:grant")
        _event(selectable)
        selectable_goal = Goal(
            id="selectable", agent_name=selectable_actor.name, description="Learn",
            category="increase_knowledge", priority=5, created_day=1,
            review_day=7, target_locations=["library"],
        )
        scenarios["composite_strategy_runtime_selectable"] = (
            selectable.goal_planner.select_strategy(
                selectable_goal, selectable_actor, selectable,
            ).name == STRATEGY
        )

        lifecycle = _engine(root, "lifecycle")
        engines.append(lifecycle)
        actor, goal, intent, plan = _bind(lifecycle, "composite-lifecycle")
        initial_currency = lifecycle.economy.total_currency()
        initial_materials = lifecycle.materials.total_quantities()
        initial = lifecycle.plan_system.goal_dependency_for_agent(
            actor.id, day=1, tick=7, current_daily_event=None,
            goal_plan_id=plan.id,
        )
        scenarios["missing_resource_absent_event_is_preparable_without_progress"] = (
            [item.status for item in initial.dependencies]
            == ["preparable", "waiting"] and goal.progress == 0
        )
        preparation = _prepare(lifecycle, actor)
        scenarios["successful_purchase_only_satisfies_resource"] = (
            preparation["activity_id"] == "goal_acquire_reference_book"
            and goal.progress == intent.progress == 0
        )
        after_purchase = lifecycle.plan_system.goal_dependency_for_agent(
            actor.id, day=1, tick=9, current_daily_event=None,
            goal_plan_id=plan.id,
        )
        scenarios["event_absence_after_purchase_blocks_final"] = (
            after_purchase.status == "waiting"
            and [item.status for item in after_purchase.dependencies]
            == ["satisfied", "waiting"]
        )
        scenarios["one_preparation_mutation_per_tick"] = (
            len(lifecycle.materials.exchanges) == 1
        )
        _event(lifecycle)
        ready = lifecycle.plan_system.goal_dependency_for_agent(
            actor.id, day=2, tick=8,
            current_daily_event=lifecycle.current_daily_event,
            goal_plan_id=plan.id,
        )
        scenarios["both_prerequisites_satisfied_enable_final"] = (
            ready.status == "satisfied"
        )
        scenarios["event_appearance_does_not_advance_progress"] = goal.progress == 0
        final = _proof(lifecycle, actor, day=2, hour=8)
        scenarios["exact_composite_activity_selected"] = (
            final["activity_id"] == FINAL_ACTIVITY
            and len(final["source_goal_dependencies"]) == 2
        )
        accepted = _accept(lifecycle, actor, final, day=2)
        scenarios["retained_ownership_and_later_event_permit_progress"] = (
            bool(accepted) and goal.progress == intent.progress == 1
        )
        _accept(lifecycle, actor, final, day=2)
        scenarios["final_evidence_replay_idempotent"] = (
            goal.progress == intent.progress == 1 and len(plan.evidence_records) == 1
        )
        exchange = lifecycle.materials.exchanges[0]
        replay_snapshot = (
            len(lifecycle.materials.exchanges), len(lifecycle.economy.ledger),
            lifecycle.economy.account_for_agent(actor.id).balance,
        )
        try:
            lifecycle.materials.purchase(
                exchange.buyer_inventory_id, exchange.buyer_account_id,
                exchange.seller_id, exchange.good_id, exchange.quantity,
                day=3, hour=8, event_key=exchange.event_key,
            )
        except MaterialError as error:
            replay_rejected = error.code == "duplicate_event"
        else:
            replay_rejected = False
        scenarios["purchase_replay_idempotent"] = replay_rejected and replay_snapshot == (
            len(lifecycle.materials.exchanges), len(lifecycle.economy.ledger),
            lifecycle.economy.account_for_agent(actor.id).balance,
        )

        stale_event = _engine(root, "stale-event")
        engines.append(stale_event)
        se_actor, se_goal, se_intent, _ = _bind(stale_event, "stale-event")
        _grant(stale_event, se_actor, "stale-event:grant")
        _event(stale_event)
        se_record = _proof(stale_event, se_actor)
        stale_event.current_daily_event = None
        _accept(stale_event, se_actor, se_record)
        scenarios["event_disappears_before_execution_rejected"] = (
            se_goal.progress == se_intent.progress == 0
        )

        stale_resource = _engine(root, "stale-resource")
        engines.append(stale_resource)
        sr_actor, sr_goal, sr_intent, _ = _bind(stale_resource, "stale-resource")
        _grant(stale_resource, sr_actor, "stale-resource:grant")
        _event(stale_resource)
        sr_record = _proof(stale_resource, sr_actor)
        seller = stale_resource.materials.sellers["seller:market_stall"]
        stale_resource.materials.transfer_good(
            stale_resource.materials.inventory_for_agent(sr_actor.id).id,
            seller.inventory_id, "reference_book", 1, day=1, hour=10,
            reason="authorized loss", authorization_type="evaluation",
            authorization_id="stale-resource:loss", event_key="stale-resource:loss",
        )
        _accept(stale_resource, sr_actor, sr_record)
        scenarios["resource_loss_after_satisfaction_rejected"] = (
            sr_goal.progress == sr_intent.progress == 0
        )

        external = _engine(root, "external")
        engines.append(external)
        ex_actor, ex_goal, ex_intent, _ = _bind(external, "external")
        _grant(external, ex_actor, "external:grant")
        _event(external)
        _accept(external, ex_actor, _proof(external, ex_actor))
        scenarios["external_authoritative_acquisition_accepted"] = (
            ex_goal.progress == ex_intent.progress == 1
            and not external.economy.ledger
        )

        blocked = _engine(root, "blocked")
        engines.append(blocked)
        blocked_seller = blocked.materials.sellers["seller:market_stall"]
        blocked.materials.sellers[blocked_seller.id] = replace(
            blocked_seller, active=False,
        )
        b_actor, b_goal, _b_intent, b_plan = _bind(blocked, "blocked")
        b_opportunity = blocked.plan_system.goal_dependency_for_agent(
            b_actor.id, day=1, tick=8, current_daily_event=None,
            goal_plan_id=b_plan.id,
        )
        scenarios["no_legal_route_is_blocked"] = b_opportunity.status == "blocked"
        candidates = blocked.goal_planner.generate_strategies(b_goal, b_actor, blocked)
        replacement = next(item for item in candidates
                           if item.name == "seek_information_at_location")
        adapted = blocked.plan_system.adapt_goal_plan(
            b_plan, replacement, day=2, trigger="hard_constraint",
            preserved_progress=0, goal_planner=blocked.goal_planner,
        )
        scenarios["bounded_adaptation_does_not_invent_resource"] = (
            adapted and not b_plan.dependencies
            and blocked.materials.inventory_for_agent(b_actor.id).quantity(
                "reference_book"
            ) == 0
        )

        provenance = _engine(root, "provenance")
        engines.append(provenance)
        p_actor, p_goal, p_intent, p_plan = _bind(provenance, "provenance")
        _grant(provenance, p_actor, "provenance:grant")
        _event(provenance)
        base = _proof(provenance, p_actor)
        mutations = {
            "cross_owner_evidence_rejected": ("agent", "Other resident"),
            "cross_goal_evidence_rejected": ("source_goal_id", "other-goal"),
            "cross_plan_evidence_rejected": ("source_goal_plan_id", "other-plan"),
            "cross_revision_evidence_rejected": ("source_goal_plan_revision", 99),
            "cross_intent_evidence_rejected": ("source_intent_id", "other-intent"),
        }
        for name, (field, value) in mutations.items():
            record = deepcopy(base)
            record[field] = value
            _accept(provenance, p_actor, record)
            scenarios[name] = p_goal.progress == p_intent.progress == 0
        wrong_resource = deepcopy(base)
        wrong_resource["source_goal_dependencies"][0]["subject_id"] = "wrong_good"
        _accept(provenance, p_actor, wrong_resource)
        scenarios["wrong_resource_rejected"] = p_goal.progress == 0
        wrong_event = deepcopy(base)
        wrong_event["source_goal_dependencies"][1]["authority_reference"] = "wrong_event"
        _accept(provenance, p_actor, wrong_event)
        scenarios["wrong_event_rejected"] = p_goal.progress == 0
        wrong_location = deepcopy(base)
        wrong_location["source_goal_dependencies"][1]["subject_id"] = "market"
        _accept(provenance, p_actor, wrong_location)
        scenarios["wrong_dependency_location_rejected"] = p_goal.progress == 0

        persistence = _engine(root, "persistence")
        engines.append(persistence)
        ps_actor, ps_goal, _ps_intent, _ps_plan = _bind(persistence, "persistence")
        _prepare(persistence, ps_actor)
        _event(persistence)
        persistence.state.save(persistence, 1, 9)
        resumed = _engine(root, "persistence", load=True)
        engines.append(resumed)
        resumed_plan = resumed.plan_system.get_goal_plan(ps_goal.id)
        resumed_states = resumed.plan_system.refresh_goal_dependency(
            resumed_plan, day=2, tick=8, current_daily_event=None,
        )
        scenarios["save_resume_rechecks_authorities"] = (
            [item.status for item in resumed_states] == ["satisfied", "waiting"]
        )

        version_five = lifecycle.plan_system.to_dict()
        old_plan = deepcopy(version_five["goal_plans"][0])
        old_plan["strategy_name"] = "study_reference_material"
        dependency = old_plan.pop("dependencies")[0]
        old_plan.pop("legacy_dependency_omitted", None)
        version_five["schema_version"] = 5
        version_five["goal_plans"] = [{**old_plan, "dependency": dependency}]
        migrated = PlanSystem.from_dict(
            version_five, commitment_system=lifecycle.commitment_system,
            agents=lifecycle.agents, outcome_memory=lifecycle.outcome_memory,
            materials=lifecycle.materials,
        )
        scenarios["version_five_singular_migrates_safely"] = (
            len(migrated.goal_plans[0].dependencies) == 1
            and migrated.goal_plans[0].dependencies[0].kind == "owned_good"
        )
        malformed = lifecycle.plan_system.to_dict()
        malformed["goal_plans"][0]["dependencies"].append(
            deepcopy(malformed["goal_plans"][0]["dependencies"][0])
        )
        try:
            PlanSystem.from_dict(
                malformed, commitment_system=lifecycle.commitment_system,
                agents=lifecycle.agents, materials=lifecycle.materials,
            )
        except ValueError:
            malformed_closed = True
        else:
            malformed_closed = False
        scenarios["malformed_composite_fails_closed"] = malformed_closed

        priority = _engine(root, "priority")
        engines.append(priority)
        pr_actor, pr_goal, pr_intent, pr_plan = _bind(priority, "priority")
        commitment = priority.commitment_system.create(
            proposer_id="agent_002", counterpart_id=pr_actor.id,
            commitment_type="meet", day=1, due_day=1,
            metadata={"location": "cafe"}, status="proposed",
        )
        priority.commitment_system.transition(
            commitment.id, "accepted", day=1, reason="accepted",
        )
        with patch("src.behavior.planner.random.random", return_value=0.5):
            priority_record = _prepare(priority, pr_actor)
        scenarios["due_v3_commitment_preempts_goal_activity"] = (
            priority_record["source_commitment_id"] == commitment.id
            and pr_goal.progress == pr_intent.progress == 0
            and [item.status for item in pr_plan.dependencies]
            == ["preparable", "waiting"]
        )
        scenarios["unrelated_prompt_has_no_private_composite_state"] = (
            "dependency" not in str(priority.prepare_conversation_context(
                "cafe", priority.agents[0], priority.agents[1], 1,
            )["context"]).lower()
            and STRATEGY not in str(priority.prepare_conversation_context(
                "cafe", priority.agents[0], priority.agents[1], 1,
            )["context"])
        )

        from src.analysis.goal_resource_dependency_evaluation import (
            evaluate_goal_resource_dependencies,
        )
        from src.analysis.goal_strategy_dependency_evaluation import (
            evaluate_goal_strategy_dependencies,
        )
        from src.analysis.goal_strategy_execution_evaluation import (
            evaluate_goal_strategy_execution,
        )
        from src.analysis.goal_planning_evaluation import evaluate_goal_planning

        scenarios["all_phase_one_through_four_evaluators_pass"] = all((
            evaluate_goal_planning()["passed"],
            evaluate_goal_strategy_execution()["passed"],
            evaluate_goal_strategy_dependencies()["passed"],
            evaluate_goal_resource_dependencies()["passed"],
        ))
        scenarios["deterministic_repeated_runs_equivalent"] = (
            _deterministic_trace(root, "repeat-a")
            == _deterministic_trace(root, "repeat-b")
        )

        invariants = {
            "currency_conserved": (
                lifecycle.economy.total_currency() == initial_currency
                and lifecycle.economy.conservation_holds()
            ),
            "materials_conserved": (
                lifecycle.materials.total_quantities() == initial_materials
                and lifecycle.materials.material_conservation_holds()
            ),
            "material_provenance_reconciles": (
                lifecycle.materials.provenance_reconciles()
            ),
            "ordered_dependency_bound_holds": all(
                len(item.dependencies) <= 2
                for world in engines for item in world.plan_system.goal_plans
            ),
            "dependency_histories_are_bounded": all(
                len(state.transitions) <= 20
                for world in engines for item in world.plan_system.goal_plans
                for state in item.dependencies
            ),
            "dependency_revisions_are_bound": all(
                state.revision == item.revision
                for world in engines for item in world.plan_system.goal_plans
                for state in item.dependencies
            ),
            "plan_invariants_hold": all(
                all(world.plan_system.validate_invariants(world.goal_planner).values())
                for world in engines
            ),
        }

    for name, passed in {**scenarios, **invariants}.items():
        if not passed:
            diagnostics[name] = "deterministic composite dependency check failed"
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
