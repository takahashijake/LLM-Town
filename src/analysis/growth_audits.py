"""Shared release audits; use simulation authorities rather than shadow state."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.simulation.engine import SimulationEngine


def conservation_checks(engine: SimulationEngine) -> dict[str, bool]:
    """Reconcile currency, goods, transfers and lot lineage independently."""
    return {
        'currency': engine.economy.conservation_holds(),
        'ledger': engine.economy.ledger_reconstructs_balances(),
        'materials': engine.materials.material_conservation_holds(),
        'material_history': engine.materials.material_history_reconstructs_inventories(),
        'lot_provenance': engine.materials.provenance_reconciles(),
        'lot_history': engine.materials.provenance_history_reconstructs_holdings(),
        'lot_movements': engine.materials.lot_movements_reconcile_with_events(),
        'exchange_payments': engine.materials.exchanges_reconcile_with_ledger(),
        'production': engine.materials.production_records_are_valid(),
        'consumption': engine.materials.consumption_records_are_valid(),
    }


def authority_checks(engine: SimulationEngine) -> dict[str, bool]:
    """Name each failing authority boundary without swallowing unexpected errors."""
    checks = {}
    for name in ('population', 'location', 'event', 'institution', 'commerce'):
        try:
            getattr(engine, f'validate_{name}_authorities')()
        except (KeyError, TypeError, ValueError):
            checks[name] = False
        else:
            checks[name] = True
    checks.update(engine.outcome_memory.validate())
    return checks


def authoritative_signature(engine: SimulationEngine) -> dict:
    """Complete growth/economic evidence plus owner memories and activity state."""
    return {
        name: getattr(engine, name).to_dict()
        for name in ('growth_proposals', 'town_growth', 'location_growth',
                     'event_ecology', 'institution_growth', 'commerce_growth',
                     'economy', 'materials')
    } | {
        'activity_records': engine.activity_records,
        'locations': [(item.id, item.name, item.description, item.affinities)
                      for item in engine.locations],
        'residents': [(item.id, item.name, item.location_id, item.needs,
                       [memory.to_dict() for memory in item.memory if memory.causal],
                       [memory.to_dict() for memory in item.memory_archive if memory.causal])
                      for item in engine.agents],
    }
