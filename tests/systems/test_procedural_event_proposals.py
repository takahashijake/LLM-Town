from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from src.systems.event_ecology import DynamicEventTemplate, EventEcologySystem
from src.systems.growth_proposals import GrowthProposalSystem
from src.systems.location_growth import LocationTemplate
from src.town.location import Location


DEFAULT_EVENT = object()


class Provider:
    provider_kind = "event-test"

    def __init__(self, event=DEFAULT_EVENT):
        self.location_calls = 0
        self.event_calls = 0
        self.event = {
            "name": "Story Exchange",
            "description": "Residents share local stories.",
            "tags": ["social", "knowledge", "community"],
            "required_affinities": ["knowledge", "community"],
        } if event is DEFAULT_EVENT else event

    def propose_resident(self, context):
        raise AssertionError("resident proposal is disabled")

    def propose_location(self, context):
        self.location_calls += 1
        return {
            "name": f"Story Grove {self.location_calls}",
            "description": "A public place for reading and conversation.",
            "affinities": ["social", "knowledge", "community"],
        }

    def propose_event(self, context):
        self.event_calls += 1
        if isinstance(self.event, Exception):
            raise self.event
        return self.event


def config(*, locations=1, events=1):
    data = json.loads(open("data/town_growth.json", encoding="utf-8").read())
    data["procedural_growth"] = {"policy": {
        "enabled": True, "earliest_proposal_day": 1,
        "review_interval_days": 1, "proposal_cooldown_days": 0,
        "resident_proposal_capacity": 0,
        "location_proposal_capacity": locations,
        "event_proposal_capacity": events,
        "event_templates_per_location": 1,
        "history_limit": locations + events or 1,
    }}
    return data


def make_system(provider, *, locations=1, events=1, state=None):
    return GrowthProposalSystem.from_config(
        config(locations=locations, events=events),
        agents=[SimpleNamespace(name="Ada")],
        locations=[Location("square", "Square", "Square", ["social"])],
        provider=provider, state=state,
    )


def proposal_context(system, day, *, location_growth=None, locations=None, activity=None):
    return system.build_context(
        completed_day=day,
        agents=[SimpleNamespace(id="a", name="Ada")],
        locations=locations or [Location("square", "Square", "Square", ["social"])],
        activity_records=activity or [], town_history=[], location_history=[],
        location_growth=location_growth,
    )


def activated_target(system, *, activation_day=1):
    template = next(iter(system.location_templates.values()))
    location = Location(
        template.location_id, template.name, template.description,
        list(template.affinities),
    )
    growth = SimpleNamespace(activation_records=[SimpleNamespace(
        status="activated", template_id=template.id,
        location_id=template.location_id, activation_day=activation_day,
    )])
    activity = [
        {"type": "activity", "day": day, "agent_id": agent,
         "location": location.id}
        for day in (2, 3, 4) for agent in ("a", "b")
    ]
    return template, location, growth, activity


def admit_location(system):
    record = system.review(day=1, context=proposal_context(system, 1))
    assert record.kind == "location" and record.status == "admitted"


def test_event_candidate_is_semantic_only_and_authority_is_deterministic():
    provider = Provider()
    system = make_system(provider)
    admit_location(system)
    target, location, growth, activity = activated_target(system)
    context = proposal_context(
        system, 4, location_growth=growth,
        locations=[Location("square", "Square", "Square", ["social"]), location],
        activity=activity,
    )
    record = system.review(day=4, context=context)
    template = system.event_templates[record.generated_template_id]
    assert record.kind == "event" and record.status == "admitted"
    assert record.target_location_template_id == target.id
    assert template.id == "generated_event_template_0001"
    assert template.location_template_id == target.id
    assert template.minimum_location_age_days == system.event_policy.minimum_location_age_days
    assert template.minimum_distinct_residents == system.event_policy.minimum_distinct_residents
    assert template.minimum_activity_days == system.event_policy.minimum_activity_days
    assert template.cooldown_days == 14


@pytest.mark.parametrize("candidate", [
    "{bad json",
    [],
    {"name": "x", "description": "x", "tags": ["unknown"],
     "required_affinities": ["community"]},
    {"name": "x", "description": "x", "tags": ["social", "social"],
     "required_affinities": ["community"]},
    {"name": "x", "description": "x", "tags": ["social"],
     "required_affinities": ["justice"]},
    {"name": "x", "description": "x", "tags": ["social"],
     "required_affinities": ["community"], "institution": True},
])
def test_hostile_event_candidates_are_bounded_rejections(candidate):
    system = make_system(Provider(event=candidate))
    admit_location(system)
    _target, location, growth, activity = activated_target(system)
    record = system.review(
        day=4, context=proposal_context(
            system, 4, location_growth=growth, locations=[location], activity=activity,
        ),
    )
    assert record.status == "rejected"
    assert record.target_location_template_id == "generated_location_template_0001"
    assert not system.event_templates
    assert system.next_event_template_sequence == 1


def test_event_provider_exception_consumes_attempt_capacity():
    provider = Provider(event=RuntimeError("boom"))
    system = make_system(provider)
    admit_location(system)
    _target, location, growth, activity = activated_target(system)
    context = proposal_context(
        system, 4, location_growth=growth, locations=[location], activity=activity,
    )
    record = system.review(day=4, context=context)
    assert record.status == "rejected"
    assert record.reason == "provider_exception:RuntimeError"
    assert system.review(day=5, context=context) is None
    assert provider.event_calls == 1


def test_target_requires_activation_exact_identity_and_sustained_use():
    system = make_system(Provider())
    admit_location(system)
    _target, location, growth, activity = activated_target(system)
    assert system.select_event_target(
        completed_day=4, locations=[location], activity_records=activity,
        location_growth=growth,
    ) is not None
    forged = Location(location.id, "Forged", location.description, location.affinities)
    assert system.select_event_target(
        completed_day=4, locations=[forged], activity_records=activity,
        location_growth=growth,
    ) is None
    assert system.select_event_target(
        completed_day=4, locations=[location], activity_records=activity[:2],
        location_growth=growth,
    ) is None


def test_two_generated_locations_are_served_without_starvation():
    provider = Provider()
    system = make_system(provider, locations=2, events=2)
    system.review(day=1, context=proposal_context(system, 1))
    system.review(day=2, context=proposal_context(system, 2))
    templates = sorted(system.location_templates.values(), key=lambda item: item.id)
    locations = [
        Location(item.location_id, item.name, item.description, list(item.affinities))
        for item in templates
    ]
    growth = SimpleNamespace(activation_records=[
        SimpleNamespace(
            status="activated", template_id=item.id, location_id=item.location_id,
            activation_day=index,
        )
        for index, item in enumerate(templates, start=1)
    ])
    activity = [
        {"type": "activity", "day": day, "agent_id": agent,
         "location": location.id}
        for day in (3, 4, 5, 6)
        for location in locations for agent in ("a", "b")
    ]
    first = system.review(day=5, context=proposal_context(
        system, 5, location_growth=growth, locations=locations, activity=activity,
    ))
    second = system.review(day=6, context=proposal_context(
        system, 6, location_growth=growth, locations=locations, activity=activity,
    ))
    assert first.target_location_template_id == templates[0].id
    assert second.target_location_template_id == templates[1].id
    assert {item.location_template_id for item in system.event_templates.values()} == {
        item.id for item in templates
    }


def test_phase_one_state_migrates_to_empty_event_authority():
    system = make_system(Provider(), events=0)
    admit_location(system)
    phase_one = system.to_dict()
    phase_one["schema_version"] = 1
    phase_one.pop("commerce_templates")
    phase_one.pop("next_commerce_template_sequence")
    for record in phase_one["records"]:
        record.pop("target_institution_template_id")
    phase_one.pop("event_templates")
    phase_one.pop("next_event_template_sequence")
    phase_one.pop("institution_templates")
    phase_one.pop("next_institution_template_sequence")
    for record in phase_one["records"]:
        record.pop("target_location_template_id")
    restored = make_system(Provider(), events=0, state=phase_one)
    assert restored.event_templates == {}
    assert restored.next_event_template_sequence == 1
    assert restored.to_dict()["schema_version"] == 4


def test_event_ecology_supplemental_and_live_registration_validate_binding(tmp_path):
    location = LocationTemplate(
        "generated_location_template_0001", "generated_location_0001",
        "Story Grove", "A grove.", ("community", "knowledge", "social"),
    )
    template = DynamicEventTemplate(
        "generated_event_template_0001", "Story Exchange", "Stories.",
        ("community",), ("community",), location.id, 3, 2, 3, 14,
    )
    ecology = EventEcologySystem.from_config(
        "data/town_growth.json", supplemental_templates=[template],
        generated_location_templates={location.id: location},
    )
    assert ecology.templates[template.id] == template
    with pytest.raises(ValueError, match="collides"):
        ecology.register_generated_template(template)
    impossible = DynamicEventTemplate(
        "generated_event_template_0002", "Legal Debate", "No.",
        ("planning",), ("social",), location.id, 3, 2, 3, 14,
    )
    narrow_location = LocationTemplate(
        location.id, location.location_id, location.name, location.description,
        ("community",),
    )
    narrow = EventEcologySystem.from_config(
        "data/town_growth.json",
        generated_location_templates={location.id: narrow_location},
    )
    with pytest.raises(ValueError, match="impossible affinity"):
        narrow.register_generated_template(impossible)


def test_event_state_tampering_fails_collectively():
    system = make_system(Provider())
    admit_location(system)
    _target, location, growth, activity = activated_target(system)
    system.review(day=4, context=proposal_context(
        system, 4, location_growth=growth, locations=[location], activity=activity,
    ))
    state = system.to_dict()
    attacks = [
        lambda data: data.__setitem__("next_event_template_sequence", 1),
        lambda data: data["event_templates"].append(deepcopy(data["event_templates"][0])),
        lambda data: data["records"][1].__setitem__("kind", "location"),
        lambda data: data["records"][1].__setitem__("target_location_template_id", "location_template_001"),
        lambda data: data["event_templates"][0].__setitem__("cooldown_days", 1),
    ]
    for attack in attacks:
        tampered = deepcopy(state)
        attack(tampered)
        with pytest.raises((KeyError, TypeError, ValueError)):
            make_system(Provider(), state=tampered)
