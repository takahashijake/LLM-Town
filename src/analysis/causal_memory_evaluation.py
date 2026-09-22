"""Deterministic acceptance evaluation for bounded causal private memory."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.agents.memory import Memory
from src.llm.client import FakeLLMClient
from src.llm.context import MAX_CONTEXT_TEXT_CHARS, _prompt_context_text_chars
from src.simulation.engine import SimulationEngine
from src.systems.crime import CrimeSystem


def _engine(root: Path, name: str, load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=root / f"{name}.json",
        logs_dir=root / f"{name}-logs",
    )


def _accepted(engine, *, good="trade_materials", quantity=1, due=3):
    item = engine.commitment_system.create(
        proposer_id="agent_002", counterpart_id="agent_001",
        commitment_type="transfer", day=1, due_day=due,
        metadata={"good_id": good, "quantity": quantity},
    )
    return engine.commitment_system.transition(
        item.id, "accepted", day=1, reason="evaluation acceptance"
    )


def _act(engine, day, hour):
    with patch("src.behavior.planner.random.random", return_value=0.0):
        engine.activity_system.run_agent_activities(
            [engine.agents[0]], [place.id for place in engine.locations],
            day, hour, None, {},
        )


def _key(*requirements):
    for number in range(10000):
        key = f"causal-memory-{number}"
        if all(CrimeSystem.witness_observes(key, agent, ) is expected
               for agent, expected in requirements):
            return key
    raise AssertionError("no deterministic witness key")


def _steal(engine, *, witnessed):
    positions = {"agent_001": "library", "agent_002": "market",
                 "agent_003": "market" if witnessed else "library",
                 "agent_004": "market"}
    for agent in engine.agents:
        agent.location_id = positions[agent.id]
    key = _key(("agent_003", True), ("agent_004", False)) if witnessed else _key(("agent_004", False))
    return engine.crime.attempt_theft(
        actor_id="agent_002", source_inventory_id="inventory:agent:agent_004",
        good_id="trade_materials", quantity=1, day=2, hour=12,
        location_id="market", event_key=key, agents=engine.agents,
    )


def evaluate_causal_memory() -> dict:
    scenarios = {}
    with TemporaryDirectory() as directory:
        root = Path(directory)
        engine = _engine(root, "main")

        commitment = _accepted(engine)
        _act(engine, 2, 8)
        _act(engine, 2, 12)
        participants = engine.agents[:2]
        scenarios["fulfilled_promise"] = (
            commitment.status == "fulfilled"
            and all(any(m.event_type == "commitment_fulfilled" for m in a.memory)
                    for a in participants)
            and not any(m.source_id == commitment.id for m in engine.agents[2].memory)
        )

        failed = _engine(root, "failed")
        missed = _accepted(failed, good="reference_book", quantity=999, due=1)
        for hour in (8, 12, 18):
            failed.plan_system.opportunities_for_agent("agent_001", day=2, tick=hour)
        failed.commitment_system.expire_due(day=3)
        scenarios["private_plan_failure"] = (
            any(m.event_type == "plan_failed" for m in failed.agents[0].memory)
            and not any(m.event_type == "plan_failed" for m in failed.agents[1].memory)
            and any(m.event_type == "commitment_expired" for m in failed.agents[1].memory)
            and missed.status == "expired"
        )
        for agent in failed.agents[:2]:
            failed.journal_system.compress_old_memories(agent, current_day=40)
        failed_context = failed.prepare_conversation_context(
            "market", failed.agents[0], failed.agents[1], 40
        )["context"]

        crime = _engine(root, "crime")
        incident = _steal(crime, witnessed=True)
        scenarios["witnessed_theft"] = (
            any(m.source_id == incident.id for m in crime.agents[1].memory)
            and any(m.knowledge_basis == "direct_observer" and m.source_id == incident.id
                    for m in crime.agents[2].memory)
            and not any(m.source_id == incident.id for m in crime.agents[0].memory)
            and not any(m.source_id == incident.id for m in crime.agents[3].memory)
        )

        loss = _engine(root, "loss")
        hidden = _steal(loss, witnessed=False)
        loss.crime.discover_loss(
            incident_id=hidden.id, victim_id="agent_004", day=2, hour=13,
            event_key="loss-discovery",
        )
        victim_memory = next(m for m in loss.agents[3].memory
                             if m.event_type == "loss_discovered")
        scenarios["unwitnessed_loss"] = (
            victim_memory.counterpart_ids == []
            and "do not know who" in victim_memory.description
            and loss.agents[1].name not in victim_memory.description
        )

        direct = next(e for e in crime.crime.evidence
                      if e.incident_id == incident.id and e.evidence_type == "eyewitness")
        case = crime.justice.open_case(
            incident_id=incident.id, opened_by_agent_id="agent_003",
            investigator_agent_id="agent_001", trigger_evidence_id=direct.id,
            day=2, hour=13, event_key="open-causal",
        )
        decision = crime.justice.adjudicate(
            case_id=case.id, reviewer_agent_id="agent_001", day=2, hour=14,
            event_key="decide-causal",
        )
        crime.justice.apply_consequence(
            adjudication_id=decision.id, day=2, hour=15,
            event_key="consequence-causal",
        )
        scenarios["adjudication_restitution"] = all(
            any(m.event_type == "adjudicated_responsible" for m in agent.memory)
            for agent in crime.agents
        ) and all(any(m.event_type == "restitution_received" for m in agent.memory)
                  for agent in (crime.agents[1], crime.agents[3]))

        for agent in participants:
            engine.journal_system.compress_old_memories(agent, current_day=40)
        context = engine.prepare_conversation_context(
            "market", participants[0], participants[1], 40
        )["context"]
        scenarios["historical_recall"] = (
            any("fulfilled" in text for text in context["relevant_memories"])
            and len(context["relevant_memories"]) <= 3
            and _prompt_context_text_chars(context) <= MAX_CONTEXT_TEXT_CHARS
        )
        scenarios["historical_outcome_distinction"] = (
            any("fulfilled" in text and "not fulfilled" not in text
                for text in context["relevant_memories"])
            and any("not fulfilled" in text
                    for text in failed_context["relevant_memories"])
        )

        owner = participants[0]
        important_id = next(m.id for m in owner.memory_archive if m.causal)
        owner.memory_archive.extend(Memory(
            day=day, hour=1, type="conversation", description=f"ordinary {day}",
            participants=[owner.name], location="cafe", importance=1,
            sentiment=0, tags=[], id=f"pressure-{day}",
        ) for day in range(600))
        owner.summarize_archived_memories()
        scenarios["archive_pressure"] = (
            len(owner.memory_archive) == 500
            and important_id in {m.id for m in owner.memory_archive}
            and len({m.id for m in owner.memory_archive}) == 500
        )

        before = sum(m.source_id == commitment.id for a in engine.agents
                     for m in a.memory + a.memory_archive)
        engine.commitment_system._project_transition(commitment, "fulfilled", 2, 12)
        after = sum(m.source_id == commitment.id for a in engine.agents
                    for m in a.memory + a.memory_archive)
        scenarios["replay"] = before == after

        engine.state.save(engine, 40, 12)
        resumed = _engine(root, "main", load=True)
        scenarios["save_resume"] = all(
            m.to_dict() == next(x for x in resumed.agents[i].memory_archive
                                if x.id == m.id).to_dict()
            for i, agent in enumerate(engine.agents[:2])
            for m in agent.memory_archive if m.causal
        )

        authority_before = (engine.materials.to_dict(), engine.commitment_system.to_dict())
        owner.remember(Memory(
            day=40, hour=1, type="fabricated", description="A transfer happened.",
            participants=[owner.name], location="market", importance=5,
            sentiment=1, tags=[],
        ))
        owner.memory = [m for m in owner.memory if m.type != "fabricated"]
        scenarios["authority_independence"] = authority_before == (
            engine.materials.to_dict(), engine.commitment_system.to_dict()
        )

        weights_before = engine.conversation_selector.get_listener_weights(
            engine.agents[1], [engine.agents[0], engine.agents[2]]
        )
        scenarios["future_choice_pressure"] = (
            weights_before[0] != weights_before[1]
            and abs(weights_before[0] - weights_before[1]) <= 5
        )

        invariants = engine.outcome_memory.validate()
        invariants.update({
            "archive_bounded": all(len(a.memory_archive) <= 500 for a in engine.agents),
            "active_memory_bounded": all(len(a.memory) <= 200 for a in engine.agents),
            "historical_retrieval_bounded": len(context["relevant_memories"]) <= 3,
            "prompt_memory_budget_bounded": _prompt_context_text_chars(context) <= MAX_CONTEXT_TEXT_CHARS,
            "private_plan_state": scenarios["private_plan_failure"],
            "victim_discovery_no_culprit": scenarios["unwitnessed_loss"],
            "memory_not_authority": scenarios["authority_independence"],
            "social_effect_not_double_applied": commitment.consequence_applied,
        })
    failed_scenarios = sorted(name for name, passed in scenarios.items() if not passed)
    failed_invariants = sorted(name for name, passed in invariants.items() if not passed)
    return {
        "passed": not failed_scenarios and not failed_invariants,
        "scenario_count": len(scenarios),
        "scenarios_passed": len(scenarios) - len(failed_scenarios),
        "invariant_count": len(invariants),
        "invariants_passed": len(invariants) - len(failed_invariants),
        "scenarios": scenarios,
        "invariants": invariants,
        "diagnostics": {
            "failed_scenarios": failed_scenarios,
            "failed_invariants": failed_invariants,
        },
    }
