"""Focused authority tests for bounded dynamic daily events."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.systems.event_ecology import (
    DynamicEventOccurrenceRecord,
    DynamicEventTemplate,
    EventEcologySystem,
)
from src.systems.location_growth import LocationGrowthSystem
from src.town.daily_event import DailyEvent
from src.town.location import Location


def ecology_fixture():
    base = [
        Location("town_square", "Town Square", "Square", ["social", "community"]),
        Location("cafe", "Cafe", "Cafe", ["social"]),
        Location("library", "Library", "Library", ["knowledge"]),
        Location("market", "Market", "Market", []),
    ]
    agents = [SimpleNamespace(id=f"agent_{index}", location_id="town_square")
              for index in range(1, 6)]
    growth = LocationGrowthSystem.from_config("data/town_growth.json", base)
    broad_activity = [
        {"type": "activity", "day": day, "agent_id": agent.id,
         "location": "town_square"}
        for day in range(22, 29) for agent in agents
    ]
    review = growth.review(
        day=28, agents=agents, locations=base, activity_records=broad_activity,
    )
    assert review.status == "proposed"
    record = growth.activate(review.activation_id, day=28)
    garden = growth.activated_locations()[0]
    locations = base + [garden]
    garden_activity = [
        {"type": "activity", "day": day, "hour": 8,
         "agent_id": agent.id, "location": garden.id}
        for day in (29, 30, 31) for agent in agents[:2]
    ]
    ecology = EventEcologySystem.from_config(
        "data/town_growth.json", simulation_seed=11,
    )
    return ecology, growth, locations, broad_activity + garden_activity, record


def test_dynamic_event_requires_authoritative_place_use_and_activation():
    ecology, growth, locations, activity, _record = ecology_fixture()
    assert not ecology.eligible_dynamic_candidates(
        day=31, locations=locations, location_growth=growth,
        activity_records=activity,
    )
    candidates = ecology.eligible_dynamic_candidates(
        day=32, locations=locations, location_growth=growth,
        activity_records=activity,
    )
    assert {item[0].id for item in candidates} == {"garden_learning_circle"}
    assert not ecology.eligible_dynamic_candidates(
        day=32, locations=locations[:-1], location_growth=growth,
        activity_records=activity,
    )


def test_selection_creates_one_stable_occurrence_and_cooldown_is_bounded():
    ecology, growth, locations, activity, _record = ecology_fixture()
    event = ecology.select_daily_event(
        day=32, locations=locations, location_growth=growth,
        activity_records=activity,
    )
    assert event.source_kind == "dynamic"
    assert event.occurrence_id == (
        f"daily-event:32:{event.template_id}:community_garden"
    )
    assert len(ecology.occurrence_history) == 1
    with pytest.raises(ValueError, match="already processed"):
        ecology.select_daily_event(
            day=32, locations=locations, location_growth=growth,
            activity_records=activity,
        )
    assert len(ecology.occurrence_history) <= ecology.policy.history_limit


def test_unknown_tags_affinities_and_schema_fail_closed():
    ecology, _growth, _locations, _activity, _record = ecology_fixture()
    template = next(iter(ecology.templates.values()))
    data = {
        "id": template.id, "name": template.name,
        "description": template.description, "tags": ["market"],
        "required_affinities": list(template.required_affinities),
        "location_template_id": template.location_template_id,
        "minimum_location_age_days": template.minimum_location_age_days,
        "minimum_distinct_residents": template.minimum_distinct_residents,
        "minimum_activity_days": template.minimum_activity_days,
        "cooldown_days": template.cooldown_days,
    }
    with pytest.raises(ValueError, match="unknown tags"):
        DynamicEventTemplate.from_dict(data)
    data["tags"] = ["community"]
    data["required_affinities"] = ["business"]
    with pytest.raises(ValueError, match="affinity"):
        DynamicEventTemplate.from_dict(data)
    with pytest.raises(ValueError, match="schema version"):
        EventEcologySystem.from_config(
            "data/town_growth.json", state={"schema_version": 999},
        )


def test_forged_occurrences_fail_closed():
    ecology, growth, locations, activity, _record = ecology_fixture()
    event = ecology.select_daily_event(
        day=32, locations=locations, location_growth=growth,
        activity_records=activity,
    )
    for forged in (
        replace(event, location_id="invented_place"),
        replace(event, day=33),
        replace(event, tags=["market"]),
        replace(event, template_id="unknown"),
        replace(event, occurrence_id="daily-event:32:wrong:community_garden"),
    ):
        with pytest.raises(ValueError):
            ecology.validate_occurrence(
                forged, current_day=32, locations=locations,
                location_growth=growth, activity_records=activity,
            )


def test_state_rejects_duplicate_or_unproven_occurrences():
    ecology, growth, locations, activity, _record = ecology_fixture()
    event = ecology.select_daily_event(
        day=32, locations=locations, location_growth=growth,
        activity_records=activity,
    )
    state = ecology.to_dict()
    state["occurrence_history"].append(dict(state["occurrence_history"][0]))
    with pytest.raises(ValueError, match="unique"):
        EventEcologySystem.from_config("data/town_growth.json", state=state)

    unproved = EventEcologySystem.from_config("data/town_growth.json")
    with pytest.raises(ValueError, match="provenance"):
        unproved.validate_occurrence(
            event, current_day=32, locations=locations,
            location_growth=growth, activity_records=activity,
        )


def test_base_event_validation_does_not_grant_dynamic_authority():
    ecology, growth, locations, activity, _record = ecology_fixture()
    forged = DailyEvent(
        "garden_learning_circle", "Garden Learning Circle", "Forged.",
        "community_garden", ["community"], "garden_learning_circle",
        "daily-event:32:garden_learning_circle:community_garden", 32, "base",
    )
    with pytest.raises(ValueError, match="base daily event"):
        ecology.validate_occurrence(
            forged, current_day=32, locations=locations,
            location_growth=growth, activity_records=activity,
        )


def test_occurrence_record_identity_includes_day_template_and_location():
    with pytest.raises(ValueError, match="identity"):
        DynamicEventOccurrenceRecord(
            "daily-event:31:event:community_garden", "event",
            "community_garden", 32,
        )


def test_least_served_dynamic_location_is_selected_deterministically():
    base = [
        Location("town_square", "Town Square", "Square", ["social", "community"]),
        Location("cafe", "Cafe", "Cafe", ["social"]),
        Location("library", "Library", "Library", ["knowledge"]),
        Location("market", "Market", "Market", []),
    ]
    agents = [SimpleNamespace(id=f"agent_{index}") for index in range(1, 7)]
    growth = LocationGrowthSystem.from_config("data/town_growth.json", base)
    broad = [
        {"type": "activity", "day": day, "agent_id": agent.id,
         "location": "town_square"}
        for day in range(22, 64) for agent in agents
    ]
    first = growth.review(
        day=28, agents=agents, locations=base, activity_records=broad,
    )
    growth.activate(first.activation_id, day=28)
    locations = base + growth.activated_locations()
    second = growth.review(
        day=63, agents=agents, locations=locations, activity_records=broad,
    )
    growth.activate(second.activation_id, day=63)
    locations = base + growth.activated_locations()
    local_use = [
        {"type": "activity", "day": day, "agent_id": agent.id,
         "location": location_id}
        for day in range(64, 68)
        for location_id in ("community_garden", "civic_pavilion")
        for agent in agents[:2]
    ]
    prior = DynamicEventOccurrenceRecord(
        "daily-event:40:garden_learning_circle:community_garden",
        "garden_learning_circle", "community_garden", 40,
    )
    ecology = EventEcologySystem.from_config(
        "data/town_growth.json", simulation_seed=11,
    )
    ecology.occurrence_history.append(prior)
    ecology.processed_occurrence_ids.add(prior.occurrence_id)

    event = ecology.select_daily_event(
        day=68, locations=locations, location_growth=growth,
        activity_records=broad + local_use,
    )
    assert event.source_kind == "dynamic"
    assert event.location_id == "civic_pavilion"
    assert event.template_id.startswith("pavilion_")
