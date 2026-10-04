"""Closed commerce proposals cannot carry economic authority."""
from copy import deepcopy
from dataclasses import replace

import pytest

from src.systems.growth_proposals import GrowthProposalRecord, payload_digest
from src.systems.commerce_growth import CommerceGrowthSystem
from tests.systems.test_procedural_institution_proposals import admitted_chain


class CommerceProvider:
    provider_kind = "commerce-test"

    def __init__(self, candidate):
        self.candidate = candidate
        self.calls = 0
        self.context = None

    def propose_commerce(self, context):
        self.calls += 1
        self.context = context
        if isinstance(self.candidate, Exception):
            raise self.candidate
        return self.candidate


def proposal_system(candidate):
    system, *_ = admitted_chain()
    system.policy = replace(system.policy, commerce_proposal_capacity=1, history_limit=4)
    system.provider = CommerceProvider(candidate)
    target = next(iter(system.institution_templates.values()))
    context = {"commerce_target": {
        "institution_template_id": target.id,
        "location_template_id": target.location_template_id,
        "name": target.name, "place": "Story Grove",
    }}
    return system, context


@pytest.mark.parametrize("candidate", [
    "not json", "[]", {}, None, RuntimeError("provider failure"),
    {"offer": "unknown"}, {"offer": []},
    *[{"offer": "community_meals", field: value} for field, value in (
        ("seller_id", "seller:market_stall"), ("account_id", "account:forged"),
        ("inventory_id", "inventory:forged"), ("institution_id", "institution:forged"),
        ("employee_id", "agent_001"), ("employment_id", "employment:forged"),
        ("quantity", 999), ("unit_price", 1), ("recipe", {}),
        ("activation_day", 1), ("stock", 20), ("demand", 100),
    )],
])
def test_invalid_commerce_consumes_attempt(candidate):
    system, context = proposal_system(candidate)
    record = system.review(day=10, context=context)
    assert record.status == "rejected"
    assert record.target_institution_template_id == "generated_institution_template_0001"
    assert not system.commerce_templates
    assert system.remaining_capacity("commerce") == 0
    assert system.review(day=11, context=context) is None
    assert system.provider.calls == 1


def test_commerce_schema_identity_context_and_collision():
    system, context = proposal_system('{"offer":"community_meals"}')
    record = system.review(day=10, context=context)
    assert record.status == "admitted"
    assert record.canonical_payload_hash == payload_digest({"offer": "community_meals"})
    template = system.commerce_templates[record.generated_template_id]
    assert template.id == "generated_commerce_template_0001"
    assert template.production_activity_id == "generated_work_activity_0001"
    assert template.purchase_activity_id == "generated_purchase_activity_0001"
    assert system.provider.context == {
        "target_institution": "Story Grove Commons", "target_place": "Story Grove",
        "observed_evidence": "sustained work, local use and meal purchases",
        "permitted_offers": ["community_meals"],
    }
    commerce = CommerceGrowthSystem.from_config("data/town_growth.json")
    commerce.register_generated_template(template, proposal_authority=system)
    assert not commerce.activation_records
    with pytest.raises(ValueError, match="collision"):
        commerce.register_generated_template(template, proposal_authority=system)
    with pytest.raises(ValueError):
        system.derive_commerce_template(template.id, template.institution_template_id, "location_template_001")
    with pytest.raises(ValueError):
        system.derive_commerce_template(template.id, "institution_template_001", template.location_template_id)


@pytest.mark.parametrize("field,value", [
    ("target_institution_template_id", "institution_template_001"),
    ("target_location_template_id", "location_template_001"),
    ("kind", "institution"),
])
def test_target_records_fail_closed(field, value):
    system, context = proposal_system({"offer": "community_meals"})
    record = system.review(day=10, context=context)
    data = deepcopy(record.__dict__)
    data[field] = value
    with pytest.raises(ValueError):
        GrowthProposalRecord.from_dict(data)


def test_registration_requires_proposal_provenance_and_later_review():
    from types import SimpleNamespace

    system, context = proposal_system({"offer": "community_meals"})
    record = system.review(day=84, context=context)
    template = system.commerce_templates[record.generated_template_id]
    commerce = CommerceGrowthSystem.from_config("data/town_growth.json")
    with pytest.raises(ValueError, match="provenance"):
        commerce.register_generated_template(replace(template, input_quantity=99), proposal_authority=system)
    commerce.register_generated_template(template, proposal_authority=system)
    commerce.templates.pop("commerce_template_001")
    calls = []

    def eligible(*args, **kwargs):
        calls.append(kwargs["day"])
        return "eligible", SimpleNamespace(
            id="formation:test", institution_id="institution:test", location_id="location:test",
            location_activation_id="activation:test", employee_agent_id="agent:test",
            employment_id="employment:test", employer_account_id="account:test",
        )

    commerce.readiness_reason = eligible
    arguments = dict(agents=[], locations=[], institution_growth=None,
                     location_growth=None, economy=None, materials=None, activity_records=[])
    assert commerce.review(day=84, **arguments).status == "waiting"
    assert calls == []
    assert commerce.review(day=91, **arguments).status == "proposed"
    assert calls == [91]


def test_schema_three_migrates_without_commerce_authority():
    from tests.systems.test_procedural_institution_proposals import make_system, Provider

    system, *_ = admitted_chain()
    state = system.to_dict()
    state["schema_version"] = 3
    state.pop("commerce_templates")
    state.pop("next_commerce_template_sequence")
    for record in state["records"]:
        record.pop("target_institution_template_id")
    restored = make_system(Provider(), state)
    assert restored.to_dict()["schema_version"] == 4
    assert restored.commerce_templates == {}
    assert restored.next_commerce_template_sequence == 1
    assert all(item.target_institution_template_id is None for item in restored.records)
    state["commerce_templates"] = []
    with pytest.raises(ValueError, match="v3"):
        make_system(Provider(), state)


def test_pending_commerce_cannot_claim_another_formation(tmp_path):
    from tests.systems.test_commerce_growth import _ready_engine, _propose

    engine = _ready_engine(tmp_path)
    record = _propose(engine)
    engine.validate_commerce_authorities()
    record.institution_formation_id = "institution-formation:9999"
    with pytest.raises(ValueError, match="historical authority"):
        engine.validate_commerce_authorities()


@pytest.mark.parametrize("version", [1, 2, 3])
def test_legacy_record_schema_cannot_smuggle_new_target_field(version):
    from tests.systems.test_procedural_institution_proposals import make_system, Provider

    system, *_ = admitted_chain()
    state = system.to_dict()
    state.update(schema_version=version)
    state.pop("commerce_templates")
    state.pop("next_commerce_template_sequence")
    for record in state["records"]:
        record.pop("target_institution_template_id")
    if version < 3:
        state.pop("institution_templates")
        state.pop("next_institution_template_sequence")
        state["records"] = [item for item in state["records"] if item["kind"] != "institution"]
    if version == 1:
        state.pop("event_templates")
        state.pop("next_event_template_sequence")
        state["records"] = [item for item in state["records"] if item["kind"] != "event"]
        for record in state["records"]:
            record.pop("target_location_template_id")
    state["next_proposal_sequence"] = len(state["records"]) + 1
    state["last_attempt_day"] = state["records"][-1]["proposal_day"]
    field = "target_location_template_id" if version == 1 else "target_institution_template_id"
    state["records"][0][field] = "forged_authority"
    with pytest.raises(ValueError, match="legacy proposal record"):
        make_system(Provider(), state)
