"""Execution, hostile evidence, bounds and replay contracts for civic authority."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.agents.agent import Agent
from src.behavior.activity import Activity
from src.systems.collective_projects import (
    CollectiveProjectSystem, ProjectPolicy, PROJECT_ID, WORK, WORKSHOP,
)
from src.town.location import Location


def fixture(policy=None):
    agents = [Agent(id=f'agent_{i:03d}', name=f'Resident {i}', personality='curious',
                    location_id='community_garden') for i in range(1, 4)]
    formation = SimpleNamespace(id='institution-formation:0001', institution_id='institution:0001',
                                institution_key='community_garden_stewardship',
                                status='activated', activation_day=1, location_id='community_garden')
    # Use a real dataclass formation for pure serialization.
    from src.systems.institution_growth import InstitutionFormationRecord
    formation = InstitutionFormationRecord(
        id=formation.id, institution_id=formation.institution_id,
        event_key='institution-review:day:1', template_id='institution_template_001',
        institution_key=formation.institution_key, name='Garden stewardship',
        location_id=formation.location_id, location_activation_id='location-activation:0001',
        employee_agent_id=agents[-1].id, employer_account_id='account:institution:0001',
        employment_id='employment:institution:0001', role_template_id='garden_steward',
        review_day=1, status='activated', activation_day=1, startup_transaction_id='tx:1')
    institutions = SimpleNamespace(formation_records=[formation])
    locations = [Location('community_garden', 'Garden', 'Public garden', ['knowledge', 'community'])]
    system = CollectiveProjectSystem(policy or ProjectPolicy(enabled=True), institutions=institutions,
                                     agents=agents, locations=locations, activity_records=[])
    system.review(1)
    return system, agents


def restore(system, state=None):
    return CollectiveProjectSystem(system.policy, institutions=system.institutions,
                                   agents=system.agents, locations=system.locations,
                                   activity_records=system.activities,
                                   state=state if state is not None else system.to_dict())


def perform(system, agent, day, hour=8):
    offered = system.opportunities(agent, day, hour)
    assert offered
    activity = offered[0]
    agent.set_activity(activity)
    record = dict(type='activity', day=day, hour=hour, agent_id=agent.id,
                  activity_id=activity.id, location=activity.location_id,
                  source_project_id=activity.source_project_id,
                  source_project_effect_id=activity.source_project_effect_id)
    system.activities.append(record)
    assert system.execute(agent, activity, record, day, hour)
    return activity, record


def complete():
    system, agents = fixture()
    for day, agent in [(2, agents[0]), (3, agents[1]), (4, agents[0]), (5, agents[1])]:
        perform(system, agent, day)
        system.review(day)
    return system, agents


def test_independent_work_and_future_learning_effect():
    system, agents = fixture()
    assert not system.opportunities(agents[0], 1, 8)
    for day in range(2, 5):
        perform(system, agents[0], day)
        system.review(day)
        assert system.projects[0].status == 'active'
        assert not system.effects
        restore(system)
    # The last slot is reserved for another independent resident.
    assert not system.opportunities(agents[0], 5, 8)
    perform(system, agents[1], 5)
    assert not system.effects
    restore(system)  # immediately before completion
    system.review(5)
    assert system.projects[0].status == 'completed'
    assert system.effects[0].available_day == 6
    assert not system.opportunities(agents[0], 5, 9)
    restored = restore(system)
    activity, _ = perform(restored, agents[2], 6)
    assert activity.id == WORKSHOP
    assert not restored.opportunities(agents[0], 6, 8)  # workshop capacity
    restore(restored)


def test_reviews_execution_and_terminal_effect_are_idempotent():
    system, agents = fixture()
    activity, record = perform(system, agents[0], 2)
    state = system.to_dict()
    assert not system.execute(agents[0], activity, record, 2, 8)
    assert system.to_dict() == state
    system.review(2)
    state = system.to_dict()
    system.review(2)
    system.review(1)
    assert system.to_dict() == state
    system, _ = complete()
    premature = system.to_dict()
    premature["last_review_day"] -= 1
    with pytest.raises(ValueError):
        restore(system, premature)
    original_effects = list(system.effects)
    system.review(6)
    system.review(6)
    assert system.effects == original_effects
    with pytest.raises(ValueError):
        system.cancel(PROJECT_ID, 7)


def test_expiration_and_operator_cancellation_never_unlock_benefit():
    system, agents = fixture(ProjectPolicy(enabled=True, lifetime_days=2))
    perform(system, agents[0], 2)
    system.review(2)
    system.review(4)
    assert system.projects[0].status == 'expired'
    assert not system.effects and not system.opportunities(agents[1], 5, 8)
    restore(system)
    system, agents = fixture()
    perform(system, agents[0], 2)
    system.cancel(PROJECT_ID, 2)
    restore(system)
    assert not system.effects
    assert not system.opportunities(agents[1], 3, 8)


@pytest.mark.parametrize('field,value', [
    ('enabled', 1), ('enabled', 'true'), ('required_units', True), ('required_units', 1),
    ('required_units', 17), ('minimum_residents', 1), ('minimum_residents', 9),
    ('minimum_residents', 5), ('lifetime_days', 1), ('lifetime_days', 61),
    ('daily_capacity', 0), ('daily_capacity', 5), ('daily_capacity', 1.0),
])
def test_policy_rejects_types_and_unbounded_requirements(field, value):
    with pytest.raises(ValueError):
        ProjectPolicy.from_config({field: value})


def test_policy_rejects_unsupported_templates_and_resource_authority():
    for config in [{'template': 'arbitrary'}, {'resource_amount': 100}, {'budget': 100}, None]:
        with pytest.raises(ValueError):
            ProjectPolicy.from_config(config)


@pytest.mark.parametrize('mutation', [
    lambda s: s['contributions'].append(deepcopy(s['contributions'][0])),
    lambda s: s['contributions'][0].update(actor_id='ghost'),
    lambda s: s['contributions'][0].update(actor_id='agent_003'),
    lambda s: s['contributions'][0].update(project_id='civic-project:other'),
    lambda s: s['contributions'][0].update(location_id='library'),
    lambda s: s['contributions'][0].update(day=1),
    lambda s: s['contributions'][0].update(day=100),
    lambda s: s['contributions'][0].update(hour=True),
    lambda s: s['contributions'][0].update(activity_index=1),
    lambda s: s['contributions'][0].update(activity_index=-1),
    lambda s: s['contributions'][0].update(execution_key='another-branch'),
    lambda s: s['contributions'][0].update(id='forged'),
    lambda s: s['contributions'][0].update(quantity=10),
    lambda s: s['projects'][0].update(template_id='other'),
    lambda s: s['projects'][0].update(formation_id='institution-formation:0002'),
    lambda s: s['projects'][0].update(institution_id='institution:0002'),
    lambda s: s['projects'][0].update(deadline_day=100),
    lambda s: s['projects'][0].update(status='completed', resolution_day=2),
    lambda s: s.update(last_review_day=0),
    lambda s: s.update(schema_version=True),
    lambda s: s.update(schema_version=2),
    lambda s: s.update(contributions=[]),
    lambda s: s.update(projects=[]),
    lambda s: s.update(effects=[{'id': 'fake'}]),
    lambda s: s['policy'].update(enabled=False),
    lambda s: s.update(next_sequence=2),
])
def test_corrupted_evidence_fails_closed_without_mutation(mutation):
    system, agents = fixture()
    perform(system, agents[0], 2)
    system.review(2)
    original = deepcopy(system.to_dict())
    activities = deepcopy(system.activities)
    changed = deepcopy(original)
    mutation(changed)
    with pytest.raises((ValueError, TypeError)):
        restore(system, changed)
    assert system.to_dict() == original and system.activities == activities


@pytest.mark.parametrize('field,value', [
    ('agent_id', 'agent_002'), ('source_project_id', 'other'), ('location', 'library'),
    ('day', 3), ('hour', 9), ('activity_id', 'organize_community'),
    ('civic_execution_key', 'wrong'), ('civic_status', 'claimed'),
])
def test_persisted_activity_must_match_exact_execution(field, value):
    system, agents = fixture()
    perform(system, agents[0], 2)
    system.review(2)
    system.activities[0][field] = value
    with pytest.raises(ValueError):
        restore(system)


@pytest.mark.parametrize('attack', ['copy_record', 'other_actor', 'changed_activity', 'wrong_location',
                                    'wrong_hour', 'copied_activity', 'narrative'])
def test_forged_runtime_execution_never_advances(attack):
    system, agents = fixture()
    a = system.opportunities(agents[0], 2, 8)[0]
    agents[0].set_activity(a)
    record = dict(type='activity', agent_id=agents[0].id, day=2, hour=8,
                  activity_id=WORK, location=a.location_id, source_project_id=PROJECT_ID)
    system.activities.append(record)
    actor, hour = agents[0], 8
    if attack == 'copy_record': record = dict(record)
    if attack == 'other_actor': actor = agents[1]
    if attack == 'changed_activity': a.source_project_id = 'other'
    if attack == 'wrong_location': agents[0].location_id = 'library'
    if attack == 'wrong_hour': hour = 9
    if attack == 'copied_activity': a = replace(a)
    if attack == 'narrative':
        a = Activity('organize_community', 'Project complete', 'community_garden',
                     'All residents contributed', ['community'], source_project_id=PROJECT_ID)
    before = system.to_dict()
    assert not system.execute(actor, a, record, 2, hour)
    assert system.to_dict() == before


def test_capacity_distinct_days_and_same_tick_actor_order():
    system, agents = fixture(ProjectPolicy(enabled=True, required_units=4, daily_capacity=2))
    # Execution order need not be alphabetical; persisted contributions are canonical.
    perform(system, agents[1], 2)
    perform(system, agents[0], 2)
    system.review(2)
    assert system.projects[0].status == 'active'
    restore(system)
    assert [c.actor_id for c in system.contributions] == sorted(a.id for a in agents[:2])
    perform(system, agents[1], 3)
    perform(system, agents[0], 3)
    system.review(3)
    assert system.projects[0].status == 'completed'
    restore(system)


def test_final_slot_reserves_a_later_day():
    system, agents = fixture(ProjectPolicy(enabled=True, required_units=2, daily_capacity=2))
    perform(system, agents[0], 2)
    assert not system.opportunities(agents[1], 2, 8)
    system.review(2)
    perform(system, agents[1], 3)
    system.review(3)
    assert system.projects[0].status == 'completed'


def test_stale_offers_recheck_remaining_capacity_and_day_reservation():
    system, agents = fixture(ProjectPolicy(enabled=True, required_units=2, daily_capacity=2))
    stale = system.opportunities(agents[1], 2, 8)[0]
    perform(system, agents[0], 2)
    agents[1].set_activity(stale)
    record = dict(type='activity', day=2, hour=8, agent_id=agents[1].id,
                  activity_id=WORK, location='community_garden', source_project_id=PROJECT_ID)
    system.activities.append(record)
    before = system.to_dict()
    assert not system.execute(agents[1], stale, record, 2, 8)
    assert system.to_dict() == before


def test_stale_workshop_offers_cannot_bypass_same_tick_capacity():
    system, agents = complete()
    stale = system.opportunities(agents[1], 6, 8)[0]
    perform(system, agents[0], 6)
    agents[1].set_activity(stale)
    record = dict(type='activity', day=6, hour=8, agent_id=agents[1].id,
                  activity_id=WORKSHOP, location='community_garden',
                  source_project_effect_id=stale.source_project_effect_id)
    system.activities.append(record)
    before = system.to_dict()
    assert not system.execute(agents[1], stale, record, 6, 8)
    assert system.to_dict() == before


@pytest.mark.parametrize('day,hour', [(1, 8), (3, 8), (True, 8), (2, -1), (2, 24), (2, True)])
def test_stale_future_and_invalid_clock_never_offer_work(day, hour):
    system, agents = fixture()
    assert not system.opportunities(agents[0], day, hour)


def test_missing_prerequisite_and_disabled_policy_never_create_projects():
    system, agents = fixture()
    system.institutions.formation_records[0].status = 'rejected'
    other = CollectiveProjectSystem(ProjectPolicy(enabled=True), institutions=system.institutions,
                                    agents=agents, locations=system.locations, activity_records=[])
    other.review(1)
    assert not other.projects
    disabled, agents = fixture(ProjectPolicy())
    assert not disabled.projects and not disabled.opportunities(agents[0], 1, 8)


def test_resident_copy_cannot_impersonate_authorized_object():
    system, agents = fixture()
    assert not system.opportunities(deepcopy(agents[0]), 2, 8)


@pytest.mark.parametrize('field,value', [('type', 'claim'), ('source_project_effect_id', 'fake')])
def test_executor_rejects_mixed_or_narrative_record_authority(field, value):
    system, agents = fixture()
    activity = system.opportunities(agents[0], 2, 8)[0]
    agents[0].set_activity(activity)
    record = dict(type='activity', day=2, hour=8, agent_id=agents[0].id,
                  activity_id=WORK, location='community_garden', source_project_id=PROJECT_ID)
    record[field] = value
    system.activities.append(record)
    assert not system.execute(agents[0], activity, record, 2, 8)
    assert not system.contributions


def test_historical_roster_cannot_include_future_arrivals():
    from src.systems.collective_projects import validate_authority
    from dataclasses import asdict
    system, agents = fixture()
    with pytest.raises(ValueError):
        validate_authority(system.to_dict(), system.policy,
                           [asdict(r) for r in system.institutions.formation_records],
                           {a.id for a in agents}, {'community_garden'}, [],
                           {agents[2].id: 10})


@pytest.mark.parametrize('history', [None, {}, ['work'], [None]])
def test_malformed_execution_history_fails_closed(history):
    system, _ = fixture()
    system.activities = history
    with pytest.raises(ValueError):
        restore(system)


def test_opportunity_storage_is_bounded_with_large_resident_pools():
    system, agents = complete()
    agents.extend(Agent(id=f'late_{i:03d}', name=f'Late resident {i}', personality='curious',
                        location_id='community_garden') for i in range(100))
    for agent in agents:
        system.opportunities(agent, 6, 8)
    assert len(system._offers) == 64
