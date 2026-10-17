"""A failed checkpoint must leave the previous reconstructable world intact."""
import errno
import json
import random

import pytest

from src.analysis.collective_project_evaluation import engine


@pytest.fixture
def town(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(open('data/town_growth.json').read())
    town = engine(tmp_path, 'checkpoint', config)
    town.state.save(town, 0, 8, day_complete=True)
    return town, config


def test_failed_checkpoint_replacement_preserves_reconstructable_authority(town, monkeypatch):
    town, config = town
    before = town.state.path.read_bytes()
    contents = set(town.state.path.parent.iterdir())
    caller = random.getstate()

    def disk_failure(*args):
        raise OSError(errno.ENOSPC, 'injected full disk')

    monkeypatch.setattr('os.replace', disk_failure)
    with pytest.raises(OSError, match='injected full disk'):
        town.state.save(town, 1, 8, day_complete=True)
    assert town.state.path.read_bytes() == before
    assert set(town.state.path.parent.iterdir()) == contents
    restored = engine(town.state.path.parent, 'checkpoint', config, load=True)
    assert restored.economy.to_dict() == json.loads(before)['economy']
    assert random.getstate() == caller


def test_serialization_failure_preserves_checkpoint_and_cleans_temporary_file(town, monkeypatch):
    town, _ = town
    before = town.state.path.read_bytes()
    contents = set(town.state.path.parent.iterdir())
    town.recent_actions.append(object())
    with pytest.raises(TypeError):
        town.state.save(town, 1, 8)
    assert town.state.path.read_bytes() == before
    assert set(town.state.path.parent.iterdir()) == contents


def test_successful_replacement_preserves_save_schema(town):
    town, config = town
    old = json.loads(town.state.path.read_bytes())
    town.state.save(town, 1, 8, day_complete=True)
    saved = json.loads(town.state.path.read_bytes())
    assert saved == {**old, 'current_day': 1}
    restored = engine(town.state.path.parent, 'checkpoint', config, load=True)
    assert json.loads(json.dumps(restored.materials.to_dict())) == saved['materials']
    assert not list(town.state.path.parent.glob('*.tmp'))
