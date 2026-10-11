"""V9 opt-in compatibility and validation before random stream mutation."""
from copy import deepcopy
import json
import random

import pytest

from src.analysis.collective_project_evaluation import engine
from src.simulation.project_random_state import restore_project_random_state


@pytest.mark.parametrize('mutate', [
    lambda s: s.update(version=True),
    lambda s: s.update(version=2),
    lambda s: s['state'][1].pop(),
    lambda s: s['state'][1].__setitem__(0, True),
    lambda s: s['state'][1].__setitem__(0, -1),
    lambda s: s['state'][1].__setitem__(-1, 625),
    lambda s: s['state'].__setitem__(2, float('nan')),
    lambda s: s.update(unexpected=1),
])
def test_malformed_arbitration_state_cannot_change_runtime_stream(mutate):
    before = random.getstate()
    state = json.loads(json.dumps({'version': 1, 'state': before}))
    mutate(state)
    with pytest.raises(ValueError):
        restore_project_random_state(state)
    assert random.getstate() == before


def test_legacy_save_has_explicit_opt_in_without_invented_evidence(tmp_path):
    config = tmp_path / 'config.json'
    data = json.loads(open('data/town_growth.json').read())
    config.write_text(json.dumps(data))
    legacy = engine(tmp_path, 'legacy', config)
    legacy.state.save(legacy, 1, 8, day_complete=True)
    saved = json.loads(legacy.state.path.read_text())
    assert 'collective_projects' not in saved and 'v9_random_state' not in saved
    # Narrative never supplies eligibility or work, including on migration.
    saved['agents'][0]['memory_summary'] = 'Garden project complete; everybody contributed.'
    legacy.state.path.write_text(json.dumps(saved))
    data['collective_projects'] = {'enabled': True}
    config.write_text(json.dumps(data))
    upgraded = engine(tmp_path, 'legacy', config, load=True)
    assert not upgraded.collective_projects.projects
    assert not upgraded.collective_projects.contributions
    assert not upgraded.collective_projects.effects
    upgraded.collective_projects.review(2)
    assert not upgraded.collective_projects.projects  # institution not yet eligible
    upgraded.state.save(upgraded, 2, 8, day_complete=True)
    assert engine(tmp_path, 'legacy', config, load=True).collective_projects.to_dict() == upgraded.collective_projects.to_dict()


def test_missing_project_section_with_execution_claim_fails_closed(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(open('data/town_growth.json').read())
    town = engine(tmp_path, 'legacy', config)
    town.state.save(town, 1, 8, day_complete=True)
    saved = json.loads(town.state.path.read_text())
    forged = deepcopy(saved)
    forged['activity_records'].append({'activity_id': 'civic_garden_prepare', 'civic_status': 'verified',
                                      'source_project_id': 'civic-project:garden_learning'})
    town.state.path.write_text(json.dumps(forged))
    with pytest.raises(ValueError):
        engine(tmp_path, 'legacy', config, load=True)
    assert town.economy.to_dict() == saved['economy']


def test_disabled_policy_rejects_arbitration_section_even_without_effects(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(open('data/town_growth.json').read())
    town = engine(tmp_path, 'disabled', config)
    town.state.save(town, 1, 8, day_complete=True)
    save = json.loads(town.state.path.read_text())
    save['collective_projects'] = town.collective_projects.to_dict()
    save['v9_random_state'] = {'version': 1, 'state': 'forged'}
    town.state.path.write_text(json.dumps(save))
    with pytest.raises(ValueError):
        engine(tmp_path, 'disabled', config, load=True)
