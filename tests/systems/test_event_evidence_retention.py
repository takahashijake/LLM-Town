"""A bounded event history must retain evidence referenced by later authority."""
from copy import deepcopy
from dataclasses import replace

import pytest

from tests.systems.test_event_ecology import ecology_fixture


def test_protected_occurrence_survives_bounded_real_selection():
    ecology, growth, locations, activity, _ = ecology_fixture()
    ecology.policy = replace(ecology.policy, history_limit=3)
    protected = set()
    for day in range(32, 113):
        activity.extend({'type': 'activity', 'day': day - 1, 'hour': 8,
                         'agent_id': agent, 'location': 'community_garden'}
                        for agent in ('a', 'b', 'c'))
        event = ecology.select_daily_event(
            day=day, locations=locations, location_growth=growth, activity_records=activity,
            protected_occurrence_ids=protected)
        if event.source_kind == 'dynamic' and not protected:
            protected.add(event.occurrence_id)
    assert protected.issubset(ecology.processed_occurrence_ids)
    assert len(ecology.occurrence_history) == 3
    assert all(ecology.validate(locations=locations, location_growth=growth,
                                activity_records=activity).values())
    before = deepcopy(ecology.to_dict())
    for row in list(ecology.occurrence_history):
        with pytest.raises(ValueError, match='already processed'):
            ecology.select_daily_event(day=row.day, locations=locations, location_growth=growth,
                                       activity_records=activity)
    assert ecology.to_dict() == before


def test_history_cannot_discard_required_evidence_to_make_room():
    ecology, growth, locations, activity, _ = ecology_fixture()
    ecology.policy = replace(ecology.policy, history_limit=1)
    first = ecology.select_daily_event(day=32, locations=locations, location_growth=growth,
                                       activity_records=activity)
    activity.extend({'type': 'activity', 'day': day, 'agent_id': agent,
                     'location': 'community_garden'}
                    for day in range(33, 53) for agent in ('a', 'b', 'c'))
    before = deepcopy(ecology.to_dict())
    with pytest.raises(ValueError, match='cannot retain'):
        ecology.select_daily_event(day=52, locations=locations, location_growth=growth,
                                   activity_records=activity,
                                   protected_occurrence_ids={first.occurrence_id})
    assert ecology.to_dict() == before
