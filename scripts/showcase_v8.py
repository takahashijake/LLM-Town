#!/usr/bin/env python3
"""Generate, inspect and reconstruct the seeded model-free V6 two-branch world."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.causal_inspector import trace
from src.analysis.simulation_inspector import timeline, compare
from src.analysis.v6_freeze_evaluation import MultiBranchProvider, write_config, branch_checks
from src.analysis.procedural_institution_evaluation import _horizon


def write_report(path: Path, report: dict) -> None:
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def demonstrate(root: Path) -> dict:
    """Use real seeded trajectories; assert evidence, replay and branch isolation."""
    root.mkdir(parents=True, exist_ok=True)
    config = write_config(root)
    full = _horizon(root, 'after', config, (180,), MultiBranchProvider())
    _horizon(root, 'before', config, (90,), MultiBranchProvider())
    _horizon(root, 'reconstructed', config, (90, 90), MultiBranchProvider())
    checks = branch_checks(full)
    assert all(checks.values()), checks
    activations = sorted((r for r in full.commerce_growth.activation_records
                          if r.template_id.startswith('generated_')), key=lambda r: r.id)
    assert len(activations) == 2
    final = root / 'after.json'
    reconstructed = root / 'reconstructed.json'
    institution_reports = []
    lot_reports = []
    for number, activation in enumerate(activations, 1):
        institution = trace(final, type='institution', identity=activation.institution_id,
                            depth=2, limit=100, direction='both')
        assert any(e['relationship'] == 'startup_funding' for e in institution['edges'])
        assert any(u['code'] == 'eligibility_witness_not_persisted' for u in institution['unresolved'])
        production = next(r for r in full.materials.production_records if r.recipe_id == activation.recipe_id)
        lot = trace(final, type='lot', identity=production.output_lot_ids[0],
                    depth=5, limit=200, direction='both')
        assert any(e['relationship'] == 'produced_lot' for e in lot['edges'])
        assert institution == trace(reconstructed, type='institution', identity=activation.institution_id,
                                    depth=2, limit=100, direction='both')
        assert lot == trace(reconstructed, type='lot', identity=production.output_lot_ids[0],
                            depth=5, limit=200, direction='both')
        write_report(root / f'institution-{number}.json', institution)
        write_report(root / f'lot-{number}.json', lot)
        institution_reports.append(institution['signature'])
        lot_reports.append(lot['signature'])
    # A damaged copy provides honest missing-evidence behavior, not fake success.
    damaged = json.loads(final.read_text())
    damaged['materials'].pop('lot_movements')
    missing = trace(damaged, type='lot', identity=production.output_lot_ids[0])
    assert not missing['edges'] and missing['unresolved']
    write_report(root / 'unresolved-lot.json', missing)
    write_report(root / 'timeline.json', timeline(final, limit=25))
    write_report(root / 'comparison.json', compare(root / 'before.json', final))
    result = {'schema_version': 1, 'kind': 'v8_showcase', 'seed': 23, 'days': 180,
              'branches': len(activations), 'branch_checks': checks,
              'institution_signatures': institution_reports, 'lot_signatures': lot_reports,
              'reconstruction_equal': True,
              'note': 'Trace equality excludes legacy UUID relationship histories; comparison remains a projection comparison.'}
    write_report(root / 'showcase.json', result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='dedicated directory for generated worlds and reports')
    args = parser.parse_args()
    result = demonstrate(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
