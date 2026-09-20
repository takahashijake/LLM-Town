"""Whole-V2 deterministic acceptance and freeze-readiness evaluation."""

from __future__ import annotations

import json
import random
from pathlib import Path

from src.behavior.activity import Activity
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.crime import CrimeError, CrimeSystem
from src.systems.justice import JusticeError
from src.systems.materials import MaterialError


MARKET = "inventory:business:market_stall"
VICTIM = "agent_001"
ACTOR = "agent_002"
WITNESS = "agent_003"
MERCHANT = "agent_004"


class ControlledWorkPlanner:
    """Select configured work through the normal ActivitySystem route."""

    _activities = {
        "agent_001": Activity("investigate_story", "Investigate", "town_square", "controlled V2 work", ["work", "journalism"]),
        "agent_002": Activity("review_records", "Review records", "library", "controlled V2 work", ["work", "accounting"]),
        "agent_003": Activity("organize_community", "Organize", "town_square", "controlled V2 work", ["work", "community"]),
        "agent_004": Activity("restock_market", "Restock", "market", "controlled V2 production", ["work", "production", "business"]),
    }

    def choose_activity(self, *, agent, **_kwargs):
        return self._activities[agent.id]


def _build(root: Path, work: Path, load=False):
    return SimulationEngine(
        root / "data/agents.json", root / "data/locations.json",
        economy_path=root / "data/economy.json", materials_path=root / "data/materials.json",
        crime_path=root / "data/crime.json", justice_path=root / "data/justice.json",
        load_state=load, llm_client=FakeLLMClient(), state_path=work / "state.json",
        logs_dir=work / ("resumed_logs" if load else "logs"),
    )


def _agent(engine, agent_id):
    return next(item for item in engine.agents if item.id == agent_id)


def _witness_key(label: str, **expected):
    for number in range(10000):
        key = f"v2:{label}:{number}"
        if all(CrimeSystem.witness_observes(key, agent_id) is value
               for agent_id, value in expected.items()):
            return key
    raise RuntimeError("unable to construct deterministic witness event")


def _reputation_state(engine):
    return {
        agent.id: {
            target: {dimension: belief.to_dict() for dimension, belief in dimensions.items()}
            for target, dimensions in agent.reputation_beliefs.items()
        }
        for agent in engine.agents
    }


def _authoritative_state(engine):
    return {
        "economy": engine.economy.to_dict(),
        "materials": engine.materials.to_dict(),
        "crime": engine.crime.to_dict(),
        "justice": engine.justice.to_dict(),
        "reputation": _reputation_state(engine),
    }


def _effect_state(engine):
    """Exclude rejection diagnostics while detecting every authoritative effect."""
    economy = engine.economy.to_dict()
    materials = engine.materials.to_dict()
    crime = engine.crime.to_dict()
    justice = engine.justice.to_dict()
    economy.pop("rejected_transactions", None)
    materials.pop("rejected_operations", None)
    crime.pop("rejected_attempts", None)
    justice.pop("rejected_attempts", None)
    return {"economy": economy, "materials": materials, "crime": crime,
            "justice": justice, "reputation": _reputation_state(engine)}


def _save_reload(root, work, engine, day, hour):
    engine.state.save(engine, day, hour)
    return _build(root, work, True)


def _deplete_market(engine):
    for agent in engine.agents:
        inventory = engine.materials.inventory_for_agent(agent.id)
        account = engine.economy.account_for_agent(agent.id)
        for index in range(6):
            engine.materials.purchase(
                inventory.id, account.id, "seller:market_stall", "prepared_meal", 1,
                day=1, hour=7, event_key=f"v2:deplete:{agent.id}:{index}",
            )
    # Make the positive victim's later purchase unambiguously use the produced lot.
    victim = _agent(engine, VICTIM)
    engine.materials.consume(
        victim, engine.materials.inventory_for_agent(VICTIM).id, "prepared_meal", 6,
        day=1, hour=8, activity_id="eat_meal", event_key="v2:clear:victim",
    )


def _run_positive(root: Path, work: Path, interrupted: bool):
    engine = _build(root, work)
    _deplete_market(engine)
    merchant = _agent(engine, MERCHANT)
    merchant_need_before = merchant.needs["wealth"]
    engine.activity_system.activity_planner = ControlledWorkPlanner()
    engine.activity_system.run_agent_activities(
        engine.agents, ["market", "library", "town_square"], 2, 8, None, {},
    )
    production = engine.materials.production_records[-1]
    wage = next(
        item for item in engine.economy.ledger
        if item.transaction_type == "wage" and dict(item.metadata).get("agent_id") == MERCHANT
    )
    if interrupted:
        engine = _save_reload(root, work, engine, 2, 8)

    victim = _agent(engine, VICTIM)
    victim_inventory = engine.materials.inventory_for_agent(VICTIM)
    exchange = engine.materials.purchase(
        victim_inventory.id, engine.economy.account_for_agent(VICTIM).id,
        "seller:market_stall", "prepared_meal", 1, day=2, hour=9,
        event_key="v2:positive:purchase",
    )
    for agent in engine.agents:
        agent.location_id = "market" if agent.id in {VICTIM, ACTOR, WITNESS, MERCHANT} else "library"
    theft_key = _witness_key(
        "positive-theft", agent_001=False, agent_003=True, agent_004=False
    )
    incident = engine.crime.attempt_theft(
        actor_id=ACTOR, source_inventory_id=victim_inventory.id,
        good_id="prepared_meal", quantity=1, day=2, hour=10,
        location_id="market", event_key=theft_key, agents=engine.agents,
    )
    direct = next(
        item for item in engine.crime.evidence
        if item.incident_id == incident.id and item.evidence_type == "eyewitness"
        and item.holder_agent_id == WITNESS
    )
    case = engine.justice.open_case(
        incident_id=incident.id, opened_by_agent_id=WITNESS,
        investigator_agent_id=VICTIM, trigger_evidence_id=direct.id,
        day=2, hour=11, event_key="v2:positive:case",
    )
    private_before_review = not engine.justice.knowledge_for_agent(ACTOR)["cases"]
    if interrupted:
        engine = _save_reload(root, work, engine, 2, 11)

    decision = engine.justice.adjudicate(
        case_id=case.id, reviewer_agent_id=VICTIM, day=2, hour=12,
        event_key="v2:positive:adjudication",
    )
    observer = _agent(engine, VICTIM)
    listener = _agent(engine, ACTOR)
    before_context = engine.conversation_context_preparer.prepare_conversation_context(
        "market", observer, listener, 2, None, {}, [],
    )
    currency_before_consequence = engine.economy.to_dict()
    consequence = engine.justice.apply_consequence(
        adjudication_id=decision.id, day=2, hour=13,
        event_key="v2:positive:consequence",
    )
    after_context = engine.conversation_context_preparer.prepare_conversation_context(
        "market", observer, listener, 2, None, {}, [],
    )
    restitution = next(item for item in engine.justice.restitutions
                       if item.adjudication_id == decision.id)
    restitution_transfer = next(item for item in engine.materials.inventory_transfers
                                if item.id == restitution.material_transfer_id)
    ids = {
        "work_activity_id": production.activity_id, "wage_transaction_id": wage.id,
        "production_id": production.id, "production_lot_ids": list(production.output_lot_ids),
        "exchange_id": exchange.id, "purchase_transfer_id": exchange.inventory_transfer_id,
        "crime_incident_id": incident.id, "theft_transfer_id": incident.unauthorized_transfer_id,
        "direct_evidence_id": direct.id, "case_id": case.id,
        "adjudication_id": decision.id, "restitution_id": restitution.id,
        "restitution_transfer_id": restitution.material_transfer_id,
        "consequence_id": consequence.id,
    }
    facts = {
        "merchant_need_before": merchant_need_before,
        "merchant_need_after": _agent(engine, MERCHANT).needs["wealth"],
        "target_stock_after_batch": engine.materials.quantity(MARKET, "prepared_meal"),
        "private_before_review": private_before_review,
        "decision_result": decision.result,
        "direct_evidence_ids": list(decision.actor_identifying_evidence_ids),
        "theft_lots": list(engine.materials.lot_ids_moved_by_transfer(incident.unauthorized_transfer_id)),
        "restitution_lots": list(engine.materials.lot_ids_moved_by_transfer(restitution_transfer.id)),
        "restitution_status": restitution.status,
        "currency_unchanged_by_justice": engine.economy.to_dict() == currency_before_consequence,
        "reputation_context_before": before_context["context"]["reputation_context"],
        "reputation_context_after": after_context["context"]["reputation_context"],
        "reputation_weights_before": before_context["reputation_adjusted_weights"],
        "reputation_weights_after": after_context["reputation_adjusted_weights"],
        "reputation_deltas_after": after_context["reputation_weight_adjustments"],
    }
    return engine, ids, facts


def _run_negative(root: Path, work: Path):
    engine = _build(root, work)
    positions = {VICTIM: "library", ACTOR: "market", WITNESS: "library", MERCHANT: "market"}
    for agent in engine.agents:
        agent.location_id = positions[agent.id]
    theft_key = _witness_key("hidden-theft", agent_004=False)
    incident = engine.crime.attempt_theft(
        actor_id=ACTOR, source_inventory_id="inventory:agent:agent_004",
        good_id="trade_materials", quantity=1, day=3, hour=8,
        location_id="market", event_key=theft_key, agents=engine.agents,
    )
    loss = engine.crime.discover_loss(
        incident_id=incident.id, victim_id=MERCHANT, day=3, hour=9,
        event_key="v2:hidden:discovery",
    )
    actor_knowledge = next(item for item in engine.crime.evidence
                           if item.incident_id == incident.id and item.evidence_type == "actor_knowledge")
    hearsay = engine.crime.share_evidence(
        speaker_id=ACTOR, listener_id=VICTIM, evidence_id=actor_knowledge.id,
        day=3, hour=10, event_key="v2:hidden:hearsay",
    )
    case = engine.justice.open_case(
        incident_id=incident.id, opened_by_agent_id=MERCHANT,
        investigator_agent_id=VICTIM, trigger_evidence_id=loss.id,
        day=3, hour=11, event_key="v2:hidden:case",
    )
    engine.justice.submit_evidence(
        case_id=case.id, submitter_agent_id=VICTIM, evidence_id=hearsay.id,
        day=3, hour=12, event_key="v2:hidden:submit-hearsay",
    )
    uninvolved_private = (
        not engine.crime.knowledge_for_agent(WITNESS)
        and not engine.justice.knowledge_for_agent(WITNESS)["cases"]
    )
    context = engine.conversation_context_preparer.prepare_conversation_context(
        "library", _agent(engine, WITNESS), _agent(engine, VICTIM), 3, None, {}, [],
    )["context"]
    serialized_context = json.dumps(context, sort_keys=True)
    decision = engine.justice.adjudicate(
        case_id=case.id, reviewer_agent_id=VICTIM, day=3, hour=13,
        event_key="v2:hidden:adjudication",
    )
    return engine, {
        "ground_truth_actor_id": incident.actor_id,
        "loss_claims_actor": loss.claims_actor,
        "hearsay_provenance": hearsay.provenance_type,
        "hearsay_source_evidence_id": hearsay.source_evidence_id,
        "direct_actor_evidence_count": sum(
            item.evidence_type == "eyewitness" for item in engine.crime.evidence
        ),
        "uninvolved_private_before_public_review": uninvolved_private,
        "authoritative_state_absent_from_llm_context": all(
            marker not in serialized_context
            for marker in (incident.id, incident.unauthorized_transfer_id,
                           actor_knowledge.id, case.id, "lot_holdings", "balances")
        ),
        "result": decision.result,
        "responsible_actor_id": decision.responsible_actor_id,
        "restitution_count": len(engine.justice.restitutions),
        "consequence_count": len(engine.justice.consequences),
    }


def _run_unavailable_lot(root: Path, work: Path):
    engine, ids, _facts = _run_positive(root, work, interrupted=False)
    # The positive flow already returned its lot; create a second witnessed theft
    # of that produced lot, consume it, and give the actor unrelated initial stock.
    victim_inventory = engine.materials.inventory_for_agent(VICTIM)
    actor_inventory = engine.materials.inventory_for_agent(ACTOR)
    engine.materials.transfer_good(
        victim_inventory.id, actor_inventory.id, "prepared_meal", 1,
        day=4, hour=7, reason="Set up second theft victim holding",
        authorization_type="authorized_transfer", authorization_id="v2:second-setup",
        event_key="v2:second-setup", preferred_lot_ids=tuple(ids["production_lot_ids"]),
    )
    # Return it so the theft API records the authoritative unauthorized movement.
    engine.materials.transfer_good(
        actor_inventory.id, victim_inventory.id, "prepared_meal", 1,
        day=4, hour=8, reason="Restore before second theft",
        authorization_type="authorized_transfer", authorization_id="v2:second-restore",
        event_key="v2:second-restore", preferred_lot_ids=tuple(ids["production_lot_ids"]),
    )
    for agent in engine.agents:
        agent.location_id = "market"
    key = _witness_key("consumed-lot", agent_003=True)
    incident = engine.crime.attempt_theft(
        actor_id=ACTOR, source_inventory_id=victim_inventory.id,
        good_id="prepared_meal", quantity=1, day=4, hour=9,
        location_id="market", event_key=key, agents=engine.agents,
    )
    direct = next(item for item in engine.crime.evidence
                  if item.incident_id == incident.id and item.evidence_type == "eyewitness"
                  and item.holder_agent_id == WITNESS)
    case = engine.justice.open_case(
        incident_id=incident.id, opened_by_agent_id=WITNESS,
        investigator_agent_id=VICTIM, trigger_evidence_id=direct.id,
        day=4, hour=10, event_key="v2:consumed:case",
    )
    # Remove the actor's older initial meals, then consume the stolen production lot.
    actor = _agent(engine, ACTOR)
    initial_quantity = engine.materials.quantity(actor_inventory.id, "prepared_meal") - 1
    if initial_quantity:
        engine.materials.consume(actor, actor_inventory.id, "prepared_meal", initial_quantity,
                                 day=4, hour=11, activity_id="eat_meal",
                                 event_key="v2:consume:actor-initial")
    engine.materials.consume(actor, actor_inventory.id, "prepared_meal", 1,
                             day=4, hour=12, activity_id="eat_meal",
                             event_key="v2:consume:stolen-lot")
    # Give unrelated initial-batch stock after the stolen production lot is gone.
    donor = engine.materials.inventory_for_agent(WITNESS)
    engine.materials.transfer_good(
        donor.id, actor_inventory.id, "prepared_meal", 1,
        day=4, hour=13, reason="Unrelated fungible replacement",
        authorization_type="authorized_transfer", authorization_id="v2:unrelated-replacement",
        event_key="v2:unrelated-replacement",
    )
    decision = engine.justice.adjudicate(
        case_id=case.id, reviewer_agent_id=VICTIM, day=4, hour=14,
        event_key="v2:consumed:adjudication",
    )
    engine.justice.apply_consequence(
        adjudication_id=decision.id, day=4, hour=15,
        event_key="v2:consumed:consequence",
    )
    restitution = next(item for item in engine.justice.restitutions
                       if item.adjudication_id == decision.id)
    return engine, {
        "stolen_lot_ids": list(engine.materials.lot_ids_moved_by_transfer(incident.unauthorized_transfer_id)),
        "actor_total_fungible_quantity": engine.materials.quantity(actor_inventory.id, "prepared_meal"),
        "status": restitution.status,
        "returned_quantity": restitution.returned_quantity,
        "transfer_id": restitution.material_transfer_id,
    }


def _replay_attacks(engine, ids):
    before = _effect_state(engine)
    codes = {}
    merchant = _agent(engine, MERCHANT)
    activity = ControlledWorkPlanner._activities[MERCHANT]
    engine.economy.process_activity(merchant, activity, day=2, hour=8)
    codes["wage"] = engine.economy.rejected_transactions[-1]["code"]
    operations = {
        "production": lambda: engine.materials.produce(
            "recipe:market_prepared_meals", actor_id=MERCHANT,
            employment_id="employment:agent_004:merchant", inventory_id=MARKET,
            day=2, hour=8, activity_id="restock_market", location_id="market",
            event_key="production:recipe:market_prepared_meals:agent_004:2:8"),
        "purchase": lambda: engine.materials.purchase(
            engine.materials.inventory_for_agent(VICTIM).id,
            engine.economy.account_for_agent(VICTIM).id, "seller:market_stall",
            "prepared_meal", 1, day=2, hour=9, event_key="v2:positive:purchase"),
        "theft": lambda: engine.crime.attempt_theft(
            actor_id=ACTOR, source_inventory_id=engine.materials.inventory_for_agent(VICTIM).id,
            good_id="prepared_meal", quantity=1, day=2, hour=10, location_id="market",
            event_key=next(item.event_key for item in engine.crime.incidents if item.id == ids["crime_incident_id"]),
            agents=engine.agents),
        "case": lambda: engine.justice.open_case(
            incident_id=ids["crime_incident_id"], opened_by_agent_id=WITNESS,
            investigator_agent_id=VICTIM, trigger_evidence_id=ids["direct_evidence_id"],
            day=2, hour=11, event_key="v2:positive:case"),
        "adjudication": lambda: engine.justice.adjudicate(
            case_id=ids["case_id"], reviewer_agent_id=VICTIM, day=2, hour=12,
            event_key="v2:positive:adjudication"),
        "consequence": lambda: engine.justice.apply_consequence(
            adjudication_id=ids["adjudication_id"], day=2, hour=13,
            event_key="v2:positive:consequence"),
    }
    for name, operation in operations.items():
        try:
            operation()
        except (MaterialError, CrimeError, JusticeError) as error:
            codes[name] = error.code
    return codes, before == _effect_state(engine)


def _integrity(engine):
    material = engine.materials.diagnostics()
    return {
        "balances_nonnegative": all(item.balance >= 0 for item in engine.economy.accounts.values()),
        "currency_conserved": engine.economy.conservation_holds(),
        "ledger_reconstructs": engine.economy.ledger_reconstructs_balances(),
        "inventories_nonnegative": material["no_negative_inventory"],
        "material_accounting": material["material_conserved_with_consumption"],
        "inventory_history": material["history_reconstructs_inventories"],
        "exchange_reconciliation": material["exchanges_reconcile_with_ledger"],
        "production_records": material["production_records_valid"],
        "lot_holdings": material["provenance_reconciles"],
        "lot_history": material["provenance_history_reconstructs"],
        "lot_event_reconciliation": material["lot_movements_reconcile_with_events"],
        "crime_material_reconciliation": engine.crime.incidents_reconcile_with_materials(),
        "evidence_provenance": engine.crime.evidence_is_valid(),
        "justice_history": engine.justice.history_is_valid(),
    }


def _long_horizon(root: Path, work: Path):
    engine = _build(root, work)
    daily = []
    resume_exact = True
    for day in range(1, 31):
        random.seed(10_000 + day)
        engine.activity_system.run_agent_activities(
            engine.agents, [location.id for location in engine.locations],
            day, 8, None, engine.agent_intents,
        )
        checks = _integrity(engine)
        daily.append(all(checks.values()))
        if day == 15:
            expected = _authoritative_state(engine)
            engine = _save_reload(root, work, engine, day, 8)
            resume_exact = resume_exact and expected == _authoritative_state(engine)
    return engine, {"days": 30, "daily_checks_passed": all(daily),
                    "save_resume_exact": resume_exact, "final": _integrity(engine)}


def run_v2_evaluation(work_dir: str | Path, *, project_root: str | Path = ".") -> dict:
    caller_random_state = random.getstate()
    root, work = Path(project_root).resolve(), Path(work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    continuous, ids, facts = _run_positive(root, work / "continuous", False)
    resumed, resumed_ids, resumed_facts = _run_positive(root, work / "resumed", True)
    equivalent = _authoritative_state(continuous) == _authoritative_state(resumed)
    replay_codes, replay_safe = _replay_attacks(resumed, resumed_ids)
    negative, negative_facts = _run_negative(root, work / "negative")
    unavailable, unavailable_facts = _run_unavailable_lot(root, work / "unavailable")
    long_engine, long_facts = _long_horizon(root, work / "long_horizon")
    positive_integrity = _integrity(continuous)
    negative_integrity = _integrity(negative)
    unavailable_integrity = _integrity(unavailable)

    hard = {
        "positive_causal_chain_complete": all(ids.values()) and facts["decision_result"] == "responsible",
        "planned_work_paid_wage_and_produced": facts["merchant_need_after"] > facts["merchant_need_before"] and bool(continuous.materials.production_records),
        "target_threshold_batch_semantics": facts["target_stock_after_batch"] == 3,
        "purchase_links_money_and_material": continuous.materials.exchanges_reconcile_with_ledger(),
        "theft_is_unauthorized_not_exchange": ids["theft_transfer_id"] not in {item.inventory_transfer_id for item in continuous.materials.exchanges},
        "direct_evidence_supports_responsibility": facts["direct_evidence_ids"] == [ids["direct_evidence_id"]],
        "private_case_did_not_leak": facts["private_before_review"],
        "exact_lot_restitution": facts["theft_lots"] == facts["restitution_lots"] == ids["production_lot_ids"],
        "justice_preserved_currency": facts["currency_unchanged_by_justice"],
        "unavailable_stolen_lot_not_replaced": unavailable_facts["actor_total_fungible_quantity"] > 0 and unavailable_facts["status"] == "unresolved" and unavailable_facts["returned_quantity"] == 0,
        "negative_ground_truth_remained_private": negative_facts["ground_truth_actor_id"] == ACTOR and negative_facts["uninvolved_private_before_public_review"],
        "llm_context_respects_authority_boundary": negative_facts["authoritative_state_absent_from_llm_context"],
        "loss_discovery_did_not_identify_actor": not negative_facts["loss_claims_actor"],
        "hearsay_remained_hearsay": negative_facts["hearsay_provenance"] == "hearsay" and negative_facts["direct_actor_evidence_count"] == 0,
        "insufficient_evidence_no_consequence": negative_facts["result"] == "insufficient_evidence" and negative_facts["responsible_actor_id"] is None and negative_facts["restitution_count"] == negative_facts["consequence_count"] == 0,
        "continuous_resumed_equivalent": equivalent and ids == resumed_ids and facts == resumed_facts,
        "replay_attacks_rejected": replay_safe and all(code == "duplicate_event" for code in replay_codes.values()),
        "positive_integrity": all(positive_integrity.values()),
        "negative_integrity": all(negative_integrity.values()),
        "unavailable_lot_integrity": all(unavailable_integrity.values()),
        "thirty_day_integrity": long_facts["daily_checks_passed"] and long_facts["save_resume_exact"] and all(long_facts["final"].values()),
        "public_reputation_reaches_context": not facts["reputation_context_before"] and bool(facts["reputation_context_after"]),
    }
    result = {
        "passed": all(hard.values()), "hard_invariants": hard,
        "causal_event_ids": ids, "positive": facts,
        "negative_information_boundary": negative_facts,
        "unavailable_lot_restitution": unavailable_facts,
        "persistence": {"continuous_resumed_equivalent": equivalent},
        "replay": {"codes": replay_codes, "effects_unchanged": replay_safe},
        "long_horizon": long_facts,
        "reputation_downstream": {
            "context_changed": facts["reputation_context_before"] != facts["reputation_context_after"],
            "action_weights_changed": facts["reputation_weights_before"] != facts["reputation_weights_after"],
            "finding": "Public justice changes private dialogue context; this bounded consequence does not cross the current action-weight threshold or alter activity/target selection.",
        },
        "integrity": {"positive": positive_integrity, "negative": negative_integrity,
                      "unavailable": unavailable_integrity},
    }
    random.setstate(caller_random_state)
    return result


def write_v2_evaluation(result: dict, path: str | Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
