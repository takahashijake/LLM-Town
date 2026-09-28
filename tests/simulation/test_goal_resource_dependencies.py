"""Adversarial V4 Phase 4 resource preparation and execution coverage."""

from dataclasses import replace
from unittest.mock import patch

from src.agents.goal import Goal
from src.behavior.activity import Activity
from src.behavior.goal_planner import StrategyCandidate
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def engine_at(tmp_path, name="state", load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=tmp_path / f"{name}.json",
        logs_dir=tmp_path / f"{name}-logs",
    )


def bind(engine):
    actor = engine.agents[0]
    goal = Goal(
        id="goal-study-book", agent_name=actor.name,
        description="Study authoritative reference material",
        category="increase_knowledge", priority=5, created_day=1,
        review_day=7, progress_target=4, target_locations=["library"],
    )
    actor.goals = [goal]
    candidate = StrategyCandidate(
        "study_reference_material", "investigate", 5.0,
        target_location="library", feasible=True, score=5.4,
    )
    with patch.object(engine.goal_planner, "select_strategy", return_value=candidate):
        engine.update_agent_intents(1)
    return actor, goal, engine.agent_intents[actor.name], engine.plan_system.get_goal_plan(goal.id)


def prepare(engine, actor, day=1, hour=8):
    engine.activity_system.run_agent_activities(
        [actor], [location.id for location in engine.locations], day, hour,
        engine.current_daily_event, engine.agent_intents,
    )
    return engine.activity_records[-1]


def study(engine, actor, day=1, hour=9):
    intent = engine.agent_intents[actor.name]
    dependency = engine.plan_system.goal_dependency_for_agent(
        actor.id, day=day, tick=hour, goal_plan_id=intent.source_goal_plan_id,
    )
    activity = engine.activity_planner.create_intent_activity(intent, dependency)
    engine.activity_system.log_activity_event(day, hour, actor, activity)
    record = engine.activity_records[-1]
    engine.intent_system._engine_for_goal_check = engine
    engine.intent_system.update_intent_after_activity(
        day=day, agent=actor, activity_record=record,
    )
    return activity, record


def grant_book(engine, actor, event_key="test:grant-book"):
    seller = engine.materials.sellers["seller:market_stall"]
    return engine.materials.transfer_good(
        seller.inventory_id, engine.materials.inventory_for_agent(actor.id).id,
        "reference_book", 1, day=1, hour=7, reason="test authorized transfer",
        authorization_type="test", authorization_id=event_key, event_key=event_key,
    )


def test_owned_book_satisfies_without_purchase_and_wrong_owner_or_good_does_not(tmp_path):
    engine = engine_at(tmp_path)
    actor = engine.agents[0]
    grant_book(engine, actor)
    actor, goal, _intent, plan = bind(engine)
    assert plan.dependency.status == "satisfied"
    assert plan.dependency.authority_reference == engine.materials.inventory_for_agent(actor.id).id
    assert not engine.materials.exchanges and goal.progress == 0

    wrong = engine_at(tmp_path, "wrong")
    wrong_actor, _goal, _intent, wrong_plan = bind(wrong)
    grant_book(wrong, wrong.agents[1])
    seller = wrong.materials.sellers["seller:market_stall"]
    wrong.materials.transfer_good(
        seller.inventory_id, wrong.materials.inventory_for_agent(wrong_actor.id).id,
        "household_supplies", 1, day=1, hour=7, reason="wrong good",
        authorization_type="test", authorization_id="wrong-good", event_key="wrong-good",
    )
    state = wrong.plan_system.refresh_goal_dependency(wrong_plan, day=1, tick=8)
    assert state.status == "preparable"


def test_missing_book_discovers_real_bounded_purchase_route(tmp_path):
    engine = engine_at(tmp_path)
    actor, _goal, _intent, plan = bind(engine)
    route = engine.materials.find_purchase_route(actor.id, "reference_book", 1)
    assert route.seller_id == "seller:market_stall"
    assert route.location_id == "market" and route.total_price == 25
    assert plan.dependency.status == "preparable"
    assert plan.dependency.authority_reference == route.seller_id


def test_preparation_is_atomic_authoritative_and_not_goal_progress(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, plan = bind(engine)
    buyer = engine.economy.account_for_agent(actor.id)
    seller = engine.materials.sellers["seller:market_stall"]
    seller_account = engine.economy.get_account(seller.account_id)
    buyer_inventory = engine.materials.inventory_for_agent(actor.id)
    seller_inventory = engine.materials.get_inventory(seller.inventory_id)
    before = (buyer.balance, seller_account.balance,
              buyer_inventory.quantity("reference_book"),
              seller_inventory.quantity("reference_book"))

    record = prepare(engine, actor)
    after = (
        engine.economy.account_for_agent(actor.id).balance,
        engine.economy.get_account(seller.account_id).balance,
        engine.materials.inventory_for_agent(actor.id).quantity("reference_book"),
        engine.materials.get_inventory(seller.inventory_id).quantity("reference_book"),
    )
    assert record["activity_id"] == "goal_acquire_reference_book"
    assert record["preparation_exchange_id"] == engine.materials.exchanges[-1].id
    assert after == (before[0] - 25, before[1] + 25, before[2] + 1, before[3] - 1)
    assert goal.progress == intent.progress == 0
    assert engine.materials.material_conservation_holds()
    assert engine.economy.conservation_holds()
    assert engine.materials.provenance_reconciles()
    assert engine.plan_system.refresh_goal_dependency(plan, day=1, tick=9).status == "satisfied"


def test_exact_study_advances_once_but_generic_library_activity_does_not(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, plan = bind(engine)
    prepare(engine, actor)
    generic = {
        "agent": actor.name, "day": 1, "hour": 9,
        "activity_id": "goal_seek_information", "activity_name": "Read nearby",
        "location": "library", "tags": ["goal_strategy", "seek_information"],
        "source_goal_id": goal.id, "source_goal_plan_id": plan.id,
        "source_goal_plan_revision": plan.revision,
        "source_goal_strategy": plan.strategy_name, "source_intent_id": intent.id,
        "source_goal_dependency_kind": "owned_good",
        "source_goal_dependency_subject": "reference_book",
        "source_goal_dependency_authority_ref": plan.dependency.authority_reference,
    }
    engine.intent_system.update_intent_after_activity(day=1, agent=actor, activity_record=generic)
    assert goal.progress == 0
    _activity, exact = study(engine, actor)
    assert goal.progress == 1 and intent.progress == 1
    engine.intent_system.update_intent_after_activity(day=1, agent=actor, activity_record=exact)
    assert goal.progress == 1 and len(plan.evidence_records) == 1


def test_insufficient_funds_stock_and_inactive_seller_never_mutate(tmp_path):
    for name, break_route in (
        ("funds", "funds"), ("stock", "stock"), ("inactive", "inactive"),
    ):
        engine = engine_at(tmp_path, name)
        actor = engine.agents[0]
        seller = engine.materials.sellers["seller:market_stall"]
        if break_route == "funds":
            account = engine.economy.account_for_agent(actor.id)
            engine.economy._accounts[account.id] = replace(account, balance=0)
        elif break_route == "stock":
            stock = engine.materials.quantity(seller.inventory_id, "reference_book")
            engine.materials.transfer_good(
                seller.inventory_id, engine.materials.inventory_for_agent(engine.agents[1].id).id,
                "reference_book", stock, day=1, hour=7, reason="remove stock",
                authorization_type="test", authorization_id=f"remove:{name}",
                event_key=f"remove:{name}",
            )
        else:
            engine.materials.sellers[seller.id] = replace(seller, active=False)
        balances = {key: value.balance for key, value in engine.economy.accounts.items()}
        quantities = engine.materials.total_quantities()
        actor, goal, _intent, plan = bind(engine)
        assert plan.dependency.status == "blocked"
        assert engine.materials.find_purchase_route(actor.id, "reference_book", 1) is None
        assert {key: value.balance for key, value in engine.economy.accounts.items()} == balances
        assert engine.materials.total_quantities() == quantities and goal.progress == 0


def test_resource_loss_before_study_fails_closed(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, plan = bind(engine)
    prepare(engine, actor)
    _activity, stale_record = study(engine, actor, hour=9)
    assert goal.progress == 1
    # Use a fresh goal/intention to prove a persisted satisfied label is insufficient.
    goal.progress = 0
    goal.processed_evidence_keys.clear()
    intent.progress = 0
    intent.evidence.clear()
    plan.evidence_records.clear()
    plan.processed_evidence_keys.clear()
    engine.materials.transfer_good(
        engine.materials.inventory_for_agent(actor.id).id,
        engine.materials.sellers["seller:market_stall"].inventory_id,
        "reference_book", 1, day=1, hour=10, reason="legitimate loss",
        authorization_type="test", authorization_id="loss", event_key="loss",
    )
    engine.intent_system.update_intent_after_activity(
        day=1, agent=actor, activity_record={**stale_record, "hour": 10},
    )
    assert goal.progress == intent.progress == 0
    assert plan.dependency.status == "preparable"


def test_preparation_replay_cannot_charge_or_duplicate_material(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, _plan = bind(engine)
    record = prepare(engine, actor)
    activity = Activity(
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
        engine.economy.account_for_agent(actor.id).balance,
        engine.materials.inventory_for_agent(actor.id).quantity("reference_book"),
        len(engine.materials.exchanges), len(engine.economy.ledger),
    )
    assert engine.materials.process_activity(actor, activity, day=2, hour=8) is None
    assert snapshot == (
        engine.economy.account_for_agent(actor.id).balance,
        engine.materials.inventory_for_agent(actor.id).quantity("reference_book"),
        len(engine.materials.exchanges), len(engine.economy.ledger),
    )
    assert record["execution_status"] == "prepared"
    assert goal.progress == intent.progress == 0


def test_old_revision_and_cross_goal_proof_are_rejected(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, _intent, plan = bind(engine)
    prepare(engine, actor)
    _activity, old_record = study(engine, actor)
    goal.progress = 0
    goal.processed_evidence_keys.clear()
    replacement = StrategyCandidate(
        "seek_information_at_location", "investigate", 4.6,
        target_location="library", score=5.3,
    )
    assert engine.plan_system.adapt_goal_plan(
        plan, replacement, day=2, trigger="resource_unavailable",
        preserved_progress=0, goal_planner=engine.goal_planner,
    )
    engine.intent_system.update_intent_after_activity(day=2, agent=actor, activity_record=old_record)
    assert goal.progress == 0 and plan.revision == 1
    assert old_record["source_goal_plan_revision"] == 0


def test_save_resume_recomputes_missing_and_owned_state(tmp_path):
    missing = engine_at(tmp_path, "missing")
    actor, goal, _intent, _plan = bind(missing)
    missing.state.save(missing, 1, 8)
    resumed = engine_at(tmp_path, "missing", load=True)
    restored = resumed.plan_system.get_goal_plan(goal.id)
    assert resumed.plan_system.refresh_goal_dependency(restored, day=2, tick=8).status == "preparable"

    owned = engine_at(tmp_path, "owned")
    owned_actor, owned_goal, _intent, _plan = bind(owned)
    prepare(owned, owned_actor)
    owned.state.save(owned, 1, 8)
    owned_resumed = engine_at(tmp_path, "owned", load=True)
    owned_plan = owned_resumed.plan_system.get_goal_plan(owned_goal.id)
    assert owned_resumed.plan_system.refresh_goal_dependency(
        owned_plan, day=2, tick=8,
    ).status == "satisfied"


def test_due_v3_commitment_preempts_goal_preparation(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, plan = bind(engine)
    commitment = engine.commitment_system.create(
        proposer_id="agent_002", counterpart_id=actor.id,
        commitment_type="meet", day=1, due_day=1,
        metadata={"location": "cafe"}, status="proposed",
    )
    engine.commitment_system.transition(commitment.id, "accepted", day=1, reason="accepted")
    with patch("src.behavior.planner.random.random", return_value=0.5):
        engine.activity_system.run_agent_activities(
            [actor], [location.id for location in engine.locations], 1, 8,
            None, engine.agent_intents,
        )
    record = engine.activity_records[-1]
    assert record["source_commitment_id"] == commitment.id
    assert not engine.materials.exchanges and goal.progress == intent.progress == 0
    assert plan.dependency.status == "preparable"


def test_dialogue_claim_has_no_resource_or_goal_authority(tmp_path):
    engine = engine_at(tmp_path)
    actor, goal, intent, plan = bind(engine)
    before = engine.materials.inventory_for_agent(actor.id).quantity("reference_book")
    accepted = engine.plan_system.observe_goal_evidence(
        goal, evidence_key="dialogue-book-claim", day=1, intent_id=intent.id,
        evidence_type="strategy_activity",
        details={"dialogue": "I bought and read the reference book."},
    )
    assert not accepted and goal.progress == 0
    assert engine.materials.inventory_for_agent(actor.id).quantity("reference_book") == before
    assert plan.dependency.status == "preparable"


def test_production_strategy_candidate_is_bounded_and_adapts_when_route_disappears(tmp_path):
    engine = engine_at(tmp_path)
    actor = engine.agents[0]
    goal = Goal(
        id="production-resource", agent_name=actor.name, description="Learn",
        category="increase_knowledge", priority=5, created_day=1, review_day=7,
        target_locations=["library"],
    )
    candidates = engine.goal_planner.generate_strategies(goal, actor, engine)
    resource = next(item for item in candidates if item.name == "study_reference_material")
    assert resource.feasible
    assert engine.goal_planner.select_strategy(goal, actor, engine).name == "seek_information_at_location"
    goal.progress = 1
    assert engine.goal_planner.select_strategy(goal, actor, engine).name == resource.name
    goal.progress = 0
    grant_book(engine, actor)
    assert engine.goal_planner.select_strategy(goal, actor, engine).name == resource.name
    engine.materials.transfer_good(
        engine.materials.inventory_for_agent(actor.id).id,
        engine.materials.sellers["seller:market_stall"].inventory_id,
        "reference_book", 1, day=1, hour=8, reason="remove owned prerequisite",
        authorization_type="test", authorization_id="remove-owned",
        event_key="remove-owned",
    )
    seller = engine.materials.sellers["seller:market_stall"]
    engine.materials.sellers[seller.id] = replace(seller, active=False)
    candidates = engine.goal_planner.generate_strategies(goal, actor, engine)
    resource = next(item for item in candidates if item.name == "study_reference_material")
    assert not resource.feasible and "neither owned" in resource.infeasible_reason
    assert any(item.feasible for item in candidates if item.name != resource.name)
