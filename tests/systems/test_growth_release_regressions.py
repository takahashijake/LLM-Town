"""Small regressions for defects found by the integrated corruption matrix."""
from copy import deepcopy

import pytest

from src.systems.commerce_growth import CommerceGrowthSystem, CommerceReview
from src.systems.institution_growth import InstitutionGrowthSystem, InstitutionReview
from tests.systems.test_commerce_growth import _ready_engine
from tests.systems.test_procedural_institution_proposals import admitted_chain, make_system, Provider


@pytest.mark.parametrize('system_type,prefix', [
    (CommerceGrowthSystem, 'commerce'), (InstitutionGrowthSystem, 'institution'),
])
def test_load_cannot_truncate_overlong_duplicate_reviews(system_type, prefix):
    system = system_type.from_config('data/town_growth.json')
    state = system.to_dict()
    state['review_history'] = [
        dict(event_key=f'{prefix}-review:day:{day}', day=day, status='waiting', reason='waiting',
             **({'activation_id': None, 'template_id': None} if prefix == 'commerce' else
                {'formation_id': None, 'template_id': None, 'candidate_agent_id': None}))
        for day in range(1, system.policy.history_limit + 1)
    ]
    state['processed_event_keys'] = [row['event_key'] for row in state['review_history']]
    state['review_history'].append(deepcopy(state['review_history'][0]))
    with pytest.raises(ValueError, match='history'):
        system_type.from_config('data/town_growth.json', state)


@pytest.mark.parametrize('record_type,prefix,field', [
    (CommerceReview, 'commerce', 'activation_id'),
    (CommerceReview, 'commerce', 'template_id'),
    (InstitutionReview, 'institution', 'formation_id'),
    (InstitutionReview, 'institution', 'template_id'),
    (InstitutionReview, 'institution', 'candidate_agent_id'),
])
@pytest.mark.parametrize('value', [[], '', 0, False])
def test_waiting_reviews_require_null_authority(record_type, prefix, field, value):
    with pytest.raises(ValueError):
        record_type(event_key=f'{prefix}-review:day:1', day=1, status='waiting',
                    reason='waiting', **{field: value})


def test_valid_other_role_cannot_replace_formation_role(tmp_path):
    engine = _ready_engine(tmp_path)
    record = engine.institution_growth.formation_records[0]
    record.role_template_id = engine.institution_growth.template('institution_template_002').role.role_template_id
    with pytest.raises(ValueError, match='institution authority'):
        engine.validate_institution_authorities()


@pytest.mark.parametrize('field', ['minimum_activity_days', 'minimum_candidate_activities'])
def test_generated_persisted_template_cannot_omit_nullable_fields(field):
    state = admitted_chain()[0].to_dict()
    state['institution_templates'][0].pop(field)
    with pytest.raises(ValueError, match='persisted record'):
        make_system(Provider(), state)
