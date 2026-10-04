"""Commit-time failure must restore money and material provenance together."""
from copy import deepcopy

import pytest

from tests.systems.test_materials import build_materials, purchase
from tests.systems.test_production import build_system, produce


@pytest.mark.parametrize('stage', ['payment', 'goods', 'lot_movement'])
def test_purchase_commit_exception_restores_all_authority(monkeypatch, stage):
    economy, materials = build_materials()
    target, method = {
        'payment': (economy, 'transfer'),
        'goods': (materials, '_commit_transfer'),
        'lot_movement': (materials, '_move_allocations'),
    }[stage]
    original = getattr(target, method)
    def fail_after_commit(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('injected commit failure')
    before = deepcopy(economy.to_dict()), deepcopy(materials.to_dict())
    monkeypatch.setattr(target, method, fail_after_commit)
    with pytest.raises(RuntimeError, match='injected'):
        purchase(materials)
    assert before == (economy.to_dict(), materials.to_dict())
    monkeypatch.setattr(target, method, original)
    purchase(materials)
    assert materials.exchanges_reconcile_with_ledger()
    assert materials.material_conservation_holds()


def test_production_commit_exception_restores_consumed_lots(monkeypatch):
    economy, materials = build_system()
    original = materials._move_allocations
    def fail_after_commit(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('injected production failure')
    before = deepcopy(economy.to_dict()), deepcopy(materials.to_dict())
    monkeypatch.setattr(materials, '_move_allocations', fail_after_commit)
    with pytest.raises(RuntimeError, match='injected'):
        produce(materials)
    assert before == (economy.to_dict(), materials.to_dict())
    monkeypatch.setattr(materials, '_move_allocations', original)
    produce(materials)
    assert materials.production_records_are_valid()
