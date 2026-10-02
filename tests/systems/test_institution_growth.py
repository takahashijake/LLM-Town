"""Focused authority tests for bounded institution formation."""

from types import SimpleNamespace

import pytest

from src.systems.economy import EconomySystem, Employment
from src.systems.event_ecology import (
    DynamicEventOccurrenceRecord,
    EventEcologySystem,
)
from src.systems.institution_growth import InstitutionGrowthSystem
from src.systems.location_growth import LocationGrowthSystem
from src.town.location import Location


def _fixture():
    agents = [SimpleNamespace(id=f"agent_{index:03d}", name=f"Agent {index}")
              for index in range(1, 6)]
    base = [
        Location("town_square", "Town Square", "Square", ["social", "community"]),
        Location("cafe", "Cafe", "Cafe", ["social"]),
        Location("library", "Library", "Library", ["knowledge"]),
        Location("market", "Market", "Market", []),
    ]
    location_growth = LocationGrowthSystem.from_config("data/town_growth.json", base)
    broad = [{"type": "activity", "day": day, "agent_id": agent.id,
              "location": "town_square"}
             for day in range(22, 29) for agent in agents]
    proposal = location_growth.review(
        day=28, agents=agents, locations=base, activity_records=broad,
    )
    location_growth.activate(proposal.activation_id, day=28)
    garden = location_growth.activated_locations()[0]
    recent = [{"type": "activity", "day": day, "hour": 8,
               "agent_id": agent.id, "location": garden.id,
               "activity_id": "explore_dynamic_place"}
              for day in range(49, 71) for agent in agents[2:]]
    templates = EventEcologySystem.from_config("data/town_growth.json").templates
    occurrences = [
        DynamicEventOccurrenceRecord(
            f"daily-event:{day}:garden_learning_circle:community_garden",
            "garden_learning_circle", "community_garden", day,
        ) for day in (40, 56)
    ]
    ecology = EventEcologySystem(
        EventEcologySystem.from_config("data/town_growth.json").policy,
        list(templates.values()), occurrence_history=occurrences,
        processed_occurrence_ids={item.occurrence_id for item in occurrences},
    )
    economy = EconomySystem.from_config("data/economy.json", agents)
    system = InstitutionGrowthSystem.from_config("data/town_growth.json")
    return agents, base + [garden], location_growth, ecology, economy, broad + recent, system


def test_readiness_uses_exact_place_event_and_unemployment_authority():
    agents, locations, growth, ecology, economy, activity, system = _fixture()
    review = system.review(
        day=70, agents=agents, locations=locations, location_growth=growth,
        event_ecology=ecology, activity_records=activity, economy=economy,
    )
    assert review.status == "proposed"
    assert review.candidate_agent_id == "agent_005"
    assert system.pending_formation().location_id == "community_garden"
    assert system.review(
        day=70, agents=agents, locations=locations, location_growth=growth,
        event_ecology=ecology, activity_records=activity, economy=economy,
    ) is review


def test_readiness_fails_without_events_activity_or_unemployed_candidate():
    agents, locations, growth, ecology, economy, activity, _system = _fixture()
    no_events = EventEcologySystem.from_config("data/town_growth.json")
    system = InstitutionGrowthSystem.from_config("data/town_growth.json")
    assert system.review(
        day=70, agents=agents, locations=locations, location_growth=growth,
        event_ecology=no_events, activity_records=activity, economy=economy,
    ).status == "waiting"

    system = InstitutionGrowthSystem.from_config("data/town_growth.json")
    assert system.review(
        day=70, agents=agents, locations=locations, location_growth=growth,
        event_ecology=ecology, activity_records=[], economy=economy,
    ).status == "waiting"


def test_runtime_economic_registration_requires_zero_baseline_and_exact_location():
    agents, _locations, _growth, _ecology, economy, _activity, _system = _fixture()
    account = economy.register_employer_account(
        "institution:0001", "account:institution:0001"
    )
    assert account.balance == 0
    assert economy.initial_balances[account.id] == 0
    job = Employment(
        "employment:institution:0001", agents[-1].id, "garden steward",
        account.id, 18, ("steward_community_garden",), start_day=71,
        activity_locations=(("steward_community_garden", "community_garden"),),
        activity_names=(("steward_community_garden", "Steward the Garden"),),
        institution_id="institution:0001", formation_id="formation:0001",
        role_template_id="garden_steward",
    )
    assert economy.register_employment(job) is job
    assert not economy.can_register_employment(job)
    with pytest.raises(Exception):
        economy.register_employer_account(
            "institution:0001", "account:institution:another"
        )


def test_unknown_schema_and_serialized_ready_flag_fail_closed():
    system = InstitutionGrowthSystem.from_config("data/town_growth.json")
    state = system.to_dict()
    state["schema_version"] = 999
    with pytest.raises(ValueError, match="schema"):
        InstitutionGrowthSystem.from_config("data/town_growth.json", state)
    state = system.to_dict()
    state["ready"] = True
    with pytest.raises(ValueError, match="schema"):
        InstitutionGrowthSystem.from_config("data/town_growth.json", state)
