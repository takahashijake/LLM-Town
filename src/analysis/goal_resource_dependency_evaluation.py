"""Deterministic acceptance evaluation for V4 Phase 4 resource preparation."""

from contextlib import contextmanager
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.agents.goal import Goal
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.materials import MaterialError


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


def _install_goal(engine):
    actor = engine.agents[0]
    goal = Goal(
        id="evaluation-study-reference", agent_name=actor.name,
        description="Study a reference book for durable knowledge",
        category="increase_knowledge", priority=5, created_day=1,
        review_day=7, progress_target=4, target_locations=["library"],
        progress=1,
    )
    actor.goals = [goal]
    engine.update_agent_intents(1)
    intent = engine.agent_intents[actor.name]
    plan = engine.plan_system.get_goal_plan(goal.id)
    return actor, goal, intent, plan


def evaluate_goal_resource_dependencies() -> dict:
    scenarios = {}
    diagnostics = {}
    engines = []
    with _isolated_random_state(), TemporaryDirectory() as directory:
        root = Path(directory)
        engine = _engine(root, "lifecycle")
        engines.append(engine)
        actor, goal, intent, plan = _install_goal(engine)
        initial_currency = engine.economy.total_currency()
        initial_materials = engine.materials.total_quantities()
        scenarios["resource_strategy_selected"] = (
            plan.strategy_name == "study_reference_material"
        )
        scenarios["dependency_missing"] = (
            plan.dependency.kind == "owned_good"
            and plan.dependency.subject_id == "reference_book"
            and plan.dependency.status == "preparable"
        )
        route = engine.materials.find_purchase_route(actor.id, "reference_book", 1)
        scenarios["legal_route_discovered"] = (
            route is not None and route.seller_id == "seller:market_stall"
            and route.location_id == "market" and route.total_price == 25
        )

        missing_dependency = engine.plan_system.goal_dependency_for_agent(
            actor.id, day=1, tick=7, goal_plan_id=plan.id,
        )
        forged_study = engine.activity_planner.create_intent_activity(
            intent, missing_dependency,
        )
        engine.activity_system.log_activity_event(1, 7, actor, forged_study)
        engine.intent_system._engine_for_goal_check = engine
        engine.intent_system.update_intent_after_activity(
            day=1, agent=actor, activity_record=engine.activity_records[-1],
        )
        no_resource_progress = goal.progress == 1 and intent.progress == 0

        engine.activity_system.run_agent_activities(
            [actor], [location.id for location in engine.locations], 1, 8,
            None, engine.agent_intents,
        )
        preparation_record = engine.activity_records[-1]
        scenarios["preparation_selected"] = (
            preparation_record["activity_id"] == "goal_acquire_reference_book"
            and preparation_record["location"] == "market"
        )
        scenarios["authoritative_purchase_succeeded"] = (
            len(engine.materials.exchanges) == 1
            and preparation_record.get("preparation_exchange_id")
            == engine.materials.exchanges[0].id
        )
        no_preparation_progress = goal.progress == 1 and intent.progress == 0
        dependency = engine.plan_system.goal_dependency_for_agent(
            actor.id, day=1, tick=9, goal_plan_id=plan.id,
        )
        scenarios["dependency_satisfied"] = (
            dependency.status == "satisfied"
            and engine.materials.inventory_for_agent(actor.id).quantity(
                "reference_book"
            ) == 1
        )
        study = engine.activity_planner.create_intent_activity(intent, dependency)
        scenarios["strategy_execution_selected"] = (
            study.id == "goal_study_reference_material"
            and study.location_id == "library"
        )
        engine.activity_system.log_activity_event(1, 9, actor, study)
        study_record = engine.activity_records[-1]
        accepted = engine.intent_system.update_intent_after_activity(
            day=1, agent=actor, activity_record=study_record,
        )
        scenarios["authoritative_execution_accepted"] = bool(accepted)
        scenarios["goal_progressed"] = goal.progress == 2 and intent.progress == 1
        engine.intent_system.update_intent_after_activity(
            day=1, agent=actor, activity_record=study_record,
        )
        scenarios["goal_evidence_replay_idempotent"] = goal.progress == 2

        exchange = engine.materials.exchanges[0]
        replay_snapshot = (
            engine.economy.account_for_agent(actor.id).balance,
            engine.materials.inventory_for_agent(actor.id).quantity("reference_book"),
            len(engine.economy.ledger), len(engine.materials.exchanges),
        )
        try:
            engine.materials.purchase(
                exchange.buyer_inventory_id, exchange.buyer_account_id,
                exchange.seller_id, exchange.good_id, exchange.quantity,
                day=2, hour=8, event_key=exchange.event_key,
            )
        except MaterialError as error:
            replay_rejected = error.code == "duplicate_event"
        else:
            replay_rejected = False
        scenarios["purchase_replay_idempotent"] = replay_rejected and replay_snapshot == (
            engine.economy.account_for_agent(actor.id).balance,
            engine.materials.inventory_for_agent(actor.id).quantity("reference_book"),
            len(engine.economy.ledger), len(engine.materials.exchanges),
        )

        dialogue_accepted = engine.plan_system.observe_goal_evidence(
            goal, evidence_key="dialogue-claim", day=1, intent_id=intent.id,
            evidence_type="strategy_activity",
            details={"dialogue": "I bought and read the book."},
        )
        scenarios["dialogue_has_no_authority"] = not dialogue_accepted and goal.progress == 2

        engine.state.save(engine, 1, 9)
        resumed = _engine(root, "lifecycle", load=True)
        engines.append(resumed)
        resumed_plan = resumed.plan_system.get_goal_plan(goal.id)
        scenarios["save_resume_rechecks_authority"] = (
            resumed.plan_system.refresh_goal_dependency(
                resumed_plan, day=2, tick=8,
            ).status == "satisfied"
        )

        priority = _engine(root, "priority")
        engines.append(priority)
        p_actor, p_goal, p_intent, p_plan = _install_goal(priority)
        commitment = priority.commitment_system.create(
            proposer_id="agent_002", counterpart_id=p_actor.id,
            commitment_type="meet", day=1, due_day=1,
            metadata={"location": "cafe"}, status="proposed",
        )
        priority.commitment_system.transition(
            commitment.id, "accepted", day=1, reason="accepted",
        )
        with patch("src.behavior.planner.random.random", return_value=0.5):
            priority.activity_system.run_agent_activities(
                [p_actor], [location.id for location in priority.locations],
                1, 8, None, priority.agent_intents,
            )
        scenarios["v3_commitment_priority_preserved"] = (
            priority.activity_records[-1]["source_commitment_id"] == commitment.id
            and not priority.materials.exchanges
            and p_goal.progress == 1 and p_intent.progress == 0
            and p_plan.dependency.status == "preparable"
        )

        owner_inventory = engine.materials.inventory_for_agent(actor.id)
        other_inventories = [
            engine.materials.inventory_for_agent(other.id)
            for other in engine.agents if other.id != actor.id
        ]
        invariants = {
            "no_progress_from_preparation": no_preparation_progress,
            "no_progress_without_owned_resource": no_resource_progress,
            "no_dialogue_authority": scenarios["dialogue_has_no_authority"],
            "resource_belongs_to_correct_owner": (
                owner_inventory.quantity("reference_book") == 1
                and all(item.quantity("reference_book") == 0 for item in other_inventories)
            ),
            "goal_proof_bound_to_current_plan_revision": (
                study_record["source_goal_plan_revision"] == plan.revision
                and plan.evidence_records[0]["source_goal_plan_revision"] == plan.revision
            ),
            "purchase_replay_idempotent": scenarios["purchase_replay_idempotent"],
            "goal_evidence_replay_idempotent": (
                scenarios["goal_evidence_replay_idempotent"]
                and len(plan.evidence_records) == 1
            ),
            "currency_conserved": (
                engine.economy.total_currency() == initial_currency
                and engine.economy.conservation_holds()
            ),
            "materials_conserved": (
                engine.materials.total_quantities() == initial_materials
                and engine.materials.material_conservation_holds()
            ),
            "lot_provenance_valid": engine.materials.provenance_reconciles(),
            "bounded_dependency_history": len(plan.dependency.transitions) <= 20,
            "v3_commitment_priority_preserved": scenarios[
                "v3_commitment_priority_preserved"
            ],
            "resource_diagnostics_are_private": "dependency" not in str(
                engine.prepare_conversation_context(
                    "cafe", engine.agents[0], engine.agents[1], 1,
                )["context"]
            ).lower(),
            "plan_invariants_hold": all(
                all(world.plan_system.validate_invariants(world.goal_planner).values())
                for world in engines
            ),
        }

    for name, passed in {**scenarios, **invariants}.items():
        if not passed:
            diagnostics[name] = "deterministic resource dependency check failed"
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
