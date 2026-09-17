"""Deterministic acceptance evaluation for the V2 economic foundation."""

from __future__ import annotations

import json
from pathlib import Path

from src.behavior.activity import Activity
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


ACTIVITY_NAMES = {
    "investigate_story": "Investigate a possible story",
    "review_records": "Review records and numbers",
    "organize_community": "Organize community support",
    "pursue_business": "Look for business opportunities",
}


class AssignedWorkPlanner:
    def __init__(self, economy):
        self.economy = economy

    def choose_activity(self, *, agent, **_kwargs) -> Activity:
        job = self.economy.employment_for_agent(agent.id)
        activity_id = job.qualifying_activity_ids[0]
        return Activity(
            id=activity_id,
            name=ACTIVITY_NAMES.get(activity_id, job.title),
            location_id=agent.location_id,
            reason=f"Deterministic evaluation shift for {job.id}",
            tags=["work"],
        )


def run_economy_evaluation(
    work_dir: str | Path,
    *,
    project_root: str | Path = ".",
) -> dict:
    project_root = Path(project_root).resolve()
    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    state_path = work_dir / "save_state.json"
    logs_dir = work_dir / "logs"

    engine = SimulationEngine(
        agents_path=project_root / "data/agents.json",
        locations_path=project_root / "data/locations.json",
        economy_path=project_root / "data/economy.json",
        llm_client=FakeLLMClient(),
        state_path=state_path,
        logs_dir=logs_dir,
    )
    starting_wealth = {agent.id: agent.needs["wealth"] for agent in engine.agents}
    engine.activity_system.activity_planner = AssignedWorkPlanner(engine.economy)
    engine.activity_system.run_agent_activities(
        agents=engine.agents,
        location_ids=[location.id for location in engine.locations],
        day=1,
        hour=8,
        current_daily_event=None,
        agent_intents={},
    )
    wealth_after_work = {agent.id: agent.needs["wealth"] for agent in engine.agents}
    engine.state.save(engine, 1, 8, day_complete=False)
    before_resume = engine.economy.to_dict()

    resumed = SimulationEngine(
        agents_path=project_root / "data/agents.json",
        locations_path=project_root / "data/locations.json",
        economy_path=project_root / "data/economy.json",
        load_state=True,
        llm_client=FakeLLMClient(),
        state_path=state_path,
        logs_dir=work_dir / "resumed_logs",
    )
    persistence_preserved = resumed.economy.to_dict() == before_resume
    transaction_count_before_duplicate = len(resumed.economy.ledger)
    resumed_agent = resumed.agents[0]
    resumed_job = resumed.economy.employment_for_agent(resumed_agent.id)
    duplicate_activity = Activity(
        id=resumed_job.qualifying_activity_ids[0],
        name="Repeated shift",
        location_id=resumed_agent.location_id,
        reason="Duplicate guard evaluation",
        tags=["work"],
    )
    wealth_before_duplicate = resumed_agent.needs["wealth"]
    duplicate_result = resumed.economy.process_activity(
        resumed_agent,
        duplicate_activity,
        day=1,
        hour=12,
    )

    diagnostics = resumed.economy.diagnostics()
    wage_agent_ids = {
        dict(transaction.metadata)["agent_id"]
        for transaction in resumed.economy.ledger
        if transaction.transaction_type == "wage"
    }
    wealth_updates_valid = all(
        wealth_after_work[agent_id]
        == min(100, starting_wealth[agent_id] - 1 + resumed.economy.wealth_need_gain)
        for agent_id in starting_wealth
    )
    invariants = {
        "all_employed_agents_earned_wages": wage_agent_ids
        == {agent.id for agent in resumed.agents},
        "all_wages_have_eligible_work_events": diagnostics["all_wages_have_work_events"],
        "no_duplicate_wage_payments": not diagnostics["duplicate_wage_event_keys"],
        "duplicate_after_resume_blocked": (
            duplicate_result is None
            and len(resumed.economy.ledger) == transaction_count_before_duplicate
            and resumed_agent.needs["wealth"] == wealth_before_duplicate
        ),
        "no_negative_balances": diagnostics["no_negative_balances"],
        "currency_conserved": diagnostics["currency_conserved"],
        "persistence_preserved": persistence_preserved,
        "wealth_updates_followed_valid_wages": wealth_updates_valid,
        "ledger_reconstructs_balances": diagnostics["ledger_reconstructs_balances"],
    }
    return {
        "schema_version": 1,
        "kind": "llm-town-economy-evaluation",
        "passed": all(invariants.values()),
        "invariants": invariants,
        "diagnostics": diagnostics,
        "work_event_count": len(resumed.economy.work_events),
        "paid_agent_ids": sorted(wage_agent_ids),
        "starting_wealth": starting_wealth,
        "wealth_after_work": wealth_after_work,
    }


def write_economy_evaluation(document: dict, output_path: str | Path) -> None:
    Path(output_path).write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

