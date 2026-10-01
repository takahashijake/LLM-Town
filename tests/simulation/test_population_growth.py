from pathlib import Path

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def engine(tmp_path: Path, *, load=False):
    return SimulationEngine(
        "data/agents.json", "data/locations.json", load_state=load,
        llm_client=FakeLLMClient(), state_path=tmp_path / "save.json",
        logs_dir=tmp_path / ("reload-logs" if load else "logs"),
    )


def make_eligible(subject):
    for day in range(8, 15):
        for agent in subject.agents:
            subject.activity_records.append({
                "type": "activity", "day": day, "hour": 8,
                "agent_id": agent.id, "agent": agent.name,
            })


def test_activation_registers_every_authority_and_is_replay_safe(tmp_path):
    subject = engine(tmp_path)
    make_eligible(subject)
    source_before = subject.economy.get_account(
        "account:employer:town_services"
    ).balance
    material_before = subject.materials.total_quantities()
    employments_before = set(subject.economy.employments)

    review = subject.review_town_growth(14)
    subject.review_town_growth(14)
    newcomer = next(item for item in subject.agents if item.id == "agent_005")

    assert review.status == "activated"
    assert newcomer.name == "Nora"
    assert newcomer.occupation == "unemployed"
    assert subject.economy.account_for_agent(newcomer.id).balance == 75
    assert subject.economy.get_account(
        "account:employer:town_services"
    ).balance == source_before - 75
    assert subject.materials.inventory_for_agent(newcomer.id).quantities == ()
    assert subject.materials.total_quantities() == material_before
    assert set(subject.economy.employments) == employments_before
    assert newcomer.id in subject.crime.agents
    assert newcomer.id in subject.justice.agents
    assert newcomer.id not in subject.crime.theft_activity_rules[
        "attempt_theft"
    ].eligible_actor_ids
    assert newcomer.id not in subject.justice.investigator_agent_ids
    assert any(item.id == newcomer.id for item in subject.plan_system.agents)
    assert any(item.id == newcomer.id for item in subject.commitment_system.agents)
    assert len(subject.town_growth.migration_records) == 1
    assert len([
        item for item in subject.economy.ledger
        if item.transaction_type == "migration_settlement"
    ]) == 1
    assert all(subject.outcome_memory.validate().values())


def test_save_before_and_after_activation_are_safe(tmp_path):
    subject = engine(tmp_path)
    make_eligible(subject)
    review = subject.town_growth.review(
        day=14, agents=subject.agents, locations=subject.locations,
        activity_records=subject.activity_records, economy=subject.economy,
    )
    assert review.status == "proposed"
    subject.state.save(subject, 14, 8)

    resumed = engine(tmp_path, load=True)
    resumed.review_town_growth(14)
    resumed.state.save(resumed, 14, 8, day_complete=True)
    reloaded = engine(tmp_path, load=True)
    reloaded.review_town_growth(14)

    assert [item.id for item in reloaded.agents].count("agent_005") == 1
    assert reloaded.economy.account_for_agent("agent_005").balance == 75
    assert len(reloaded.town_growth.migration_records) == 1
    assert len([
        item for item in reloaded.economy.ledger
        if item.transaction_type == "migration_settlement"
    ]) == 1
    arrival_ids = [
        memory.id for agent in reloaded.agents
        for memory in agent.memory + agent.memory_archive
        if memory.event_type == "resident_arrival"
    ]
    assert len(arrival_ids) == len(reloaded.agents)
    assert len(arrival_ids) == len(set(arrival_ids))


def test_old_save_without_growth_state_loads_without_fabricating_history(tmp_path):
    subject = engine(tmp_path)
    subject.state.save(subject, 3, 8)
    import json
    state = json.loads((tmp_path / "save.json").read_text())
    state.pop("town_growth")
    (tmp_path / "save.json").write_text(json.dumps(state))

    resumed = engine(tmp_path, load=True)
    assert resumed.town_growth.migration_records == []
    assert resumed.town_growth.next_resident_sequence == 5
