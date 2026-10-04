from dataclasses import replace
from types import SimpleNamespace

from src.analysis.growth_audits import conservation_checks
from tests.systems.test_materials import build_materials, purchase
from tests.systems.test_production import build_system, produce


def test_shared_conservation_audit_detects_currency_and_goods_corruption():
    economy, materials = build_materials()
    engine = SimpleNamespace(economy=economy, materials=materials)
    purchase(materials)
    assert all(conservation_checks(engine).values())
    economy._accounts['buyer_account'] = replace(economy._accounts['buyer_account'], balance=99)
    assert not conservation_checks(engine)['currency']
    assert not conservation_checks(engine)['ledger']
    inventory = materials.get_inventory('buyer_inventory')
    materials._inventories[inventory.id] = inventory.with_quantity('meal', 7)
    checks = conservation_checks(engine)
    assert not checks['materials']
    assert not checks['material_history']
    assert not checks['lot_provenance']


def test_shared_production_audit_detects_broken_lineage():
    economy, materials = build_system()
    record = produce(materials)
    key = record.output_lot_ids[0]
    materials.lots[key] = replace(materials.lots[key], parent_lot_ids=())
    assert not conservation_checks(SimpleNamespace(economy=economy, materials=materials))['production']
