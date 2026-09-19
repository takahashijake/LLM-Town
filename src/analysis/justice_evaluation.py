"""Model-free acceptance evaluation for the deterministic justice pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.crime import CrimeSystem
from src.systems.justice import JusticeError


def _engine(root: Path, work: Path, load=False):
    return SimulationEngine(
        root / "data/agents.json", root / "data/locations.json",
        economy_path=root / "data/economy.json", materials_path=root / "data/materials.json",
        crime_path=root / "data/crime.json", justice_path=root / "data/justice.json",
        load_state=load, llm_client=FakeLLMClient(), state_path=work / "state.json",
        logs_dir=work / ("resumed_logs" if load else "logs"),
    )


def _key(label, *requirements):
    for number in range(10000):
        key = f"justice-evaluation:{label}:{number}"
        if all(CrimeSystem.witness_observes(key, agent) is expected for agent, expected in requirements):
            return key
    raise RuntimeError("could not construct deterministic witness scenario")


def _arrange(engine, include_lena):
    places = {"agent_001": "library", "agent_002": "market", "agent_003": "market" if include_lena else "library", "agent_004": "market"}
    for agent in engine.agents:
        agent.location_id = places[agent.id]


def _steal(engine, label, witnessed):
    _arrange(engine, witnessed)
    requirements = (("agent_003", True), ("agent_004", False)) if witnessed else (("agent_004", False),)
    return engine.crime.attempt_theft(
        actor_id="agent_002", source_inventory_id="inventory:agent:agent_004",
        good_id="trade_materials", quantity=1, day=2, hour=12,
        location_id="market", event_key=_key(label, *requirements), agents=engine.agents,
    )


def _snapshot(engine):
    return {
        "currency": engine.economy.total_currency(),
        "balances": {key: item.balance for key, item in engine.economy.accounts.items()},
        "quantities": {key: dict(item.quantities) for key, item in engine.materials.inventories.items()},
        "ledger": len(engine.economy.ledger), "transfers": len(engine.materials.inventory_transfers),
        "adjudications": len(engine.justice.adjudications), "restitutions": len(engine.justice.restitutions),
        "consequences": len(engine.justice.consequences),
    }


def run_justice_evaluation(work_dir: str | Path, *, project_root: str | Path = ".") -> dict:
    root, work = Path(project_root).resolve(), Path(work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)

    # 1: witnessed theft, direct evidence, responsibility, restitution, consequence.
    witnessed = _engine(root, work / "witnessed")
    incident = _steal(witnessed, "witnessed", True)
    direct = next(x for x in witnessed.crime.evidence if x.incident_id == incident.id and x.evidence_type == "eyewitness" and x.holder_agent_id == "agent_003")
    case = witnessed.justice.open_case(incident_id=incident.id, opened_by_agent_id="agent_003", investigator_agent_id="agent_001", trigger_evidence_id=direct.id, day=2, hour=13, event_key="case:witnessed")
    decision = witnessed.justice.adjudicate(case_id=case.id, reviewer_agent_id="agent_001", day=2, hour=14, event_key="decision:witnessed")
    currency_before = witnessed.economy.to_dict()
    witnessed.justice.apply_consequence(adjudication_id=decision.id, day=2, hour=15, event_key="consequence:witnessed")
    restitution = witnessed.justice.restitutions[0]

    # 2: victim discovers the loss, but no direct actor-identifying evidence exists.
    unwitnessed = _engine(root, work / "unwitnessed")
    hidden = _steal(unwitnessed, "hidden", False)
    loss = unwitnessed.crime.discover_loss(incident_id=hidden.id, victim_id="agent_004", day=2, hour=13, event_key="discover:hidden")
    hidden_case = unwitnessed.justice.open_case(incident_id=hidden.id, opened_by_agent_id="agent_004", investigator_agent_id="agent_001", trigger_evidence_id=loss.id, day=2, hour=14, event_key="case:hidden")
    hidden_private_before_review = not unwitnessed.justice.knowledge_for_agent("agent_003")["cases"]
    hidden_decision = unwitnessed.justice.adjudicate(case_id=hidden_case.id, reviewer_agent_id="agent_001", day=2, hour=15, event_key="decision:hidden")

    # 3: an admitted accusation is hearsay and must remain insufficient.
    hearsay_world = _engine(root, work / "hearsay")
    rumor_incident = _steal(hearsay_world, "hearsay", True)
    rumor_direct = next(x for x in hearsay_world.crime.evidence if x.incident_id == rumor_incident.id and x.evidence_type == "eyewitness" and x.holder_agent_id == "agent_003")
    rumor = hearsay_world.crime.share_evidence(speaker_id="agent_003", listener_id="agent_001", evidence_id=rumor_direct.id, day=2, hour=13, event_key="share:rumor")
    # Victim discovery legitimately opens the case; direct evidence is deliberately not admitted.
    rumor_loss = hearsay_world.crime.discover_loss(incident_id=rumor_incident.id, victim_id="agent_004", day=2, hour=13, event_key="discover:rumor")
    rumor_case = hearsay_world.justice.open_case(incident_id=rumor_incident.id, opened_by_agent_id="agent_004", investigator_agent_id="agent_001", trigger_evidence_id=rumor_loss.id, day=2, hour=14, event_key="case:rumor")
    hearsay_world.justice.submit_evidence(case_id=rumor_case.id, submitter_agent_id="agent_001", evidence_id=rumor.id, day=2, hour=15, event_key="submit:rumor")
    rumor_decision = hearsay_world.justice.adjudicate(case_id=rumor_case.id, reviewer_agent_id="agent_001", day=2, hour=16, event_key="decision:rumor")

    # 4: exact state round trip and duplicate calls after resume.
    expected = (witnessed.justice.to_dict(), witnessed.materials.to_dict(), witnessed.economy.to_dict())
    witnessed.state.save(witnessed, 2, 15)
    resumed = _engine(root, work / "witnessed", True)
    persistence_equal = expected == (resumed.justice.to_dict(), resumed.materials.to_dict(), resumed.economy.to_dict())
    replay_before = _snapshot(resumed)
    replay_codes = []
    for operation in (
        lambda: resumed.justice.adjudicate(case_id=case.id, reviewer_agent_id="agent_001", day=2, hour=16, event_key="decision:witnessed"),
        lambda: resumed.justice.apply_consequence(adjudication_id=decision.id, day=2, hour=16, event_key="consequence:witnessed"),
    ):
        try:
            operation()
        except JusticeError as error:
            replay_codes.append(error.code)
    replay_after = _snapshot(resumed)

    restitution_transfer = next(x for x in witnessed.materials.inventory_transfers if x.id == restitution.material_transfer_id)
    invariants = {
        "witnessed_theft_found_responsible": decision.result == "responsible",
        "responsibility_uses_direct_evidence_path": decision.actor_identifying_evidence_ids == (direct.id,) and direct.provenance_type == "direct_observation",
        "system_record_only_corroborates_theft": incident.evidence_ids[0] in decision.theft_evidence_ids and incident.evidence_ids[0] not in decision.actor_identifying_evidence_ids,
        "restitution_returned_stolen_material": restitution.status == "full" and restitution_transfer.authorization_type == "justice_restitution",
        "justice_did_not_mutate_currency": witnessed.economy.to_dict() == currency_before,
        "material_conservation_holds": all(x.materials.material_conservation_holds() for x in (witnessed, unwitnessed, hearsay_world, resumed)),
        "crime_linkage_remains_valid": all(x.crime.incidents_reconcile_with_materials() for x in (witnessed, unwitnessed, hearsay_world, resumed)),
        "unwitnessed_loss_is_insufficient": hidden_decision.result == "insufficient_evidence" and hidden_decision.responsible_actor_id is None,
        "unadjudicated_actor_not_subject_to_restitution": not unwitnessed.justice.restitutions,
        "hearsay_remains_hearsay": rumor.provenance_type == "hearsay" and rumor.source_evidence_id == rumor_direct.id,
        "hearsay_alone_is_insufficient": rumor_decision.result == "insufficient_evidence" and not rumor_decision.actor_identifying_evidence_ids,
        "private_case_did_not_leak": hidden_private_before_review,
        "save_resume_exact": persistence_equal,
        "resume_replay_blocked": replay_codes == ["duplicate_event", "duplicate_event"] and replay_before == replay_after,
        "currency_conserved_everywhere": all(x.economy.conservation_holds() for x in (witnessed, unwitnessed, hearsay_world, resumed)),
    }
    return {
        "passed": all(invariants.values()), "rule_version": witnessed.justice.rule_version,
        "invariants": invariants,
        "scenarios": {
            "witnessed": {"incident_id": incident.id, "case_id": case.id, "adjudication": decision.to_dict(), "restitution": asdict_safe(restitution)},
            "unwitnessed_discovered": {"incident_id": hidden.id, "result": hidden_decision.result},
            "hearsay_only": {"source_evidence_id": rumor.source_evidence_id, "result": rumor_decision.result},
            "save_resume_replay": {"rejection_codes": replay_codes, "state_unchanged": replay_before == replay_after},
        },
        "diagnostics": resumed.justice.diagnostics(),
    }


def asdict_safe(record):
    from dataclasses import asdict
    return asdict(record)


def write_justice_evaluation(result: dict, path: str | Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
