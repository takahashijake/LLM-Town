import pytest

from src.agents.agent import Agent
from src.behavior.activity import Activity
from src.systems.economy import (
    EconomicAccount,
    EconomyError,
    EconomySystem,
    Employment,
)


def build_economy(source_balance=100, destination_balance=10):
    return EconomySystem(
        accounts=[
            EconomicAccount("employer", "employer", "town", source_balance),
            EconomicAccount("worker", "agent", "agent_1", destination_balance),
        ],
        employments=[
            Employment(
                id="job_1",
                agent_id="agent_1",
                title="tester",
                employer_account_id="employer",
                wage=20,
                qualifying_activity_ids=("do_work",),
            )
        ],
        wealth_need_gain=4,
    )


def build_agent():
    return Agent(
        id="agent_1",
        name="Worker",
        personality="careful",
        location_id="library",
        occupation="tester",
        needs={"social": 50, "wealth": 50, "knowledge": 50},
    )


def test_initialization_is_deterministic_and_account_ids_are_unique():
    first = EconomySystem.from_config("data/economy.json", [build_agent()])
    second = EconomySystem.from_config("data/economy.json", [build_agent()])
    assert first.to_dict() == second.to_dict()
    assert len(first.accounts) == len(set(first.accounts))

    with pytest.raises(ValueError, match="unique"):
        EconomySystem(
            accounts=[
                EconomicAccount("same", "system", "a", 1),
                EconomicAccount("same", "system", "b", 1),
            ],
            employments=[],
        )


def test_successful_transfer_is_atomic_audited_and_conserved():
    economy = build_economy()
    transaction = economy.transfer(
        "employer",
        "worker",
        25,
        day=2,
        hour=8,
        transaction_type="transfer",
        reason="approved test transfer",
        event_key="transfer:one",
    )
    assert transaction.id == "txn-00000001"
    assert economy.get_account("employer").balance == 75
    assert economy.get_account("worker").balance == 35
    assert economy.ledger == [transaction]
    assert economy.conservation_holds()
    assert economy.ledger_reconstructs_balances()


@pytest.mark.parametrize(
    ("source", "destination", "amount", "code"),
    [
        ("employer", "worker", 101, "insufficient_funds"),
        ("employer", "worker", 0, "invalid_amount"),
        ("employer", "worker", -1, "invalid_amount"),
        ("employer", "worker", 1.5, "invalid_amount"),
        ("employer", "worker", True, "invalid_amount"),
        ("missing", "worker", 1, "unknown_source"),
        ("employer", "missing", 1, "unknown_destination"),
        ("employer", "employer", 1, "same_account"),
    ],
)
def test_rejected_transfer_never_changes_balances_or_ledger(
    source, destination, amount, code
):
    economy = build_economy()
    before = {key: value.balance for key, value in economy.accounts.items()}
    with pytest.raises(EconomyError) as error:
        economy.transfer(
            source,
            destination,
            amount,
            day=1,
            hour=8,
            transaction_type="transfer",
            reason="invalid test",
        )
    assert error.value.code == code
    assert {key: value.balance for key, value in economy.accounts.items()} == before
    assert economy.ledger == []
    assert economy.rejected_transactions[-1]["code"] == code


def test_valid_work_pays_once_and_updates_wealth_boundedly():
    economy = build_economy()
    agent = build_agent()
    work = Activity(
        id="do_work",
        name="Do assigned work",
        location_id="library",
        reason="Scheduled shift",
        tags=["work"],
    )
    transaction = economy.process_activity(agent, work, day=1, hour=8)
    assert transaction is not None
    assert transaction.transaction_type == "wage"
    assert economy.get_account("worker").balance == 30
    assert economy.get_account("employer").balance == 80
    assert agent.needs["wealth"] == 54
    assert economy.work_events[0]["payment_status"] == "paid"

    assert economy.process_activity(agent, work, day=1, hour=12) is None
    assert economy.get_account("worker").balance == 30
    assert agent.needs["wealth"] == 54
    assert len(economy.ledger) == 1
    assert economy.rejected_transactions[-1]["code"] == "duplicate_event"


def test_non_work_and_wrong_job_activity_do_not_pay_or_change_wealth():
    economy = build_economy()
    agent = build_agent()
    activities = [
        Activity("do_work", "Work-shaped leisure", "library", "No tag", []),
        Activity("other", "Other work", "library", "Wrong assignment", ["work"]),
    ]
    for activity in activities:
        assert economy.process_activity(agent, activity, day=1, hour=8) is None
    assert economy.ledger == []
    assert agent.needs["wealth"] == 50


def test_wealth_need_gain_is_capped_by_existing_need_model():
    economy = build_economy()
    agent = build_agent()
    agent.needs["wealth"] = 99
    work = Activity("do_work", "Work", "library", "Shift", ["work"])
    economy.process_activity(agent, work, day=1, hour=8)
    assert agent.needs["wealth"] == 100


def test_unfunded_wage_is_rejected_without_wealth_effect():
    economy = build_economy(source_balance=10)
    agent = build_agent()
    work = Activity("do_work", "Work", "library", "Shift", ["work"])
    assert economy.process_activity(agent, work, day=1, hour=8) is None
    assert economy.ledger == []
    assert economy.get_account("employer").balance == 10
    assert economy.get_account("worker").balance == 10
    assert agent.needs["wealth"] == 50
    assert economy.work_events[0]["payment_status"] == "rejected:insufficient_funds"


def test_round_trip_preserves_all_economic_continuity_and_guards():
    economy = build_economy()
    agent = build_agent()
    work = Activity("do_work", "Work", "library", "Shift", ["work"])
    economy.process_activity(agent, work, day=3, hour=8)
    restored = EconomySystem.from_dict(economy.to_dict())
    assert restored.to_dict() == economy.to_dict()
    assert restored.process_activity(agent, work, day=3, hour=12) is None
    assert len(restored.ledger) == 1
    diagnostics = restored.diagnostics()
    assert diagnostics["currency_conserved"] is True
    assert diagnostics["ledger_reconstructs_balances"] is True
    assert diagnostics["all_wages_have_work_events"] is True
    assert diagnostics["duplicate_wage_event_keys"] is False
