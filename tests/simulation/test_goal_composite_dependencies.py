"""Focused V4 Phase 5 composite dependency acceptance coverage."""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

import pytest

from src.agents.goal import Goal
from src.behavior.activity import Activity
from src.behavior.goal_planner import StrategyCandidate
from src.behavior.goal_strategy_contracts import (
    DAILY_EVENT_AT_TARGET,
    OWNED_GOOD,
    strategy_contract,
)
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.plans import PLAN_SCHEMA_VERSION, PlanSystem
from src.town.daily_event import DailyEvent


STRATEGY = "study_reference_material_at_active_location"
FINAL_ACTIVITY = "goal_study_reference_material_at_active_location"


def engine_at(tmp_path, name="state", load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=tmp_path / f"{name}.json",
        logs_dir=tmp_path / f"{name}-logs",
    )


def bind(engine, goal_id="goal-composite"):
    actor = engine.agents[0]
    goal = Goal(
        id=goal_id, agent_name=actor.name,
        description="Study reference material where an event is currently active",
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


def set_library_event(engine, event_id="book_club"):
    engine.current_daily_event = DailyEvent(
        event_id, "Book Club", "A current gathering.", "library", ["learning"],
    )


def grant_book(engine, actor, event_key="composite:grant"):
    seller = engine.materials.sellers["seller:market_stall"]
    return engine.materials.transfer_good(
        seller.inventory_id, engine.materials.inventory_for_agent(actor.id).id,
        "reference_book", 1, day=1, hour=7, reason="authorized test transfer",
        authorization_type="test", authorization_id=event_key,
        event_key=event_key,
    )


def choose_one(engine, actor, day=1, hour=8):
    engine.activity_system.run_agent_activities(
        [actor], [item.id for item in engine.locations], day, hour,
        engine.current_daily_event, engine.agent_intents,
    )
    return engine.activity_records[-1]


def final_record(engine, actor, day=1, hour=9):
    intent = engine.agent_intents[actor.name]
    opportunity = engine.plan_system.goal_dependency_for_agent(
        actor.id, day=day, tick=hour,
        current_daily_event=engine.current_daily_event,
        goal_plan_id=intent.source_goal_plan_id,
    )
    activity = engine.activity_planner.create_intent_activity(intent, opportunity)
    engine.activity_system.log_activity_event(day, hour, actor, activity)
    return engine.activity_records[-1]


def accept(engine, actor, record, day=1):
    engine.intent_system._engine_for_goal_check = engine
    return engine.intent_system.update_intent_after_activity(
        day=day, agent=actor, activity_record=record,
    )


def test_contract_is_ordered_bounded_and_runtime_selectable(tmp_path):
    contract = strategy_contract(STRATEGY)
    assert [item.kind for item in contract.dependencies] == [
        OWNED_GOOD, DAILY_EVENT_AT_TARGET,
    ]
    assert contract.activity_id == FINAL_ACTIVITY
    engine = engine_at(tmp_path)
    actor = engine.agents[0]
    grant_book(engine, actor)
    set_library_event(engine)
    goal = Goal(
        id="select-composite", agent_name=actor.name, description="Learn",
        category="increase_knowledge", priority=5, created_day=1, review_day=7,
        target_locations=["library"],
    )
    assert engine.goal_planner.select_strategy(goal, actor, engine).name == STRATEGY


def test_preparation_satisfies_only_resource_then_waits_for_event(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, plan = bind(engine)
    opportunity = engine.plan_system.goal_dependency_for_agent(
        actor.id, day=1, tick=8, current_daily_event=None, goal_plan_id=plan.id,
    )
    assert opportunity.status == "preparable"
    assert [item.status for item in opportunity.dependencies] == [
        "preparable", "waiting",
    ]
    before_exchanges = len(engine.materials.exchanges)
    record = choose_one(engine, actor)
    assert record["activity_id"] == "goal_acquire_reference_book"
    assert len(engine.materials.exchanges) == before_exchanges + 1
    assert goal.progress == intent.progress == 0
    opportunity = engine.plan_system.goal_dependency_for_agent(
        actor.id, day=1, tick=9, current_daily_event=None, goal_plan_id=plan.id,
    )
    assert [item.status for item in opportunity.dependencies] == [
        "satisfied", "waiting",
    ]
    assert opportunity.status == "waiting"


def test_later_event_and_retained_ownership_allow_exactly_once_final_execution(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, plan = bind(engine)
    choose_one(engine, actor)
    set_library_event(engine)
    opportunity = engine.plan_system.goal_dependency_for_agent(
        actor.id, day=2, tick=8, current_daily_event=engine.current_daily_event,
        goal_plan_id=plan.id,
    )
    assert opportunity.status == "satisfied" and goal.progress == 0
    record = final_record(engine, actor, day=2, hour=8)
    assert record["activity_id"] == FINAL_ACTIVITY
    assert len(record["source_goal_dependencies"]) == 2
    accept(engine, actor, record, day=2)
    accept(engine, actor, record, day=2)
    assert goal.progress == intent.progress == 1
    assert len(plan.evidence_records) == 1


def test_event_disappearing_or_resource_loss_rejects_stale_final_proof(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, plan = bind(engine)
    grant_book(engine, actor)
    set_library_event(engine)
    stale = final_record(engine, actor)
    engine.current_daily_event = None
    accept(engine, actor, stale)
    assert goal.progress == intent.progress == 0
    set_library_event(engine)
    stale = final_record(engine, actor, hour=10)
    seller = engine.materials.sellers["seller:market_stall"]
    engine.materials.transfer_good(
        engine.materials.inventory_for_agent(actor.id).id, seller.inventory_id,
        "reference_book", 1, day=1, hour=10, reason="authorized loss",
        authorization_type="test", authorization_id="composite:loss",
        event_key="composite:loss",
    )
    accept(engine, actor, stale)
    assert goal.progress == intent.progress == 0
    assert [item.status for item in plan.dependencies] == ["preparable", "satisfied"]


def test_wrong_dependency_identity_and_cross_provenance_are_rejected(tmp_path):
    fields = {
        "agent": "Other resident",
        "source_goal_id": "other-goal",
        "source_goal_plan_id": "other-plan",
        "source_goal_plan_revision": 99,
        "source_intent_id": "other-intent",
        "source_goal_strategy": "study_reference_material",
    }
    for index, (field, value) in enumerate(fields.items()):
        engine = engine_at(tmp_path, f"cross-{index}")
        actor, goal, intent, _plan = bind(engine)
        grant_book(engine, actor, f"cross:grant:{index}")
        set_library_event(engine)
        record = final_record(engine, actor)
        record[field] = value
        accept(engine, actor, record)
        assert goal.progress == intent.progress == 0, field

    engine = engine_at(tmp_path, "wrong-dependencies")
    actor, goal, intent, _plan = bind(engine)
    grant_book(engine, actor, "wrong:grant")
    set_library_event(engine)
    for mutation in (
        lambda items: items[0].update(subject_id="household_supplies"),
        lambda items: items[1].update(subject_id="market"),
        lambda items: items[1].update(authority_reference="wrong-event"),
    ):
        record = final_record(engine, actor)
        mutation(record["source_goal_dependencies"])
        accept(engine, actor, record)
        assert goal.progress == intent.progress == 0


def test_authoritative_external_acquisition_is_accepted_without_planner_purchase(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, _plan = bind(engine)
    grant_book(engine, actor)
    set_library_event(engine)
    record = final_record(engine, actor)
    accept(engine, actor, record)
    assert goal.progress == intent.progress == 1
    assert not engine.economy.ledger


def test_no_route_blocks_composite_and_existing_adaptation_can_replace_it(tmp_path):
    engine = engine_at(tmp_path)
    seller = engine.materials.sellers["seller:market_stall"]
    engine.materials.sellers[seller.id] = replace(seller, active=False)
    actor, goal, _intent, plan = bind(engine)
    opportunity = engine.plan_system.goal_dependency_for_agent(
        actor.id, day=1, tick=8, current_daily_event=None, goal_plan_id=plan.id,
    )
    assert opportunity.status == "blocked"
    candidates = engine.goal_planner.generate_strategies(goal, actor, engine)
    composite = next(item for item in candidates if item.name == STRATEGY)
    replacement = next(
        item for item in candidates
        if item.name == "seek_information_at_location" and item.feasible
    )
    assert not composite.feasible
    assert engine.plan_system.adapt_goal_plan(
        plan, replacement, day=2, trigger="hard_constraint",
        preserved_progress=0, goal_planner=engine.goal_planner,
    )
    assert plan.strategy_name == replacement.name and not plan.dependencies
    assert engine.materials.inventory_for_agent(actor.id).quantity("reference_book") == 0


def test_preparation_and_final_replay_preserve_conservation(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, _plan = bind(engine)
    record = choose_one(engine, actor)
    replay = Activity(
        id=record["activity_id"], name=record["activity_name"],
        location_id=record["location"], reason=record["reason"], tags=record["tags"],
        source_goal_id=record["source_goal_id"],
        source_goal_plan_id=record["source_goal_plan_id"],
        source_goal_plan_revision=record["source_goal_plan_revision"],
        source_goal_strategy=record["source_goal_strategy"],
        source_intent_id=record["source_intent_id"],
        source_goal_dependency_kind=record["source_goal_dependency_kind"],
        source_goal_dependency_subject=record["source_goal_dependency_subject"],
        source_goal_dependency_authority_ref=record[
            "source_goal_dependency_authority_ref"
        ],
    )
    snapshot = (
        len(engine.materials.exchanges), len(engine.economy.ledger),
        engine.economy.account_for_agent(actor.id).balance,
        engine.materials.inventory_for_agent(actor.id).quantity("reference_book"),
    )
    assert engine.materials.process_activity(actor, replay, day=2, hour=8) is None
    assert snapshot == (
        len(engine.materials.exchanges), len(engine.economy.ledger),
        engine.economy.account_for_agent(actor.id).balance,
        engine.materials.inventory_for_agent(actor.id).quantity("reference_book"),
    )
    assert engine.economy.conservation_holds()
    assert engine.materials.material_conservation_holds()
    assert engine.materials.provenance_reconciles()
    set_library_event(engine)
    final = final_record(engine, actor, day=2, hour=9)
    accept(engine, actor, final, day=2)
    accept(engine, actor, final, day=2)
    assert goal.progress == intent.progress == 1


def test_save_resume_rechecks_both_authorities(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, _intent, _plan = bind(engine)
    choose_one(engine, actor)
    set_library_event(engine)
    engine.state.save(engine, 1, 8)
    resumed = engine_at(tmp_path, load=True)
    restored = resumed.plan_system.get_goal_plan(goal.id)
    states = resumed.plan_system.refresh_goal_dependency(
        restored, day=2, tick=8, current_daily_event=None,
    )
    assert [item.status for item in states] == ["satisfied", "waiting"]
    assert resumed.agents[0].get_goal(goal.id).progress == 0


def test_v5_migration_and_malformed_composites_fail_closed(tmp_path):
    engine = engine_at(tmp_path)
    actor, _goal, _intent, plan = bind(engine)
    document = engine.plan_system.to_dict()
    single = deepcopy(document["goal_plans"][0])
    single["strategy_name"] = "study_reference_material"
    single["dependencies"] = single["dependencies"][:1]
    dependency = single.pop("dependencies")[0]
    single.pop("legacy_dependency_omitted", None)
    version_five = {
        **document, "schema_version": 5, "goal_plans": [
            {**single, "dependency": dependency},
        ],
    }
    restored = PlanSystem.from_dict(
        version_five, commitment_system=engine.commitment_system,
        agents=engine.agents, outcome_memory=engine.outcome_memory,
        materials=engine.materials,
    )
    migrated = restored.goal_plans[0]
    assert len(migrated.dependencies) == 1
    assert migrated.dependency.kind == OWNED_GOOD

    for mutate in (
        lambda item: item["dependencies"].append(deepcopy(item["dependencies"][0])),
        lambda item: item["dependencies"][0].update(kind="unknown"),
        lambda item: item["dependencies"][0].update(subject_id="wrong_good"),
        lambda item: item.update(dependencies=item["dependencies"][:1]),
    ):
        malformed = deepcopy(document)
        mutate(malformed["goal_plans"][0])
        with pytest.raises(ValueError):
            PlanSystem.from_dict(
                malformed, commitment_system=engine.commitment_system,
                agents=engine.agents, outcome_memory=engine.outcome_memory,
                materials=engine.materials,
            )
    assert document["schema_version"] == PLAN_SCHEMA_VERSION
    assert plan.strategy_name == STRATEGY and len(plan.dependencies) == 2


def test_due_commitment_preempts_composite_preparation(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, plan = bind(engine)
    commitment = engine.commitment_system.create(
        proposer_id="agent_002", counterpart_id=actor.id,
        commitment_type="meet", day=1, due_day=1,
        metadata={"location": "cafe"}, status="proposed",
    )
    engine.commitment_system.transition(
        commitment.id, "accepted", day=1, reason="accepted",
    )
    with patch("src.behavior.planner.random.random", return_value=0.5):
        record = choose_one(engine, actor)
    assert record["source_commitment_id"] == commitment.id
    assert not engine.materials.exchanges
    assert goal.progress == intent.progress == 0
    assert [item.status for item in plan.dependencies] == ["preparable", "waiting"]
