"""A failed checkpoint must preserve the last reconstructable world."""
import json
from pathlib import Path
import random

import pytest

from src.analysis.collective_project_evaluation import engine
from src.simulation.state import SimulationState


@pytest.fixture
def town(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(Path('data/town_growth.json').read_text())
    return engine(tmp_path, 'checkpoint', config)


def test_interrupted_checkpoint_preserves_previous_save(town, monkeypatch):
    town.state.save(town, 1, 8, day_complete=True)
    prior = town.state.path.read_bytes()
    original = Path.write_text

    def interrupted(path, text, *args, **kwargs):
        original(path, text[:100], *args, **kwargs)
        raise OSError('interrupted checkpoint write')

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'write_text', interrupted)
        with pytest.raises(OSError, match='interrupted'):
            town.state.save(town, 2, 8, day_complete=True)
    assert town.state.path.read_bytes() == prior
    assert town.state.load()['current_day'] == 1
    assert not list(town.state.path.parent.glob('.checkpoint.json.*'))
    town.state.save(town, 2, 8, day_complete=True)
    assert town.state.load()['current_day'] == 2


@pytest.mark.parametrize('text', [
    '{"current_day":1,"current_day":2}',
    '{"economy":{"balance":1,"balance":2}}',
    '{"current_day":NaN}',
    '{"current_day":Infinity}',
    '{"needs":1e999}',
    '',
    '{}',
    '[]',
])
def test_ambiguous_save_rejected_without_mutation(tmp_path, text):
    path = tmp_path / 'attacked.json'
    path.write_text(text)
    state = SimulationState(path)
    before = random.getstate()
    with pytest.raises(ValueError):
        state.load()
    assert path.read_text() == text
    assert random.getstate() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ['attacked.json']


def test_duplicate_authority_cannot_be_hidden_by_json_last_key_wins(town):
    town.state.save(town, 1, 8, day_complete=True)
    saved = town.state.path.read_text()
    payload = json.loads(saved)
    assert isinstance(payload['economy'], dict)
    attacked = saved[:-1] + ', "economy": null}'
    town.state.path.write_text(attacked)
    with pytest.raises(ValueError, match='duplicate'):
        town.state.load()
    assert town.state.path.read_text() == attacked


@pytest.mark.parametrize('stage', ['serialize', 'sync', 'replace'])
def test_checkpoint_failure_before_commit_preserves_world(town, monkeypatch, stage):
    import os
    town.state.save(town, 1, 8, day_complete=True)
    prior = town.state.path.read_bytes()
    authority = town.economy.to_dict(), town.materials.to_dict()
    def fail(*args, **kwargs):
        raise OSError('checkpoint fault')
    with monkeypatch.context() as patch:
        if stage == 'serialize':
            patch.setattr(json, 'dumps', fail)
        else:
            patch.setattr(os, 'fsync' if stage == 'sync' else 'replace', fail)
        with pytest.raises(OSError, match='checkpoint fault'):
            town.state.save(town, 2, 8, day_complete=True)
    assert town.state.path.read_bytes() == prior
    assert (town.economy.to_dict(), town.materials.to_dict()) == authority
    assert not list(town.state.path.parent.glob('.checkpoint.json.*'))


def test_nonfinite_engine_state_cannot_replace_checkpoint(town):
    town.state.save(town, 1, 8, day_complete=True)
    prior = town.state.path.read_bytes()
    town.agents[0].needs['social'] = float('nan')
    with pytest.raises(ValueError):
        town.state.save(town, 2, 8, day_complete=True)
    assert town.state.path.read_bytes() == prior
