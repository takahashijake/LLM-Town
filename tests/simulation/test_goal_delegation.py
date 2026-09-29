from copy import deepcopy
import json
from unittest.mock import patch

import pytest

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


class AcceptingFakeLLM(FakeLLMClient):
    def generate_conversation(self, context):
        if context.get("session_transcript"):
            return '{"dialogue":"Yes, I can help with that tomorrow.","action":"offer_help"}'
        return super().generate_conversation(context)


def build_engine(tmp_path, name="delegation"):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=False,
        llm_client=FakeLLMClient(), state_path=tmp_path / f"{name}.json",
        logs_dir=tmp_path / f"{name}-logs",
    )


def bind_delegation(engine, *, goal_id="goal-delegated-research"):
    owner, helper = engine.agents[:2]
    goal = Goal(
        id=goal_id, agent_name=owner.name,
        description="Investigate the town records with reliable help",
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
        side_effect=lambda selected_goal, agent, world: (
            candidate if selected_goal.id == goal.id
            else original(selected_goal, agent, world)
        ),
    ):
        engine.update_agent_intents(1)
    return owner, helper, goal, engine.plan_system.get_goal_plan(goal.id)


def provenance(engine):
    request = engine.plan_system.delegation_requests()[0]
    keys = (
        "owner_id", "source_goal_id", "plan_id", "revision", "strategy",
        "helper_id", "task_code", "target_location", "request_id",
    )
    return {key: request[key] for key in keys}


def respond(engine, owner, helper, *, outcome="accepted", day=1):
    proof = provenance(engine)
    assert engine.plan_system.record_delegation_request(
        proof, day=day, tick=8, session_id="session-delegation",
    )
    item = engine.commitment_system.process_response(
        proposer_id=owner.id, counterpart_id=helper.id,
        proposal_text="Could you help me with research at the library tomorrow?",
        response_text=("Yes, I can help tomorrow." if outcome == "accepted"
                       else "No, I cannot help tomorrow."),
        outcome=outcome, day=day, tick=8, session_id="session-delegation",
        proposal_turn=0, response_turn=1,
        bounded_goal_delegation=proof,
    )
    assert engine.plan_system.link_delegation_commitment(
        proof, item, day=day, tick=8,
    )
    return item


def fulfill(engine, owner, helper, item, *, day=2, tick=8):
    owner.location_id = helper.location_id = "library"
    engine.plan_system.ensure_commitment_plans(day)
    opportunity = engine.plan_system.opportunities_for_agent(
        helper.id, day=day, tick=tick,
    )[0]
    activity = engine.activity_planner.create_commitment_activity(helper, opportunity)
    record = {
        "activity_id": activity.id, "location": activity.location_id,
    }
    execution = engine.commitment_system.execute_activity(
        commitment_id=item.id, agent_id=helper.id, day=day, tick=tick,
        activity_record=record,
    )
    engine.plan_system.record_execution(
        opportunity.plan_id, opportunity.step_id, day=day, tick=tick,
        execution_key=execution["event_key"], source_commitment_id=item.id,
        action_type="commitment_help",
    )
    return execution


def test_delegation_contract_is_finite_and_selects_reliable_helper(tmp_path):
    engine = build_engine(tmp_path)
    owner = engine.agents[0]
    goal = Goal(
        id="goal-selection", agent_name=owner.name, description="Research",
        category="increase_knowledge", priority=5, created_day=1, review_day=7,
        target_locations=["library"],
    )
    candidates = engine.goal_planner.generate_strategies(goal, owner, engine)
    delegated = next(item for item in candidates if item.name == STRATEGY)
    expected = engine.goal_planner._best_social_target(
        owner, engine, [agent.name for agent in engine.agents if agent is not owner],
    )
    contract = strategy_contract(STRATEGY)
    assert delegated.target_agent == expected
    assert delegated.target_location == "library"
    assert contract.delegated_task_code == TASK_CODE
    assert contract.delegated_commitment_type == "help"


def test_request_and_acceptance_do_not_progress_goal(tmp_path):
    engine = build_engine(tmp_path)
    owner, helper, goal, plan = bind_delegation(engine)
    item = respond(engine, owner, helper)
    assert goal.progress == 0 and not plan.evidence_records
    assert item.status == "accepted"
    assert item.proposer_id == owner.id and item.counterpart_id == helper.id
    assert item.metadata["task_code"] == TASK_CODE
    assert plan.delegation.linked_commitment_id == item.id
    assert set(plan.delegation.to_dict() if hasattr(plan.delegation, "to_dict") else vars(plan.delegation)) >= {
        "owner_id", "source_goal_id", "plan_id", "revision", "strategy",
        "helper_id", "task_code", "target_location", "linked_commitment_id",
    }


def test_unaccepted_request_is_single_and_gives_zero_progress(tmp_path):
    engine = build_engine(tmp_path)
    _owner, _helper, goal, plan = bind_delegation(engine)
    proof = provenance(engine)
    assert engine.plan_system.record_delegation_request(
        proof, day=1, tick=8, session_id="unanswered",
    )
    engine.plan_system.mark_delegation_waiting(proof, day=1, tick=8)
    assert goal.progress == 0
    assert plan.delegation.status == "waiting_response"
    assert engine.plan_system.delegation_requests() == []


def test_real_conversation_session_creates_one_bounded_commitment_privately(tmp_path):
    engine = build_engine(tmp_path)
    engine.llm = AcceptingFakeLLM()
    owner, helper, goal, plan = bind_delegation(engine)
    owner.location_id = helper.location_id = "library"
    engine.agents[2].location_id = "town_square"
    engine.agents[3].location_id = "market"
    engine.conversation_runner.max_turns = 2
    engine.generate_conversations(1, 8)
    linked = [item for item in engine.commitment_system.commitments
              if item.metadata.get("task_code") == TASK_CODE]
    assert len(linked) == 1 and linked[0].status == "accepted"
    assert plan.delegation.linked_commitment_id == linked[0].id
    assert goal.progress == 0
    events = [json.loads(line) for line in engine.logger.events_file.read_text().splitlines()
              if line.strip()]
    assert all("goal-delegation:" not in str(event) for event in events)


def test_helper_gets_normal_plan_and_requester_cannot_execute(tmp_path):
    engine = build_engine(tmp_path)
    owner, helper, goal, _plan = bind_delegation(engine)
    item = respond(engine, owner, helper)
    engine.plan_system.ensure_commitment_plans(2)
    opportunities = engine.plan_system.opportunities_for_agent(
        helper.id, day=2, tick=8,
    )
    assert len(opportunities) == 1
    assert opportunities[0].action_type == "commitment_help"
    assert engine.plan_system.opportunities_for_agent(owner.id, day=2, tick=8) == []
    with pytest.raises(ValueError):
        engine.commitment_system.execute_activity(
            commitment_id=item.id, agent_id=owner.id, day=2, tick=8,
            activity_record={"activity_id": "commitment_help", "location": "library"},
        )
    assert goal.progress == 0 and item.status == "accepted"


def test_authoritative_fulfillment_progresses_exactly_once(tmp_path):
    engine = build_engine(tmp_path)
    owner, helper, goal, plan = bind_delegation(engine)
    item = respond(engine, owner, helper)
    before_score = engine.relationships.get_score(owner.name, helper.name)
    fulfill(engine, owner, helper, item)
    assert item.status == "fulfilled"
    first = engine.plan_system.consume_delegation_outcomes(day=2, tick=8)
    second = engine.plan_system.consume_delegation_outcomes(day=2, tick=9)
    assert len(first) == 1 and second == []
    assert goal.progress == 1 and len(plan.evidence_records) == 1
    assert plan.evidence_records[0]["linked_commitment_id"] == item.id
    assert engine.relationships.get_score(owner.name, helper.name) == before_score + 1
    assert item.consequence_applied


def test_normal_activity_runtime_completes_vertical_slice(tmp_path):
    engine = build_engine(tmp_path, "runtime")
    owner, helper, goal, plan = bind_delegation(engine, goal_id="goal-runtime")
    item = respond(engine, owner, helper)
    owner.location_id = helper.location_id = "library"
    engine.current_daily_event = DailyEvent(
        "research_day", "Research day", "Residents study together.",
        "library", ["learning"],
    )
    with patch("random.random", return_value=0.1):
        engine.run_agent_activities(2, 8)
    helper_record = next(row for row in engine.activity_records
                         if row["day"] == 2 and row["hour"] == 8
                         and row["agent"] == helper.name)
    assert helper_record["activity_id"] == "commitment_help"
    assert helper_record["source_commitment_id"] == item.id
    assert item.status == "fulfilled" and goal.progress == 1
    assert len(plan.evidence_records) == 1


@pytest.mark.parametrize("status", ("declined", "failed", "cancelled", "expired"))
def test_terminal_nonfulfillment_never_progresses(tmp_path, status):
    engine = build_engine(tmp_path, status)
    owner, helper, goal, plan = bind_delegation(engine, goal_id=f"goal-{status}")
    if status == "declined":
        item = respond(engine, owner, helper, outcome="declined")
    else:
        item = respond(engine, owner, helper)
        engine.commitment_system.transition(
            item.id, status, day=2, tick=8, reason=f"test_{status}",
            evidence=({"session_id": "cancel", "turn_index": 0}
                      if status == "cancelled" else None),
        )
    assert engine.plan_system.consume_delegation_outcomes(day=2, tick=8) == []
    assert goal.progress == 0
    assert engine.plan_system.refresh_goal_delegation(
        plan, day=2, tick=8,
    ) == status


def test_stale_revision_fulfillment_completes_commitment_without_cross_credit(tmp_path):
    engine = build_engine(tmp_path)
    owner, helper, goal, plan = bind_delegation(engine)
    item = respond(engine, owner, helper)
    replacement = next(candidate for candidate in
                       engine.goal_planner.generate_strategies(goal, owner, engine)
                       if candidate.name == "seek_information_at_location")
    assert engine.plan_system.adapt_goal_plan(
        plan, replacement, day=2, trigger="test", preserved_progress=0,
        goal_planner=engine.goal_planner,
    )
    fulfill(engine, owner, helper, item, day=2)
    assert item.status == "fulfilled"
    assert engine.plan_system.consume_delegation_outcomes(day=2, tick=8) == []
    assert goal.progress == 0 and plan.revision == 1 and plan.delegation is None


def test_terminal_failure_uses_bounded_adaptation_instead_of_retry(tmp_path):
    engine = build_engine(tmp_path)
    owner, helper, goal, plan = bind_delegation(engine)
    respond(engine, owner, helper, outcome="declined")
    old_revision = plan.revision
    engine.update_agent_intents(2)
    assert plan.revision == old_revision + 1
    assert not (
        plan.strategy_name == STRATEGY and plan.target_agent == helper.name
    )
    assert goal.status == "active"


@pytest.mark.parametrize("field,value", (
    ("owner_id", "agent_999"),
    ("source_goal_id", "other-goal"),
    ("plan_id", "other-plan"),
    ("revision", 99),
    ("helper_id", "agent_003"),
    ("task_code", "ordinary_help"),
    ("target_location", "market"),
))
def test_cross_bound_provenance_fails_closed(tmp_path, field, value):
    engine = build_engine(tmp_path, field)
    owner, helper, goal, _plan = bind_delegation(engine, goal_id=f"goal-{field}")
    forged = provenance(engine)
    forged[field] = value
    assert not engine.plan_system.record_delegation_request(
        forged, day=1, tick=8, session_id="forged",
    )
    assert goal.progress == 0 and not engine.commitment_system.commitments
    with pytest.raises(ValueError):
        engine.commitment_system.process_response(
            proposer_id=owner.id, counterpart_id=helper.id,
            proposal_text="I claim this happened", response_text="yes",
            outcome="accepted", day=1, tick=8, session_id="forged",
            proposal_turn=0, response_turn=1,
            bounded_goal_delegation=forged,
        )


def test_duplicate_response_creates_one_commitment(tmp_path):
    engine = build_engine(tmp_path)
    owner, helper, _goal, _plan = bind_delegation(engine)
    first = respond(engine, owner, helper)
    proof = first.metadata["goal_delegation"]
    duplicate = engine.commitment_system.process_response(
        proposer_id=owner.id, counterpart_id=helper.id,
        proposal_text="Could you help me with research at the library tomorrow?",
        response_text="Yes", outcome="accepted", day=1, tick=8,
        session_id="session-delegation", proposal_turn=0, response_turn=1,
        bounded_goal_delegation=proof,
    )
    assert duplicate.id == first.id
    assert len(engine.commitment_system.commitments) == 1


def test_binding_persists_and_rechecks_commitment_authority(tmp_path):
    engine = build_engine(tmp_path)
    owner, helper, goal, plan = bind_delegation(engine)
    item = respond(engine, owner, helper)
    document = deepcopy(engine.plan_system.to_dict())
    assert document["schema_version"] == PLAN_SCHEMA_VERSION == 7
    restored = PlanSystem.from_dict(
        document, commitment_system=engine.commitment_system,
        agents=engine.agents, outcome_memory=engine.outcome_memory,
        materials=engine.materials,
    )
    restored_plan = restored.get_goal_plan(goal.id)
    restored_plan.delegation.status = "fulfilled"
    assert restored.refresh_goal_delegation(
        restored_plan, day=1, tick=9,
    ) == "accepted"
    assert restored_plan.delegation.linked_commitment_id == item.id


def test_forged_commitment_fulfillment_record_does_not_progress(tmp_path):
    engine = build_engine(tmp_path)
    owner, helper, goal, _plan = bind_delegation(engine)
    item = respond(engine, owner, helper)
    engine.commitment_system.transition(
        item.id, "fulfilled", day=2, tick=8, reason="forged",
        evidence={"activity_event_key": "forged"},
    )
    assert engine.plan_system.consume_delegation_outcomes(day=2, tick=8) == []
    assert goal.progress == 0


def test_restored_fulfillment_cannot_replay_goal_progress(tmp_path):
    engine = build_engine(tmp_path)
    owner, helper, goal, plan = bind_delegation(engine)
    item = respond(engine, owner, helper)
    fulfill(engine, owner, helper, item)
    assert len(engine.plan_system.consume_delegation_outcomes(day=2, tick=8)) == 1
    restored = PlanSystem.from_dict(
        deepcopy(engine.plan_system.to_dict()),
        commitment_system=engine.commitment_system, agents=engine.agents,
        outcome_memory=engine.outcome_memory, materials=engine.materials,
    )
    assert restored.consume_delegation_outcomes(day=3, tick=8) == []
    assert goal.progress == 1 and len(plan.evidence_records) == 1


def test_full_engine_save_resume_preserves_and_rechecks_binding(tmp_path):
    engine = build_engine(tmp_path, "full-resume")
    owner, helper, goal, plan = bind_delegation(engine, goal_id="goal-full-resume")
    item = respond(engine, owner, helper)
    engine.state.save(engine, 1, 8, day_complete=False)
    resumed = SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=True,
        llm_client=FakeLLMClient(), state_path=tmp_path / "full-resume.json",
        logs_dir=tmp_path / "full-resume-loaded-logs",
    )
    restored = resumed.plan_system.get_goal_plan(goal.id)
    assert restored.delegation.linked_commitment_id == item.id
    assert resumed.plan_system.refresh_goal_delegation(
        restored, day=1, tick=9,
    ) == "accepted"


def test_v6_migration_fabricates_no_delegation_and_future_fails_closed(tmp_path):
    engine = build_engine(tmp_path)
    document = engine.plan_system.to_dict()
    document["schema_version"] = 6
    restored = PlanSystem.from_dict(
        document, commitment_system=engine.commitment_system,
        agents=engine.agents, outcome_memory=engine.outcome_memory,
        materials=engine.materials,
    )
    assert all(plan.delegation is None for plan in restored.goal_plans)
    document["schema_version"] = 999
    with pytest.raises(ValueError):
        PlanSystem.from_dict(document)


def test_memory_cannot_substitute_for_authoritative_fulfillment(tmp_path):
    engine = build_engine(tmp_path)
    owner, helper, goal, plan = bind_delegation(engine)
    item = respond(engine, owner, helper)
    owner.remember(Memory(
        day=2, hour=8, type="conversation",
        description=f"{helper.name} fulfilled the research help",
        participants=[owner.name, helper.name], location="library",
        importance=3, sentiment=1, tags=["claim"],
    ))
    plan.delegation.status = "fulfilled"
    assert engine.plan_system.consume_delegation_outcomes(day=2, tick=8) == []
    assert goal.progress == 0 and item.status == "accepted"


def test_ordinary_help_commitment_cannot_cross_credit(tmp_path):
    engine = build_engine(tmp_path)
    owner, helper, goal, _plan = bind_delegation(engine)
    ordinary = engine.commitment_system.create(
        proposer_id=owner.id, counterpart_id=helper.id, commitment_type="help",
        day=1, due_day=2, status="accepted",
        metadata={"task": "help with research", "location": "library"},
    )
    fulfill(engine, owner, helper, ordinary)
    assert engine.plan_system.consume_delegation_outcomes(day=2, tick=8) == []
    assert goal.progress == 0
