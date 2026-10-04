from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from src.systems.growth_proposals import GrowthProposalSystem
from src.systems.institution_growth import InstitutionGrowthSystem
from src.town.location import Location


class Provider:
    provider_kind = "institution-test"

    def __init__(self, institution=None):
        self.calls = {"location": 0, "event": 0, "institution": 0}
        self.institution = institution or {
            "name": "Story Grove Commons",
            "role_title": "story grove coordinator",
            "work_activity_name": "Coordinate Story Grove programs",
        }

    def propose_resident(self, context):
        raise AssertionError("resident disabled")

    def propose_location(self, context):
        self.calls["location"] += 1
        return {
            "name": "Story Grove",
            "description": "A public grove for stories and learning.",
            "affinities": ["community", "knowledge", "social"],
        }

    def propose_event(self, context):
        self.calls["event"] += 1
        return {
            "name": "Story Exchange",
            "description": "Residents share stories and local knowledge.",
            "tags": ["community", "knowledge", "social"],
            "required_affinities": ["community", "knowledge"],
        }

    def propose_institution(self, context):
        self.calls["institution"] += 1
        if isinstance(self.institution, Exception):
            raise self.institution
        return self.institution


def config():
    data = json.loads(open("data/town_growth.json", encoding="utf-8").read())
    data["procedural_growth"] = {"policy": {
        "enabled": True,
        "earliest_proposal_day": 1,
        "review_interval_days": 1,
        "proposal_cooldown_days": 0,
        "resident_proposal_capacity": 0,
        "location_proposal_capacity": 1,
        "event_proposal_capacity": 1,
        "event_templates_per_location": 1,
        "institution_proposal_capacity": 1,
        "institution_templates_per_location": 1,
        "generated_institution_wage": 19,
        "generated_institution_startup_grant": 240,
        "generated_institution_funding_source_account_id": (
            "account:employer:town_services"
        ),
        "history_limit": 3,
    }}
    return data


def make_system(provider, state=None):
    return GrowthProposalSystem.from_config(
        config(), agents=[SimpleNamespace(name="Ada")],
        locations=[Location("square", "Square", "Square", ["social"])],
        provider=provider, state=state,
    )


def authoritative_context(system, day, location_growth=None, event_ecology=None):
    locations = [Location("square", "Square", "Square", ["social"])]
    activity = []
    if system.location_templates:
        template = next(iter(system.location_templates.values()))
        locations.append(Location(
            template.location_id, template.name, template.description,
            list(template.affinities),
        ))
        activity = [
            {"type": "activity", "day": use_day, "agent_id": agent,
             "location": template.location_id}
            for use_day in range(2, day + 1)
            for agent in ("a", "b", "c")
        ]
    return system.build_context(
        completed_day=day, agents=[SimpleNamespace(id="a", name="Ada")],
        locations=locations, activity_records=activity,
        town_history=[], location_history=[], location_growth=location_growth,
        event_ecology=event_ecology,
    ), locations, activity


def admitted_chain(provider=None):
    provider = provider or Provider()
    system = make_system(provider)
    context, _locations, _activity = authoritative_context(system, 1)
    system.review(day=1, context=context)
    location_template = next(iter(system.location_templates.values()))
    activation = SimpleNamespace(
        id="location-activation:0001", status="activated",
        template_id=location_template.id,
        location_id=location_template.location_id, activation_day=1,
    )
    location_growth = SimpleNamespace(
        activation_records=[activation],
        templates={location_template.id: location_template},
    )
    context, locations, activity = authoritative_context(
        system, 4, location_growth=location_growth,
    )
    system.review(day=4, context=context)
    event_template = next(iter(system.event_templates.values()))
    occurrences = [
        SimpleNamespace(
            occurrence_id=(
                f"daily-event:{event_day}:{event_template.id}:"
                f"{location_template.location_id}"
            ),
            template_id=event_template.id,
            location_id=location_template.location_id,
            day=event_day,
        )
        for event_day in (5, 6)
    ]
    event_ecology = SimpleNamespace(
        templates={event_template.id: event_template},
        occurrence_history=occurrences,
    )
    context, locations, activity = authoritative_context(
        system, 8, location_growth=location_growth,
        event_ecology=event_ecology,
    )
    record = system.review(day=8, context=context)
    return (
        system, provider, record, location_growth, event_ecology,
        locations, activity,
    )


def test_semantic_candidate_constructs_deterministic_institution_template():
    system, provider, record, *_ = admitted_chain()
    template = system.institution_templates[record.generated_template_id]
    assert record.kind == "institution" and record.status == "admitted"
    assert template.id == "generated_institution_template_0001"
    assert template.institution_key == "generated_institution_key_0001"
    assert template.role.role_template_id == "generated_role_template_0001"
    assert template.role.work_activity_id == "generated_work_activity_0001"
    assert template.role.wage == 19
    assert template.startup_grant == 240
    assert template.relevant_dynamic_event_template_ids == (
        "generated_event_template_0001",
    )
    context = provider.calls
    assert context == {"location": 1, "event": 1, "institution": 1}


@pytest.mark.parametrize("candidate", [
    "{bad json",
    {"name": "x", "role_title": "y", "work_activity_name": "z",
     "employee": "agent_001"},
    {"name": "x", "role_title": "y", "work_activity_name": "z",
     "wage": 999},
    {"name": "x", "role_title": "y", "work_activity_name": "z",
     "location_template_id": "location_template_001"},
    {"name": "x", "role_title": "y", "work_activity_name": "z",
     "event_ids": ["garden_learning_circle"]},
])
def test_authority_injection_is_rejected_and_consumes_capacity(candidate):
    provider = Provider(candidate)
    system, provider, record, *_ = admitted_chain(provider)
    assert record.status == "rejected"
    assert not system.institution_templates
    assert system.next_institution_template_sequence == 1
    assert provider.calls["institution"] == 1


def test_supplemental_and_live_registration_validate_branch_authority():
    system, _provider, _record, location_growth, event_ecology, *_ = (
        admitted_chain()
    )
    template = next(iter(system.institution_templates.values()))
    growth = InstitutionGrowthSystem.from_config(
        "data/town_growth.json", supplemental_templates=[template],
        location_growth=location_growth, event_ecology=event_ecology,
    )
    assert growth.templates[template.id] == template
    with pytest.raises(ValueError, match="collides"):
        growth.register_generated_template(
            template, location_growth=location_growth,
            event_ecology=event_ecology,
        )


def test_phase_two_migration_and_institution_tampering_fail_closed():
    system, *_ = admitted_chain()
    state = system.to_dict()
    phase_two = deepcopy(state)
    phase_two["schema_version"] = 2
    phase_two["records"] = phase_two["records"][:2]
    phase_two["next_proposal_sequence"] = 3
    phase_two["last_attempt_day"] = 4
    phase_two.pop("institution_templates")
    phase_two.pop("next_institution_template_sequence")
    restored = make_system(Provider(), phase_two)
    assert restored.institution_templates == {}
    assert restored.next_institution_template_sequence == 1

    attacks = [
        lambda data: data.__setitem__("next_institution_template_sequence", 1),
        lambda data: data["institution_templates"][0].__setitem__("name", "Fake"),
        lambda data: data["institution_templates"][0].__setitem__("startup_grant", 1),
        lambda data: data["institution_templates"][0]["role"].__setitem__(
            "wage", 999
        ),
        lambda data: data["institution_templates"][0].__setitem__(
            "relevant_dynamic_event_template_ids", ["garden_learning_circle"]
        ),
    ]
    for attack in attacks:
        tampered = deepcopy(state)
        attack(tampered)
        with pytest.raises((KeyError, TypeError, ValueError)):
            make_system(Provider(), tampered)


def test_two_generated_institution_targets_are_fair_and_branch_local():
    class MultiProvider(Provider):
        def propose_location(self, context):
            self.calls["location"] += 1
            return {
                "name": f"Story Grove {self.calls['location']}",
                "description": "A public grove for stories and learning.",
                "affinities": ["community", "knowledge", "social"],
            }

        def propose_event(self, context):
            self.calls["event"] += 1
            return {
                "name": f"Story Exchange {self.calls['event']}",
                "description": "Residents share stories and knowledge.",
                "tags": ["community", "knowledge"],
                "required_affinities": ["community", "knowledge"],
            }

        def propose_institution(self, context):
            self.calls["institution"] += 1
            return {
                "name": f"Story Commons {self.calls['institution']}",
                "role_title": "story coordinator",
                "work_activity_name": "Coordinate story programs",
            }

    data = config()
    policy = data["procedural_growth"]["policy"]
    policy.update({
        "location_proposal_capacity": 2,
        "event_proposal_capacity": 2,
        "institution_proposal_capacity": 2,
        "history_limit": 6,
    })
    provider = MultiProvider()
    system = GrowthProposalSystem.from_config(
        data, agents=[SimpleNamespace(name="Ada")],
        locations=[Location("square", "Square", "Square", ["social"])],
        provider=provider,
    )
    base = [Location("square", "Square", "Square", ["social"])]
    system.review(day=1, context=system.build_context(
        completed_day=1, agents=[], locations=base, activity_records=[],
        town_history=[], location_history=[],
    ))
    system.review(day=2, context=system.build_context(
        completed_day=2, agents=[], locations=base, activity_records=[],
        town_history=[], location_history=[],
    ))
    location_templates = sorted(
        system.location_templates.values(), key=lambda item: item.id
    )
    locations = [
        Location(item.location_id, item.name, item.description,
                 list(item.affinities))
        for item in location_templates
    ]
    activations = [
        SimpleNamespace(
            id=f"location-activation:{index:04d}", status="activated",
            template_id=item.id, location_id=item.location_id,
            activation_day=1,
        )
        for index, item in enumerate(location_templates, start=1)
    ]
    location_growth = SimpleNamespace(
        activation_records=activations,
        templates={item.id: item for item in location_templates},
    )
    activity = [
        {"type": "activity", "day": day, "agent_id": agent,
         "location": location.id}
        for day in range(2, 12) for location in locations
        for agent in ("a", "b", "c")
    ]
    empty_ecology = SimpleNamespace(templates={}, occurrence_history=[])
    for day in (6, 7):
        context = system.build_context(
            completed_day=day, agents=[], locations=[*base, *locations],
            activity_records=activity, town_history=[], location_history=[],
            location_growth=location_growth, event_ecology=empty_ecology,
        )
        record = system.review(day=day, context=context)
        empty_ecology.templates[record.generated_template_id] = (
            system.event_templates[record.generated_template_id]
        )
    event_templates = sorted(
        system.event_templates.values(), key=lambda item: item.id
    )
    occurrences = [
        SimpleNamespace(
            occurrence_id=f"occurrence:{event.id}:{day}",
            template_id=event.id,
            location_id=system.location_templates[
                event.location_template_id
            ].location_id,
            day=day,
        )
        for event in event_templates for day in (8, 9)
    ]
    ecology = SimpleNamespace(
        templates={item.id: item for item in event_templates},
        occurrence_history=occurrences,
    )
    records = []
    for day in (10, 11):
        context = system.build_context(
            completed_day=day, agents=[], locations=[*base, *locations],
            activity_records=activity, town_history=[], location_history=[],
            location_growth=location_growth, event_ecology=ecology,
        )
        records.append(system.review(day=day, context=context))
    assert [item.target_location_template_id for item in records] == [
        item.id for item in location_templates
    ]
    for institution in system.institution_templates.values():
        assert institution.relevant_dynamic_event_template_ids == tuple(
            event.id for event in event_templates
            if event.location_template_id == institution.location_template_id
        )
