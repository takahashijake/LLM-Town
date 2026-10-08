"""Read-only entry point for typed causal investigation over persisted saves."""
from __future__ import annotations

from pathlib import Path

from src.analysis.causal_evidence import EvidenceGraph, RecordIndex
from src.analysis.causal_materials import add_material_edges, audit_ledger
from src.analysis.causal_growth import add_growth_edges
from src.analysis.causal_commitments import add_commitment_edges
from src.analysis.inspection_save import load_save, check_versions


def build_graph(source: str | Path | dict) -> EvidenceGraph:
    """Index existing records and verify only explicit persisted contracts."""
    save = load_save(source)
    check_versions(save)
    graph = EvidenceGraph(RecordIndex(save))
    ledger_error = audit_ledger(save, graph.index)
    material_error = add_material_edges(graph, save, ledger_error)
    add_growth_edges(graph, save, ledger_error, material_valid=material_error is None)
    add_commitment_edges(graph, material_valid=material_error is None)
    return graph


def trace(source: str | Path | dict, *, type: str, identity: str,
          depth: int = 6, limit: int = 100, direction: str = 'both') -> dict:
    """Return bounded verified dependencies, facts and explicit uncertainty."""
    graph = build_graph(source)
    return graph.investigate(graph.index.root(type, identity), depth=depth,
                             limit=limit, direction=direction)
