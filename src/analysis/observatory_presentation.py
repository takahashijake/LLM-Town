"""Offline document assembly; data never becomes executable HTML or JavaScript."""
from __future__ import annotations

from pathlib import Path

from src.analysis.inspection_save import InspectionError
from src.analysis.observatory import canonical

MAX_HTML_BYTES = 16 * 1024 * 1024
ASSETS = Path(__file__).with_name('observatory_assets')


def render(bundle: dict) -> str:
    """Embed escaped JSON and local source assets; no fetch or external resources."""
    payload = canonical(bundle).decode('ascii').replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (ASSETS / 'report.html').read_text(encoding='utf-8')
    html = template.replace('/* STYLES */', (ASSETS / 'report.css').read_text(encoding='utf-8'))
    html = html.replace('/* APPLICATION */', (ASSETS / 'report.js').read_text(encoding='utf-8'))
    html = html.replace('<!-- DATA -->', payload)
    if len(html.encode('utf-8')) > MAX_HTML_BYTES:
        raise InspectionError('offline report exceeds 16 MiB output budget')
    return html


def write_observatory(source: str | Path | dict, output: Path, *,
                      before: str | Path | dict | None = None,
                      base_location_ids: tuple[str, ...] | None = None,
                      queries: tuple[tuple[str, str], ...] = ()) -> dict:
    """Inspect arbitrary saves without inference, migration or simulation."""
    from src.analysis.observatory import checkpoint, fingerprint
    states = []
    if before is not None:
        states.append(checkpoint(before, label='before', base_location_ids=base_location_ids))
    states.append(checkpoint(source, label='selected', base_location_ids=base_location_ids, queries=queries))
    bundle = {'schema_version': 1, 'kind': 'town_observatory', 'revision': 'inspection_only',
              'scenarios': [{'id': 'inspection', 'title': 'Loaded save · Public inspection',
                  'description': 'Read-only saved facts. This view has no independent simulation replay claim.',
                  'checkpoints': states, 'verification': {'status': 'INSPECTION_ONLY',
                      'note': 'No simulation, transitions or LLM inference were invoked.'}}]}
    bundle['fingerprint'] = fingerprint(bundle)
    html = render(bundle)
    with Path(output).open('x', encoding='utf-8') as handle:
        handle.write(html)
    return {'schema_version': 1, 'kind': 'offline_observatory', 'fingerprint': bundle['fingerprint']}
