"""Schema migrations may add structure, never authority or hidden defaults."""
from copy import deepcopy
from dataclasses import fields

import pytest

from src.systems.growth_proposals import GrowthProposalRecord
from src.systems.persistence_validation import require_record_fields, require_sequence
from tests.systems.test_procedural_institution_proposals import admitted_chain, make_system, Provider


def legacy_state(version):
    system, *_ = admitted_chain()
    state = system.to_dict()
    state['schema_version'] = version
    state.pop('commerce_templates')
    state.pop('next_commerce_template_sequence')
    for row in state['records']:
        row.pop('target_institution_template_id')
    if version < 3:
        state.pop('institution_templates')
        state.pop('next_institution_template_sequence')
        state['records'] = [row for row in state['records'] if row['kind'] != 'institution']
    if version < 2:
        state.pop('event_templates')
        state.pop('next_event_template_sequence')
        state['records'] = [row for row in state['records'] if row['kind'] != 'event']
        for row in state['records']:
            row.pop('target_location_template_id')
    state['next_proposal_sequence'] = len(state['records']) + 1
    state['last_attempt_day'] = state['records'][-1]['proposal_day']
    return state


@pytest.mark.parametrize('version', [1, 2, 3])
def test_genuine_legacy_schema_only_adds_empty_structure(version):
    state = legacy_state(version)
    before = deepcopy(state)
    restored = make_system(Provider(), state).to_dict()
    assert state == before
    assert restored['schema_version'] == 4
    assert restored['commerce_templates'] == []
    assert restored['next_commerce_template_sequence'] == 1
    for original, migrated in zip(state['records'], restored['records']):
        assert all(migrated[key] == value for key, value in original.items())
        assert all(value is None for key, value in migrated.items() if key not in original)
    for key in ('event_templates', 'institution_templates'):
        assert restored[key] == state.get(key, [])


LEGACY_FIELDS = [
    (version, field.name)
    for version in (1, 2, 3)
    for field in fields(GrowthProposalRecord)
    if field.name not in legacy_state(version)['records'][0]
]


@pytest.mark.parametrize('version,field', LEGACY_FIELDS)
@pytest.mark.parametrize('value', [None, 'valid-looking-authority'])
def test_every_modern_record_field_is_rejected_in_legacy(version, field, value):
    state = legacy_state(version)
    state['records'][0][field] = value
    with pytest.raises(ValueError, match='legacy proposal record'):
        make_system(Provider(), state)


@pytest.mark.parametrize('version', [1, 2, 3])
@pytest.mark.parametrize('field', ['commerce_templates', 'next_commerce_template_sequence',
                                  'generated_account_id', 'balance', 'stock'])
def test_legacy_top_level_cannot_smuggle_authority(version, field):
    state = legacy_state(version)
    state[field] = [] if field.endswith('templates') else 1
    with pytest.raises(ValueError):
        make_system(Provider(), state)


@pytest.mark.parametrize('version', [True, 1.0, 4.0, 999, '4', None])
def test_proposal_schema_versions_are_exact_integers(version):
    state = admitted_chain()[0].to_dict()
    state['schema_version'] = version
    with pytest.raises(ValueError):
        make_system(Provider(), state)


def test_shared_record_audit_rejects_missing_and_extra_nullable_fields():
    row = admitted_chain()[0].to_dict()['records'][0]
    assert require_record_fields(row, GrowthProposalRecord) == row
    for field in fields(GrowthProposalRecord):
        invalid = dict(row)
        invalid.pop(field.name)
        with pytest.raises(ValueError):
            require_record_fields(invalid, GrowthProposalRecord)
    with pytest.raises(ValueError):
        require_record_fields(row | {'authority': None}, GrowthProposalRecord)


@pytest.mark.parametrize('sequences,counter', [([1, 1], 3), ([2], 3), ([1], 1),
                                              ([1], 8), ([], True)])
def test_shared_sequence_audit_rejects_duplicates_gaps_and_counter_corruption(sequences, counter):
    with pytest.raises(ValueError):
        require_sequence(sequences, counter, 'test')
