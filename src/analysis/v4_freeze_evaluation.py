"""Deterministic whole-V4 freeze-candidate acceptance evaluation.

This module intentionally composes the existing V4 mechanisms instead of
calling their phase evaluators.  The main scenario keeps two independent goals
in one world while one goal crosses resource preparation, composite execution,
adaptation, delegation through V3, and final authoritative execution.
"""

from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.agents.goal import Goal
from src.agents.memory import Memory
from src.behavior.goal_planner import StrategyCandidate
from src.behavior.goal_strategy_contracts import (
    DEPENDENCY_KINDS,
    GOAL_STRATEGY_EXECUTION_CONTRACTS,
    MAX_STRATEGY_DEPENDENCIES,
    strategy_contract,
)
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.materials import MaterialError
from src.systems.plans import PlanSystem
from src.town.daily_event import DailyEvent


COMPOSITE = "study_reference_material_at_active_location"
DELEGATION = "request_research_help"
DIRECT = "seek_information_at_location"


class _AcceptingFakeLLM(FakeLLMClient):
    """Deterministically accepts the bounded research request in dialogue."""

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


def _engine(root: Path, name: str, *, load: bool = False, accepting=False):
    engine = SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=_AcceptingFakeLLM() if accepting else FakeLLMClient(),
        state_path=root / f"{name}.json", logs_dir=root / f"{name}-logs",
    )
    engine.sync_intent_system_refs()
    engine.intent_system._engine_for_goal_check = engine
    return engine


def _candidate(name: str, *, target=None, location="library"):
    contract = strategy_contract(name)
    return StrategyCandidate(
        name, "investigate", 5.0, target_agent=target,
        target_location=location, required_action=contract.required_social_action,
        score=6.0,
    )


def _goal(owner, goal_id: str, target: int = 3):
    return Goal(
        id=goal_id, agent_name=owner.name,
        description=f"Controlled integrated investigation for {owner.name}",
        category="investigate", priority=5, created_day=1, review_day=7,
        progress_target=target, target_locations=["library"],
    )


def _bind_two_goals(engine):
    owner, helper = engine.agents[:2]
    owner_goal = _goal(owner, "freeze-owner-goal", 3)
    helper_goal = _goal(helper, "freeze-helper-goal", 1)
    owner.goals = [owner_goal]
    helper.goals = [helper_goal]
    owner_candidate = _candidate(COMPOSITE)
    helper_candidate = _candidate(DIRECT)
    original = engine.goal_planner.select_strategy

    def select(goal, agent, world):
        if goal.id == owner_goal.id:
            return owner_candidate
        if goal.id == helper_goal.id:
            return helper_candidate
        return original(goal, agent, world)

    with patch.object(engine.goal_planner, "select_strategy", side_effect=select):
        engine.intent_system.update_agent_intents([owner, helper], 1, engine)
    return owner, helper, owner_goal, helper_goal


def _owner_helper(engine):
    return engine.agents[0], engine.agents[1]


def _activity_record(engine, actor, day: int, hour: int):
    return next(
        row for row in reversed(engine.activity_records)
        if row.get("agent") == actor.name
        and row.get("day") == day and row.get("hour") == hour
    )


def _run_actor(engine, actor, day: int, hour: int):
    with patch("src.behavior.planner.random.random", return_value=0.0):
        engine.activity_system.run_agent_activities(
            [actor], [place.id for place in engine.locations], day, hour,
            engine.current_daily_event, engine.agent_intents,
        )
    record = _activity_record(engine, actor, day, hour)
    engine.intent_system._engine_for_goal_check = engine
    engine.intent_system.update_intent_after_activity(
        day=day, agent=actor, activity_record=record,
    )
    outcomes = engine.plan_system.consume_delegation_outcomes(day=day, tick=hour)
    engine.intent_system.observe_delegation_outcomes(day=day, outcomes=outcomes)
    return record, outcomes


def _delegation_provenance(engine, plan):
    request = next(
        row for row in engine.plan_system.delegation_requests()
        if row["plan_id"] == plan.id
    )
    keys = (
        "owner_id", "source_goal_id", "plan_id", "revision", "strategy",
        "helper_id", "task_code", "target_location", "request_id",
    )
    return {key: request[key] for key in keys}


def _accept_delegation(engine, owner, helper, plan, *, day=3, tick=8):
    provenance = _delegation_provenance(engine, plan)
    engine.plan_system.record_delegation_request(
        provenance, day=day, tick=tick, session_id="freeze-delegation",
    )
    item = engine.commitment_system.process_response(
        proposer_id=owner.id, counterpart_id=helper.id,
        proposal_text="Could you help me with research at the library tomorrow?",
        response_text="Yes, I can help.", outcome="accepted", day=day, tick=tick,
        session_id="freeze-delegation", proposal_turn=0, response_turn=1,
        bounded_goal_delegation=provenance,
    )
    engine.plan_system.link_delegation_commitment(
        provenance, item, day=day, tick=tick,
    )
    return provenance, item


def _fulfill_ordinary_help(engine, owner, helper, metadata, *, tick: int):
    item = engine.commitment_system.create(
        proposer_id=owner.id, counterpart_id=helper.id,
        commitment_type="help", day=1, due_day=2, status="proposed",
        metadata=metadata,
    )
    engine.commitment_system.transition(
        item.id, "accepted", day=1, reason="unrelated",
    )
    owner.location_id = helper.location_id = metadata["location"]
    engine.plan_system.ensure_commitment_plans(2)
    opportunity = next(
        row for row in engine.plan_system.opportunities_for_agent(
            helper.id, day=2, tick=tick,
        ) if row.commitment_id == item.id
    )
    activity = engine.activity_planner.create_commitment_activity(
        helper, opportunity,
    )
    execution = engine.commitment_system.execute_activity(
        commitment_id=item.id, agent_id=helper.id, day=2, tick=tick,
        activity_record={
            "activity_id": activity.id, "location": activity.location_id,
        },
    )
    engine.plan_system.record_execution(
        opportunity.plan_id, opportunity.step_id, day=2, tick=tick,
        execution_key=execution["event_key"], source_commitment_id=item.id,
        action_type=activity.id,
    )
    return item


def _save_reload(engine, root: Path, name: str, day: int, hour: int):
    engine.state.save(engine, day, hour)
    return _engine(root, name, load=True)


def _provenance_attack_matrix(engine, owner, goal, plan, base_record):
    """Exercise the real activity acceptance path with mutated proof fields."""
    attacks = {
        "wrong_owner": ("agent", engine.agents[2].name),
        "wrong_source_goal": ("source_goal_id", "other-goal"),
        "wrong_goal_plan": ("source_goal_plan_id", "other-plan"),
        "wrong_revision": ("source_goal_plan_revision", plan.revision + 1),
        "wrong_intent": ("source_intent_id", "other-intent"),
        "wrong_strategy": ("source_goal_strategy", DIRECT),
        "wrong_activity": ("activity_id", "learn"),
        "wrong_location": ("location", "market"),
    }
    results = {}
    for name, (field, value) in attacks.items():
        record = deepcopy(base_record)
        record[field] = value
        before = goal.progress
        engine.intent_system.update_intent_after_activity(
            day=2, agent=owner, activity_record=record,
        )
        results[name] = goal.progress == before
    for name, index, field, value in (
        ("wrong_resource", 0, "subject_id", "trade_materials"),
        ("wrong_event", 1, "authority_reference", "other-event"),
    ):
        record = deepcopy(base_record)
        record["source_goal_dependencies"][index][field] = value
        before = goal.progress
        engine.intent_system.update_intent_after_activity(
            day=2, agent=owner, activity_record=record,
        )
        results[name] = goal.progress == before
    return results


def _route_denial_checks(root: Path):
    checks = {}
    for case in ("seller", "stock", "price", "funds"):
        world = _engine(root, f"route-{case}")
        actor = world.agents[0]
        seller = world.materials.sellers["seller:market_stall"]
        before = world.materials.inventory_for_agent(actor.id).quantity(
            "reference_book"
        )
        if case == "seller":
            world.materials.sellers[seller.id] = replace(seller, active=False)
        elif case == "stock":
            inventory = world.materials.get_inventory(seller.inventory_id)
            world.materials._inventories[inventory.id] = inventory.with_quantity(
                "reference_book", 0,
            )
        elif case == "price":
            world.materials.goods.pop("reference_book")
        else:
            account = world.economy.account_for_agent(actor.id)
            world.economy._accounts[account.id] = replace(account, balance=0)
        checks[case] = (
            world.materials.find_purchase_route(actor.id, "reference_book", 1) is None
            and world.materials.inventory_for_agent(actor.id).quantity(
                "reference_book"
            ) == before
            and not world.materials.exchanges
        )
    return checks


def _dependency_authority_world(root: Path):
    """Prove persisted labels and foreign holdings never replace live authority."""
    world = _engine(root, "dependency-authority")
    owner, other = _owner_helper(world)
    goal = _goal(owner, "dependency-authority-goal", 2)
    owner.goals = [goal]
    with patch.object(
        world.goal_planner, "select_strategy", return_value=_candidate(COMPOSITE),
    ):
        world.intent_system.update_agent_intents([owner], 1, world)
    plan = world.plan_system.get_goal_plan(goal.id)
    for state in plan.dependencies:
        state.status = "satisfied"
        state.authority_reference = "serialized-claim"
    refreshed = world.plan_system.goal_dependency_for_agent(
        owner.id, day=1, tick=7, current_daily_event=None, goal_plan_id=plan.id,
    )
    serialized_rejected = (
        [item.status for item in refreshed.dependencies] == ["preparable", "waiting"]
    )

    seller = world.materials.sellers["seller:market_stall"]
    world.materials.transfer_good(
        seller.inventory_id, world.materials.inventory_for_agent(other.id).id,
        "reference_book", 1, day=1, hour=7,
        reason="controlled foreign ownership", authorization_type="evaluation",
        authorization_id="foreign-book", event_key="foreign-book",
    )
    foreign_inventory_rejected = (
        world.plan_system.goal_dependency_for_agent(
            owner.id, day=1, tick=8, current_daily_event=None,
            goal_plan_id=plan.id,
        ).dependencies[0].status == "preparable"
    )
    owner_inventory = world.materials.inventory_for_agent(owner.id)
    wrong_good_rejected = (
        owner_inventory.quantity("trade_materials") >= 0
        and world.plan_system.goal_dependency_for_agent(
            owner.id, day=1, tick=9, current_daily_event=None,
            goal_plan_id=plan.id,
        ).dependencies[0].status == "preparable"
    )

    world.materials.transfer_good(
        world.materials.inventory_for_agent(other.id).id, owner_inventory.id,
        "reference_book", 1, day=1, hour=10,
        reason="controlled owner acquisition", authorization_type="evaluation",
        authorization_id="owner-book", event_key="owner-book",
    )
    world.current_daily_event = DailyEvent(
        "authority-event", "Authority event", "Controlled event.",
        "library", ["learning"],
    )
    intent = world.agent_intents[owner.name]
    opportunity = world.plan_system.goal_dependency_for_agent(
        owner.id, day=1, tick=11, current_daily_event=world.current_daily_event,
        goal_plan_id=plan.id,
    )
    activity = world.activity_planner.create_intent_activity(intent, opportunity)
    world.activity_system.log_activity_event(1, 11, owner, activity)
    proof = world.activity_records[-1]
    world.materials.transfer_good(
        owner_inventory.id, seller.inventory_id, "reference_book", 1,
        day=1, hour=12, reason="controlled loss before execution",
        authorization_type="evaluation", authorization_id="book-loss",
        event_key="book-loss",
    )
    world.intent_system.update_intent_after_activity(
        day=1, agent=owner, activity_record=proof,
    )
    loss_rejected = goal.progress == 0 and not plan.evidence_records
    return world, {
        "serialized_satisfied_state": serialized_rejected,
        "another_agents_inventory": foreign_inventory_rejected,
        "wrong_good_inventory": wrong_good_rejected,
        "ownership_lost_before_execution": loss_rejected,
    }


def _intent_recreation_world(root: Path):
    world = _engine(root, "intent-recreation")
    owner = world.agents[0]
    goal = _goal(owner, "intent-recreation-goal", 2)
    owner.goals = [goal]
    with patch.object(
        world.goal_planner, "select_strategy", return_value=_candidate(DIRECT),
    ):
        world.intent_system.update_agent_intents([owner], 1, world)
    plan = world.plan_system.get_goal_plan(goal.id)
    first = world.agent_intents[owner.name]
    first.expires_day = 1
    with patch.object(
        world.goal_planner, "should_adapt", return_value=(None, "stable"),
    ):
        world.intent_system.update_agent_intents([owner], 2, world)
    successor = world.agent_intents[owner.name]
    return world, (
        first.status == "expired" and successor.id != first.id
        and successor.source_goal_plan_id == plan.id
        and successor.source_goal_plan_revision == plan.revision
        and len([item for item in world.plan_system.goal_plans
                 if item.source_goal_id == goal.id]) == 1
    )


def _delegation_attack_world(root: Path):
    world = _engine(root, "delegation-attacks")
    owner, helper = _owner_helper(world)
    goal = _goal(owner, "delegation-attack-goal", 2)
    owner.goals = [goal]
    candidate = _candidate(DELEGATION, target=helper.name)
    with patch.object(world.goal_planner, "select_strategy", return_value=candidate):
        world.intent_system.update_agent_intents([owner], 1, world)
    plan = world.plan_system.get_goal_plan(goal.id)
    base = _delegation_provenance(world, plan)
    results = {}
    for name, field, value in (
        ("wrong_owner", "owner_id", world.agents[2].id),
        ("wrong_goal", "source_goal_id", "other-goal"),
        ("wrong_plan", "plan_id", "other-plan"),
        ("wrong_revision", "revision", plan.revision + 1),
        ("wrong_strategy", "strategy", DIRECT),
        ("wrong_helper", "helper_id", world.agents[2].id),
        ("wrong_task", "task_code", "other-task"),
        ("wrong_location", "target_location", "market"),
        ("wrong_commitment", "request_id", "other-request"),
    ):
        forged = dict(base)
        forged[field] = value
        results[name] = not world.plan_system.record_delegation_request(
            forged, day=1, tick=8, session_id="forged",
        )

    provenance, item = _accept_delegation(world, owner, helper, plan)
    _fulfill_ordinary_help(
        world, owner, helper,
        {"task": "sort files", "location": "library"}, tick=7,
    )
    results["wrong_task_commitment"] = (
        world.plan_system.consume_delegation_outcomes(day=2, tick=7) == []
        and goal.progress == 0
    )
    _fulfill_ordinary_help(
        world, owner, helper,
        {"task": "help with research", "location": "cafe"}, tick=8,
    )
    results["wrong_location_commitment"] = (
        world.plan_system.consume_delegation_outcomes(day=2, tick=8) == []
        and goal.progress == 0
    )
    _fulfill_ordinary_help(
        world, owner, helper,
        {"task": "help with research", "location": "library"}, tick=9,
    )
    results["wrong_unbound_commitment"] = (
        world.plan_system.consume_delegation_outcomes(day=2, tick=9) == []
        and goal.progress == 0
    )
    other_helper = world.agents[2]
    _fulfill_ordinary_help(
        world, owner, other_helper,
        {"task": "help with research", "location": "library"}, tick=10,
    )
    results["another_helper_commitment"] = (
        world.plan_system.consume_delegation_outcomes(day=2, tick=10) == []
        and goal.progress == 0
    )

    world.commitment_system.transition(
        item.id, "fulfilled", day=2, tick=8, reason="forged",
        evidence={"activity_event_key": "forged-event"},
    )
    results["forged_fulfillment"] = (
        world.plan_system.consume_delegation_outcomes(day=2, tick=8) == []
        and goal.progress == 0
    )
    world.plan_system.ensure_commitment_plans(2)
    results["acceptance_zero_progress"] = goal.progress == 0
    results["request_zero_progress"] = bool(provenance) and goal.progress == 0
    return world, results


def _adaptation_budget_world(root: Path):
    world = _engine(root, "adaptation-budget")
    owner = world.agents[0]
    goal = _goal(owner, "adaptation-budget-goal", 9)
    owner.goals = [goal]
    with patch.object(
        world.goal_planner, "select_strategy", return_value=_candidate(DIRECT),
    ):
        world.intent_system.update_agent_intents([owner], 1, world)
    plan = world.plan_system.get_goal_plan(goal.id)
    results = []
    for day, name in enumerate(
        ("observe_relevant_activity", DIRECT,
         "observe_relevant_activity", DIRECT), start=2,
    ):
        results.append(world.plan_system.adapt_goal_plan(
            plan, _candidate(name), day=day, trigger="freeze-budget",
            preserved_progress=goal.progress, goal_planner=world.goal_planner,
        ))
    world.plan_system.synchronize_goal_plan(goal, day=5)
    return world, plan, results


def _terminal_delegation_world(root: Path):
    world = _engine(root, "terminal-delegation")
    owner, helper = _owner_helper(world)
    goal = _goal(owner, "terminal-delegation-goal", 2)
    owner.goals = [goal]
    with patch.object(
        world.goal_planner, "select_strategy",
        return_value=_candidate(DELEGATION, target=helper.name),
    ):
        world.intent_system.update_agent_intents([owner], 1, world)
    plan = world.plan_system.get_goal_plan(goal.id)
    provenance = _delegation_provenance(world, plan)
    world.plan_system.record_delegation_request(
        provenance, day=1, tick=8, session_id="terminal-delegation",
    )
    item = world.commitment_system.process_response(
        proposer_id=owner.id, counterpart_id=helper.id,
        proposal_text="Could you help me with research at the library tomorrow?",
        response_text="No, I cannot.", outcome="declined", day=1, tick=8,
        session_id="terminal-delegation", proposal_turn=0, response_turn=1,
        bounded_goal_delegation=provenance,
    )
    world.plan_system.link_delegation_commitment(
        provenance, item, day=1, tick=8,
    )
    no_progress = (
        item.status == "declined"
        and world.plan_system.consume_delegation_outcomes(day=1, tick=9) == []
        and goal.progress == 0
    )
    previous_revision = plan.revision
    world.intent_system.update_agent_intents([owner], 2, world)
    adapted = (
        plan.revision == previous_revision + 1
        and plan.strategy_name != DELEGATION and goal.progress == 0
    )
    return world, no_progress, adapted


def evaluate_v4_freeze() -> dict:
    scenarios: dict[str, bool] = {}
    diagnostics: dict[str, str] = {}
    worlds = []
    with _isolated_random_state(), TemporaryDirectory() as directory:
        root = Path(directory)

        # One shared world: two independent goals and the complete cross-phase path.
        world = _engine(root, "integrated")
        worlds.append(world)
        owner, helper, owner_goal, helper_goal = _bind_two_goals(world)
        owner_plan = world.plan_system.get_goal_plan(owner_goal.id)
        helper_plan = world.plan_system.get_goal_plan(helper_goal.id)
        initial_plan_id = owner_plan.id
        initial_intent = world.agent_intents[owner.name]
        initial_currency = world.economy.total_currency()
        initial_materials = world.materials.total_quantities()
        scenarios["two_independent_goal_plans_coexist"] = (
            owner_plan.id != helper_plan.id
            and owner_plan.agent_id == owner.id and helper_plan.agent_id == helper.id
        )
        scenarios["strategy_selection_and_intent_creation_are_not_execution"] = (
            owner_goal.progress == helper_goal.progress == 0
            and not owner_plan.evidence_records and not helper_plan.evidence_records
        )

        world = _save_reload(world, root, "integrated", 1, 7)
        worlds[-1] = world
        owner, helper = _owner_helper(world)
        owner_goal = owner.get_goal("freeze-owner-goal")
        helper_goal = helper.get_goal("freeze-helper-goal")
        owner_plan = world.plan_system.get_goal_plan(owner_goal.id)
        helper_plan = world.plan_system.get_goal_plan(helper_goal.id)
        scenarios["resume_before_execution_preserves_stable_plan_identity"] = (
            owner_plan.id == initial_plan_id and owner_plan.revision == 0
            and len([p for p in world.plan_system.goal_plans
                     if p.source_goal_id == owner_goal.id]) == 1
        )

        purchase, _ = _run_actor(world, owner, 1, 8)
        scenarios["real_purchase_prepares_without_goal_progress"] = (
            purchase["activity_id"] == "goal_acquire_reference_book"
            and owner_goal.progress == 0
            and world.materials.inventory_for_agent(owner.id).quantity(
                "reference_book"
            ) == 1
        )
        scenarios["planner_stages_only_one_preparation_mutation"] = (
            len(world.materials.exchanges) == 1
            and purchase["activity_id"] != strategy_contract(COMPOSITE).activity_id
        )
        exchange = world.materials.exchanges[-1]
        purchase_snapshot = (
            len(world.materials.exchanges), len(world.economy.ledger),
            world.economy.account_for_agent(owner.id).balance,
        )
        try:
            world.materials.purchase(
                exchange.buyer_inventory_id, exchange.buyer_account_id,
                exchange.seller_id, exchange.good_id, exchange.quantity,
                day=1, hour=8, event_key=exchange.event_key,
            )
        except MaterialError as error:
            purchase_rejected = error.code == "duplicate_event"
        else:
            purchase_rejected = False
        scenarios["purchase_replay_cannot_charge_twice"] = (
            purchase_rejected and purchase_snapshot == (
                len(world.materials.exchanges), len(world.economy.ledger),
                world.economy.account_for_agent(owner.id).balance,
            )
        )
        scenarios["purchase_conserves_money_and_stock"] = (
            world.economy.total_currency() == initial_currency
            and world.materials.total_quantities() == initial_materials
        )

        world = _save_reload(world, root, "integrated", 1, 9)
        worlds[-1] = world
        owner, helper = _owner_helper(world)
        owner_goal = owner.get_goal("freeze-owner-goal")
        helper_goal = helper.get_goal("freeze-helper-goal")
        owner_plan = world.plan_system.get_goal_plan(owner_goal.id)
        helper_plan = world.plan_system.get_goal_plan(helper_goal.id)
        states = world.plan_system.refresh_goal_dependency(
            owner_plan, day=2, tick=7, current_daily_event=None,
        )
        scenarios["resume_after_purchase_rechecks_event_authority"] = (
            [state.status for state in states] == ["satisfied", "waiting"]
            and len(world.materials.exchanges) == 1
        )
        world.current_daily_event = DailyEvent(
            "freeze-book-club", "Book club", "Residents study together.",
            "library", ["learning"],
        )
        intent = world.agent_intents[owner.name]
        dependency = world.plan_system.goal_dependency_for_agent(
            owner.id, day=2, tick=8,
            current_daily_event=world.current_daily_event,
            goal_plan_id=owner_plan.id,
        )
        activity = world.activity_planner.create_intent_activity(intent, dependency)
        world.activity_system.log_activity_event(2, 8, owner, activity)
        base_record = world.activity_records[-1]
        attack_results = _provenance_attack_matrix(
            world, owner, owner_goal, owner_plan, base_record,
        )
        for name, passed in attack_results.items():
            scenarios[f"activity_provenance_{name}_fails_closed"] = passed
        owner.remember(Memory(
            day=2, hour=8, type="conversation",
            description="I already completed the research.",
            participants=[owner.name], location="library", importance=2,
            sentiment=1, tags=["claim"],
        ))
        scenarios["dialogue_and_memory_claims_are_not_execution"] = (
            owner_goal.progress == 0 and not owner_plan.evidence_records
        )
        world.current_daily_event = DailyEvent(
            "replacement-event", "Replacement", "A different event.",
            "library", ["learning"],
        )
        world.intent_system.update_intent_after_activity(
            day=2, agent=owner, activity_record=base_record,
        )
        scenarios["stale_event_identity_does_not_cross_credit"] = (
            owner_goal.progress == 0
        )
        world.current_daily_event = DailyEvent(
            "freeze-book-club", "Book club", "Residents study together.",
            "library", ["learning"],
        )
        world.intent_system.update_intent_after_activity(
            day=2, agent=owner, activity_record=base_record,
        )
        scenarios["exact_composite_execution_advances_once"] = (
            owner_goal.progress == 1 and len(owner_plan.evidence_records) == 1
        )
        world.intent_system.update_intent_after_activity(
            day=2, agent=owner, activity_record=base_record,
        )
        scenarios["duplicate_goal_evidence_key_is_idempotent"] = (
            owner_goal.progress == 1 and len(owner_plan.evidence_records) == 1
        )

        old_record = deepcopy(base_record)
        adapted = world.plan_system.adapt_goal_plan(
            owner_plan, _candidate(DELEGATION, target=helper.name), day=3,
            trigger="relationship", preserved_progress=owner_goal.progress,
            goal_planner=world.goal_planner,
        )
        world.intent_system.update_agent_intents([owner, helper], 3, world)
        owner_plan = world.plan_system.get_goal_plan(owner_goal.id)
        scenarios["adaptation_preserves_progress_and_stable_identity"] = (
            adapted and owner_plan.id == initial_plan_id and owner_plan.revision == 1
            and owner_goal.progress == 1
        )
        world.intent_system.update_intent_after_activity(
            day=3, agent=owner, activity_record=old_record,
        )
        scenarios["superseded_revision_proof_cannot_cross_credit"] = (
            owner_goal.progress == 1
            and initial_intent.source_goal_plan_revision == 0
        )

        relationship_before = world.relationships.get_score(owner.name, helper.name)
        provenance, delegated = _accept_delegation(
            world, owner, helper, owner_plan, day=3, tick=8,
        )
        scenarios["request_and_acceptance_give_zero_progress"] = (
            owner_goal.progress == 1 and delegated.status == "accepted"
        )
        world.plan_system.ensure_commitment_plans(3)
        scenarios["helper_owns_normal_v3_plan_and_requester_cannot_execute_it"] = (
            any(p.source_id == delegated.id and p.agent_id == helper.id
                for p in world.plan_system.plans)
            and not any(op.commitment_id == delegated.id for op in
                        world.plan_system.opportunities_for_agent(
                            owner.id, day=4, tick=8,
                        ))
        )
        scenarios["helper_independent_goal_survives_delegation"] = (
            helper_goal.status == "active" and helper_plan.status == "active"
            and helper_goal.progress == 0
        )

        world = _save_reload(world, root, "integrated", 3, 9)
        worlds[-1] = world
        owner, helper = _owner_helper(world)
        owner_goal = owner.get_goal("freeze-owner-goal")
        helper_goal = helper.get_goal("freeze-helper-goal")
        owner_plan = world.plan_system.get_goal_plan(owner_goal.id)
        helper_plan = world.plan_system.get_goal_plan(helper_goal.id)
        delegated = world.commitment_system.get(delegated.id)
        scenarios["resume_after_acceptance_preserves_exact_binding"] = (
            owner_plan.delegation.linked_commitment_id == delegated.id
            and owner_plan.delegation.request_id == provenance["request_id"]
            and len([c for c in world.commitment_system.commitments
                     if c.metadata.get("goal_delegation", {}).get("request_id")
                     == provenance["request_id"]]) == 1
        )
        owner.location_id = helper.location_id = "library"
        helper_record, outcomes = _run_actor(world, helper, 4, 8)
        scenarios["helper_arbitration_executes_authoritative_commitment_help"] = (
            helper_record["activity_id"] == "commitment_help"
            and helper_record["source_commitment_id"] == delegated.id
            and delegated.status == "fulfilled"
        )
        scenarios["delegation_fulfillment_advances_requester_exactly_once"] = (
            owner_goal.progress == 2 and len(outcomes) == 1
            and len(owner_plan.evidence_records) == 2
        )
        scenarios["delegated_work_does_not_advance_helpers_private_goal"] = (
            helper_goal.progress == 0 and helper_plan.status == "active"
        )
        social_after = world.relationships.get_score(owner.name, helper.name)
        replay_outcomes = world.plan_system.consume_delegation_outcomes(
            day=4, tick=9,
        )
        scenarios["delegation_consumption_does_not_duplicate_social_effects"] = (
            replay_outcomes == [] and social_after == relationship_before + 1
            and world.relationships.get_score(owner.name, helper.name) == social_after
        )
        v3_plan = next(p for p in world.plan_system.plans
                       if p.source_id == delegated.id)
        v3_step = v3_plan.steps[0]
        execution_count = len(world.plan_system.execution_records)
        world.plan_system.record_execution(
            v3_plan.id, v3_step.id, day=4, tick=9,
            execution_key=v3_step.execution_key,
            source_commitment_id=delegated.id, action_type="commitment_help",
        )
        scenarios["duplicate_execution_key_is_idempotent"] = (
            len(world.plan_system.execution_records) == execution_count
        )

        # Complete the owner with another registered strategy, leaving helper independent.
        owner_plan = world.plan_system.get_goal_plan(owner_goal.id)
        world.plan_system.adapt_goal_plan(
            owner_plan, _candidate(DIRECT), day=5, trigger="delegation_fulfilled",
            preserved_progress=owner_goal.progress, goal_planner=world.goal_planner,
        )
        world.intent_system.update_agent_intents([owner, helper], 5, world)
        final_record, _ = _run_actor(world, owner, 5, 8)
        scenarios["multi_revision_lifecycle_completes_from_exact_final_action"] = (
            final_record["activity_id"] == "goal_seek_information"
            and owner_goal.progress == 3 and owner_goal.status == "achieved"
            and owner_plan.status == "completed" and owner_plan.revision == 2
        )
        scenarios["one_goal_completion_does_not_terminalize_another"] = (
            helper_goal.status == "active" and helper_plan.status == "active"
        )
        terminal_snapshot = deepcopy(owner_plan.to_dict())
        world.plan_system.ensure_goal_plan(
            owner_goal, owner, world, world.goal_planner, 6,
        )
        scenarios["terminal_goal_plan_cannot_reopen"] = (
            owner_plan.to_dict() == terminal_snapshot
            and len([p for p in world.plan_system.goal_plans
                     if p.source_goal_id == owner_goal.id]) == 1
        )

        world = _save_reload(world, root, "integrated", 5, 9)
        worlds[-1] = world
        owner, helper = _owner_helper(world)
        owner_goal = owner.get_goal("freeze-owner-goal")
        helper_goal = helper.get_goal("freeze-helper-goal")
        owner_plan = world.plan_system.get_goal_plan(owner_goal.id)
        helper_plan = world.plan_system.get_goal_plan(helper_goal.id)
        before_resume = (owner_goal.progress, len(owner_plan.evidence_records),
                         len(world.materials.exchanges), len(world.commitment_system.commitments))
        world.intent_system.update_intent_after_activity(
            day=6, agent=owner, activity_record=world.activity_records[-1],
        )
        world.plan_system.consume_delegation_outcomes(day=6, tick=8)
        scenarios["resume_after_execution_cannot_duplicate_any_effect"] = (
            before_resume == (
                owner_goal.progress, len(owner_plan.evidence_records),
                len(world.materials.exchanges), len(world.commitment_system.commitments),
            )
        )

        # Authority denial matrix: no route means no invented resource.
        for name, passed in _route_denial_checks(root).items():
            scenarios[f"no_{name}_means_no_invented_acquisition"] = passed

        authority_world, authority_checks = _dependency_authority_world(root)
        worlds.append(authority_world)
        for name, passed in authority_checks.items():
            scenarios[f"dependency_authority_rejects_{name}"] = passed

        recreation_world, recreation_passed = _intent_recreation_world(root)
        worlds.append(recreation_world)
        scenarios["intent_expiration_reuses_one_stable_goal_plan"] = (
            recreation_passed
        )

        attack_world, delegation_attacks = _delegation_attack_world(root)
        worlds.append(attack_world)
        for name, passed in delegation_attacks.items():
            scenarios[f"delegation_{name}_fails_closed"] = passed

        terminal_world, terminal_no_progress, terminal_adapted = (
            _terminal_delegation_world(root)
        )
        worlds.append(terminal_world)
        scenarios["terminal_nonfulfillment_gives_zero_goal_progress"] = (
            terminal_no_progress
        )
        scenarios["terminal_delegation_failure_selects_registered_replacement"] = (
            terminal_adapted
        )

        # Stale-revision fulfillment is valid V3, but cannot credit the new goal revision.
        stale = _engine(root, "stale-delegation")
        worlds.append(stale)
        stale_owner, stale_helper = _owner_helper(stale)
        stale_goal = _goal(stale_owner, "stale-delegation-goal", 2)
        stale_owner.goals = [stale_goal]
        with patch.object(
            stale.goal_planner, "select_strategy",
            return_value=_candidate(DELEGATION, target=stale_helper.name),
        ):
            stale.intent_system.update_agent_intents([stale_owner], 1, stale)
        stale_plan = stale.plan_system.get_goal_plan(stale_goal.id)
        _stale_provenance, stale_item = _accept_delegation(
            stale, stale_owner, stale_helper, stale_plan, day=1, tick=8,
        )
        stale.plan_system.adapt_goal_plan(
            stale_plan, _candidate(DIRECT), day=2, trigger="freeze-stale",
            preserved_progress=0, goal_planner=stale.goal_planner,
        )
        stale_owner.location_id = stale_helper.location_id = "library"
        stale.plan_system.ensure_commitment_plans(2)
        stale_op = next(op for op in stale.plan_system.opportunities_for_agent(
            stale_helper.id, day=2, tick=8,
        ) if op.commitment_id == stale_item.id)
        stale_activity = stale.activity_planner.create_commitment_activity(
            stale_helper, stale_op,
        )
        stale_execution = stale.commitment_system.execute_activity(
            commitment_id=stale_item.id, agent_id=stale_helper.id, day=2, tick=8,
            activity_record={"activity_id": stale_activity.id,
                             "location": stale_activity.location_id},
        )
        stale.plan_system.record_execution(
            stale_op.plan_id, stale_op.step_id, day=2, tick=8,
            execution_key=stale_execution["event_key"],
            source_commitment_id=stale_item.id, action_type=stale_activity.id,
        )
        scenarios["stale_revision_fulfillment_is_valid_v3_but_zero_goal_credit"] = (
            stale_item.status == "fulfilled"
            and stale.plan_system.consume_delegation_outcomes(day=2, tick=8) == []
            and stale_goal.progress == 0
        )

        budget_world, budget_plan, budget_results = _adaptation_budget_world(root)
        worlds.append(budget_world)
        scenarios["adaptation_budget_stops_infinite_replanning"] = (
            budget_results == [True, True, True, False]
            and budget_plan.revision == PlanSystem.MAX_GOAL_ADAPTATIONS
            and budget_plan.status == "blocked"
            and budget_plan.terminal_reason == "adaptation_budget_exhausted"
        )

        # Real batched conversation bridge in its own controlled world.
        batch = _engine(root, "batch", accepting=True)
        worlds.append(batch)
        b_owner, b_helper = _owner_helper(batch)
        b_goal = _goal(b_owner, "batch-goal", 2)
        b_owner.goals = [b_goal]
        with patch.object(
            batch.goal_planner, "select_strategy",
            return_value=_candidate(DELEGATION, target=b_helper.name),
        ):
            batch.intent_system.update_agent_intents([b_owner], 1, batch)
        b_owner.location_id = b_helper.location_id = "library"
        batch.agents[2].location_id = "town_square"
        batch.agents[3].location_id = "market"
        batch.conversation_runner.max_turns = 2
        batch.generate_conversations(1, 8)
        batch_commitments = [
            item for item in batch.commitment_system.commitments
            if item.metadata.get("task_code") == "goal_research_help"
        ]
        scenarios["batched_dialogue_creates_one_bounded_commitment"] = (
            len(batch_commitments) == 1
            and batch.last_social_tick["worker_failures"] == []
            and batch.last_social_tick["commit_order"]
            == batch.last_social_tick["schedule_order"]
        )
        log_text = batch.logger.events_file.read_text()
        scenarios["batching_does_not_expose_private_plan_mechanics"] = (
            "goal-delegation:" not in log_text and "source_goal_id" not in log_text
        )

        # Thirty-day projection over the integrated save: stable terminal bindings
        # and bounded collections must survive repeated normal synchronization.
        with redirect_stdout(StringIO()):
            for day in range(7, 37):
                world.intent_system.update_agent_intents(world.agents, day, world)
                world.run_agent_activities(day, 8)
                world.plan_system.ensure_commitment_plans(day)
                world.plan_system.consume_delegation_outcomes(day=day, tick=8)
        scenarios["thirty_day_horizon_has_no_runaway_goal_plans"] = all(
            len([p for p in world.plan_system.goal_plans
                 if p.source_goal_id == goal.id]) == 1
            for agent in world.agents for goal in agent.goals
            if world.plan_system.get_goal_plan(goal.id) is not None
        )
        scenarios["thirty_day_horizon_keeps_terminal_plan_terminal"] = (
            owner_plan.status == "completed" and owner_goal.status == "achieved"
            and owner_plan.id == initial_plan_id
        )
        scenarios["thirty_day_horizon_does_not_repeat_delegation_request"] = (
            len([c for c in world.commitment_system.commitments
                 if isinstance(c.metadata.get("goal_delegation"), dict)
                 and c.metadata["goal_delegation"].get("request_id")
                 == provenance["request_id"]]) == 1
        )

        # Shared freeze-level invariants, aggregating subsystem validators.
        plan_checks = [
            current.plan_system.validate_invariants(current.goal_planner)
            for current in worlds
        ]
        commitment_checks = [
            current.commitment_system.validate_invariants() for current in worlds
        ]
        material_checks = [{
            "conservation": current.materials.material_conservation_holds(),
            "history": current.materials.material_history_reconstructs_inventories(),
            "exchange_ledger": current.materials.exchanges_reconcile_with_ledger(),
            "provenance": current.materials.provenance_reconciles(),
            "provenance_history": (
                current.materials.provenance_history_reconstructs_holdings()
            ),
            "lot_movements": current.materials.lot_movements_reconcile_with_events(),
        } for current in worlds]
        memory_checks = [current.outcome_memory.validate() for current in worlds]
        all_goal_plans = [
            plan for current in worlds for plan in current.plan_system.goal_plans
        ]
        all_goals = [goal for current in worlds for agent in current.agents
                     for goal in agent.goals]
        invariants = {
            "all_strategies_have_registered_execution_contracts": all(
                contract.strategy == name
                for name, contract in GOAL_STRATEGY_EXECUTION_CONTRACTS.items()
            ),
            "all_persisted_goal_plans_use_known_strategies": all(
                plan.strategy_name in GOAL_STRATEGY_EXECUTION_CONTRACTS
                for plan in all_goal_plans
            ),
            "goal_plan_ids_are_stable_owner_goal_scoped": all(
                plan.id == PlanSystem.goal_plan_id_for(
                    plan.agent_id, plan.source_goal_id,
                ) for plan in all_goal_plans
            ),
            "goal_and_plan_evidence_keys_are_unique": all(
                len(goal.processed_evidence_keys)
                == len(set(goal.processed_evidence_keys)) for goal in all_goals
            ) and all(
                len(plan.processed_evidence_keys)
                == len(set(plan.processed_evidence_keys)) for plan in all_goal_plans
            ),
            "goal_plan_evidence_mirrors_accepted_goal_evidence": all(
                all(any(goal_record.get("evidence_key") == record.get("evidence_key")
                        for goal_record in next(
                            goal for goal in all_goals
                            if goal.id == plan.source_goal_id
                            and goal.agent_name == next(
                                agent.name for current in worlds for agent in current.agents
                                if agent.id == plan.agent_id
                            )
                        ).evidence)
                    for record in plan.evidence_records)
                for plan in all_goal_plans
            ),
            "dependencies_are_known_bounded_and_current_revision": all(
                len(plan.dependencies) <= MAX_STRATEGY_DEPENDENCIES
                and all(state.kind in DEPENDENCY_KINDS
                        and state.revision == plan.revision
                        and len(state.transitions) <= 20
                        for state in plan.dependencies)
                for plan in all_goal_plans
            ),
            "delegation_bindings_are_bounded_and_exact": all(
                checks["valid_goal_delegation_bindings"]
                and checks.get("linked_goal_commitments_match_bindings", True)
                and checks.get("one_goal_commitment_per_request", True)
                for checks in plan_checks
            ),
            "execution_proofs_match_declared_sources": all(
                checks["execution_matches_source"] and checks["execution_unique"]
                for checks in plan_checks
            ),
            "terminal_goal_plans_have_no_new_evidence": (
                owner_plan.status == "completed"
                and len(owner_plan.evidence_records) == 3
            ),
            "active_goal_plans_reference_active_goals": all(
                checks["active_goal_plan_has_active_source"] for checks in plan_checks
            ),
            "plan_invariants_hold": all(
                all(checks.values()) for checks in plan_checks
            ),
            "commitment_invariants_hold": all(
                all(checks.values()) for checks in commitment_checks
            ),
            "material_invariants_hold": all(
                all(checks.values()) for checks in material_checks
            ),
            "economy_conservation_holds": all(
                current.economy.conservation_holds() for current in worlds
            ),
            "outcome_memory_provenance_holds": all(
                all(checks.values()) for checks in memory_checks
            ),
            "audit_collections_remain_bounded": all(
                len(plan.transitions) <= 50
                and len(plan.evidence_records) <= 50
                and len(plan.processed_evidence_keys) <= 50
                and (plan.delegation is None
                     or len(plan.delegation.transitions) <= 20)
                for plan in all_goal_plans
            ),
        }

    for name, passed in {**scenarios, **invariants}.items():
        if not passed:
            diagnostics[name] = "whole-V4 deterministic contract check failed"
    return {
        "passed": not diagnostics,
        "scenario_count": len(scenarios),
        "scenarios_passed": sum(scenarios.values()),
        "invariant_count": len(invariants),
        "invariants_passed": sum(invariants.values()),
        "scenarios": scenarios,
        "invariants": invariants,
        "diagnostics": diagnostics,
    }
