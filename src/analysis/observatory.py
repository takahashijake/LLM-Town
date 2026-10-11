"""Bounded public checkpoint projections; never construct or advance a town."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from src.analysis.causal_evidence import COLLECTIONS
from src.analysis.causal_inspector import build_graph
from src.analysis.inspection_records import SOURCES, chronology, safe_fields, safe_identity
from src.analysis.inspection_save import InspectionError, bounded_report, load_save, records

SCHEMA_VERSION = 1
MAX_ROWS = 12_000
MAX_EVENTS = 6_000
MAX_ENTITIES = 1_024
MAX_TRACES = 16
# UUID-bearing social histories are intentionally outside reproducibility reports.
PUBLIC_SOURCES = {k: v for k, v in SOURCES.items()
                  if k not in {'relationship_events', 'reputation_updates'}} | {
    'activities': ('activity_records',),
    'projects': ('collective_projects', 'projects'),
    'contributions': ('collective_projects', 'contributions'),
    'project_effects': ('collective_projects', 'effects'),
}
ENTITY_SOURCES = {
    'resident': ('agents',), 'location': ('location_growth', 'activation_records'),
    'institution': ('institution_growth', 'formation_records'),
    'account': ('economy', 'accounts'), 'employment': ('economy', 'employments'),
    'inventory': ('materials', 'inventories'), 'seller': ('materials', 'sellers'),
    'project': ('collective_projects', 'projects'),
}
METRIC_DEFINITIONS = {
    'population': ('agents', 'Number of unique saved resident IDs.'),
    'active_locations': ('base_location_ids + location_growth.activation_records', 'Explicit configured base IDs plus activated dynamic location IDs; unknown without base registry.'),
    'institutions': ('institution_growth.formation_records', 'Number of activated institution formation records.'),
    'employment': ('economy.employments', 'Active contracts whose start day has arrived.'),
    'currency': ('economy.accounts + economy.initial_balances + economy.ledger', 'Sum of reconciled account balances; unknown when ledger replay fails.'),
    'money_flow': ('economy.ledger', 'Gross sum of ledger transfers, not net income; unknown when replay fails.'),
    'production': ('materials.production_records + materials.lot_movements', 'Reconciled production record count, not output units.'),
    'exchanges': ('materials.exchanges + economy.ledger', 'Reconciled goods/payment exchange count, including procurement and sales.'),
    'activity_executions': ('activity_records', 'Saved activity execution count; association, not proof of success.'),
    'commitments': ('commitments.commitments', 'Saved commitment count; status does not independently prove fulfillment.'),
    'projects': ('collective_projects.projects', 'Saved civic project count.'),
    'contributions': ('collective_projects.contributions + activity_records', 'Work sessions admitted by the V9 causal audit; unknown on contradictory evidence.'),
    'completed_effects': ('collective_projects.effects + V9 causal audit', 'Effects with verified unlocked_learning_activity dependencies.'),
    'workshops': ('activity_records + V9 causal audit', 'Later executions with verified enabled_workshop_execution dependencies.'),
}


def canonical(value: object) -> bytes:
    """Stable JSON, including ASCII escaping for hostile Unicode."""
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')


def fingerprint(value: object) -> str:
    return sha256(canonical(value)).hexdigest()


def _identity(value: object) -> str:
    if not safe_identity(value):
        raise InspectionError('invalid public entity identity')
    return value


def _rows(save: dict, path: tuple[str, ...]) -> list[dict]:
    return records(save, path)


def checkpoint(source: str | Path | dict, *, label: str = 'checkpoint',
               base_location_ids: tuple[str, ...] | None = None,
               queries: tuple[tuple[str, str], ...] = ()) -> dict:
    """Project facts and V8/V9 proofs separately; partial saves remain unknown."""
    _identity(label)
    if len(queries) > MAX_TRACES:
        raise InspectionError('too many causal queries')
    save = load_save(source)
    # Apply a tighter aggregate bound before expensive inherited contract audits.
    paths = set(PUBLIC_SOURCES.values()) | set(ENTITY_SOURCES.values()) | set(COLLECTIONS.values())
    if sum(len(_rows(save, path)) for path in paths) > MAX_ROWS:
        raise InspectionError('observatory exceeds aggregate row budget')
    if 'current_day' in save and (type(save['current_day']) is not int or save['current_day'] < 0):
        raise InspectionError('invalid checkpoint day')
    if 'current_hour' in save and (type(save['current_hour']) is not int or not 0 <= save['current_hour'] <= 23):
        raise InspectionError('invalid checkpoint hour')
    if 'day_complete' in save and type(save['day_complete']) is not bool:
        raise InspectionError('invalid checkpoint completion flag')
    graph = build_graph(save)
    day = save.get('current_day')
    entities = []
    registry: dict[str, set[str]] = {}
    for kind, path in ENTITY_SOURCES.items():
        registry[kind] = set()
        for row in _rows(save, path):
            key = {'location': 'location_id', 'institution': 'institution_id'}.get(kind, 'id')
            identity = _identity(row.get(key))
            if identity in registry[kind]:
                raise InspectionError('duplicate public entity identity')
            registry[kind].add(identity)
            fields = safe_fields(row)
            if kind == 'employment':
                wage = row.get('wage')
                if wage is not None:
                    if type(wage) is not int or wage < 0:
                        raise InspectionError('invalid public wage')
                    fields['wage'] = wage
            if kind == 'resident':
                fields = {'id': identity}
                if row.get('location_id') is not None:
                    fields['location_id'] = _identity(row['location_id'])
            if kind == 'inventory' and 'quantities' in row:
                quantities = row['quantities']
                if not isinstance(quantities, dict) or any(not safe_identity(k) or type(v) is not int or v < 0 for k, v in quantities.items()):
                    raise InspectionError('invalid public inventory quantities')
                fields['quantities'] = dict(sorted(quantities.items()))
            entities.append({'type': kind, 'id': identity, 'source_path': '.'.join(path),
                             'fields': fields, 'evidence': 'persisted_fact'})
    if base_location_ids is not None:
        base = [_identity(v) for v in base_location_ids]
        if len(set(base)) != len(base) or len(base) > MAX_ENTITIES:
            raise InspectionError('invalid base location registry')
        for identity in sorted(base):
            if identity in registry['location']:
                raise InspectionError('contradictory base and dynamic location identity')
            registry['location'].add(identity)
            entities.append({'type': 'location', 'id': identity,
                             'source_path': 'scenario.base_location_ids',
                             'fields': {'id': identity}, 'evidence': 'configured_base_fact'})
    if len(entities) > MAX_ENTITIES:
        raise InspectionError('observatory exceeds entity budget')
    # Check exact public owner references; missing partial sections are uncertainty.
    uncertainties = set()
    reference_rules = {'resident': {'location_id': 'location'},
                       'employment': {'agent_id': 'resident', 'employer_account_id': 'account'},
                       'account': {}, 'inventory': {'account_id': 'account'},
                       'project': {'institution_id': 'institution', 'location_id': 'location'}}
    for entity in entities:
        fields = entity['fields']
        for key, target in reference_rules.get(entity['type'], {}).items():
            value = fields.get(key)
            if value is not None and value not in registry[target]:
                uncertainties.add('missing_' + target + '_reference')
        if entity['type'] in {'account', 'inventory'} and fields.get('owner_type') == 'agent':
            if fields.get('owner_id') not in registry['resident']:
                if 'agents' in save:
                    raise InspectionError('contradictory resident ownership')
                uncertainties.add('missing_resident_reference')
        if entity['type'] in {'account', 'inventory'} and fields.get('owner_type') == 'institution':
            if fields.get('owner_id') not in registry['institution']:
                if 'institution_growth' in save:
                    raise InspectionError('contradictory institution ownership')
                uncertainties.add('missing_institution_reference')
    events = []
    for kind, path in sorted(PUBLIC_SOURCES.items()):
        for ordinal, row in enumerate(_rows(save, path)):
            fields = safe_fields(row)
            if kind == 'activities':
                for key in ('location', 'material_result_id', 'source_plan_id', 'source_plan_step_id',
                            'source_goal_id', 'source_event_occurrence_id', 'source_goal_plan_id'):
                    if row.get(key) is not None:
                        fields[key] = _identity(row[key])
            if kind == 'activities':
                if fields.get('agent_id') not in registry['resident']:
                    uncertainties.add('missing_resident_reference')
                if fields.get('location') not in registry['location']:
                    uncertainties.add('missing_location_reference')
            event_day, hour = chronology(fields)
            # Preserve persisted sequence and source ordinal; never sort histories before auditing.
            events.append({'id': f'{kind}:{ordinal:06d}', 'source': kind,
                           'source_path': '.'.join(path) + f'[{ordinal}]',
                           'authority_id': fields.get('id'), 'day': event_day, 'hour': hour,
                           'fields': fields, 'evidence': 'authoritative_association'})
    if len(events) > MAX_EVENTS:
        raise InspectionError('observatory exceeds event budget')
    events.sort(key=lambda e: (e['day'] if e['day'] is not None else -1,
                              e['hour'] if e['hour'] is not None else -1,
                              e['source'], e['id']))
    ledger_error = graph.audit_errors['ledger']
    material_error = graph.audit_errors['materials']
    # Reconciliation proves holdings, while reciprocal V8 edges prove exchanges.
    paid = {e.effect for e in graph.edges if e.relationship == 'payment_leg'}
    delivered = {e.cause for e in graph.edges if e.relationship == 'goods_leg'}
    exchange_valid = all(ref in paid and ref in delivered
                         for ref in graph.index.of_type('exchange'))
    produced = {e.cause for e in graph.edges if e.relationship == 'produced_lot'}
    production_valid = all(ref in produced for ref in graph.index.of_type('production'))
    if not production_valid:
        uncertainties.add('production_contract_unresolved')
    if not exchange_valid:
        uncertainties.add('exchange_contract_unresolved')
    civic_refs = graph.index.of_type('project')
    civic_valid = graph.project_authority_valid is True and all(ref in graph.project_audits for ref in civic_refs)
    if 'collective_projects' in save and not civic_valid:
        uncertainties.add('project_contract_unresolved')
    employments = _rows(save, ENTITY_SOURCES['employment'])
    employment_valid = day is not None and all(
        type(r.get('active')) is bool and type(r.get('start_day')) is int
        and r['start_day'] >= 0 and r.get('agent_id') in registry['resident']
        and r.get('employer_account_id') in registry['account'] for r in employments)
    if employments and not employment_valid:
        uncertainties.add('employment_contract_unresolved')
    location_rows = _rows(save, ENTITY_SOURCES['location'])
    location_valid = all(r.get('status') == 'activated' for r in location_rows)
    if not location_valid:
        uncertainties.add('location_activation_unresolved')
    values = {
        'population': len(registry['resident']) if 'agents' in save else None,
        'active_locations': len(registry['location']) if base_location_ids is not None and location_valid else None,
        'institutions': sum(r.get('status') == 'activated' for r in _rows(save, ENTITY_SOURCES['institution'])) if 'institution_growth' in save else None,
        'employment': sum(r.get('active') is True and type(r.get('start_day')) is int and day is not None and r['start_day'] <= day for r in _rows(save, ENTITY_SOURCES['employment'])) if 'economy' in save and employment_valid else None,
        'currency': sum(r['balance'] for r in _rows(save, ENTITY_SOURCES['account'])) if ledger_error is None else None,
        'money_flow': sum(r['amount'] for r in _rows(save, PUBLIC_SOURCES['ledger'])) if ledger_error is None else None,
        'production': len(_rows(save, PUBLIC_SOURCES['production'])) if material_error is None and production_valid else None,
        'exchanges': len(_rows(save, PUBLIC_SOURCES['exchanges'])) if material_error is None and ledger_error is None and exchange_valid else None,
        'activity_executions': len(_rows(save, ('activity_records',))) if 'activity_records' in save else None,
        'commitments': len(_rows(save, PUBLIC_SOURCES['commitments'])) if 'commitments' in save else None,
        'projects': len(civic_refs) if 'collective_projects' in save else None,
        'contributions': len(graph.index.of_type('contribution')) if civic_valid else None,
        'completed_effects': sum(e.relationship == 'unlocked_learning_activity' for e in graph.edges) if civic_valid else None,
        'workshops': sum(e.relationship == 'enabled_workshop_execution' for e in graph.edges) if civic_valid else None,
    }
    if ledger_error:
        uncertainties.add(ledger_error)
    if material_error:
        uncertainties.add(material_error)
    traces = [graph.investigate(graph.index.root(kind, identity), depth=6, limit=150)
              for kind, identity in queries]
    result = {'schema_version': SCHEMA_VERSION, 'kind': 'town_checkpoint', 'label': label,
              'day': day, 'hour': save.get('current_hour'), 'day_complete': save.get('day_complete'),
              'metrics': {key: {'value': values[key], 'source': source_path, 'definition': definition}
                          for key, (source_path, definition) in sorted(METRIC_DEFINITIONS.items())},
              'entities': sorted(entities, key=lambda e: (e['type'], e['id'])),
              'events': events, 'traces': traces, 'uncertainties': sorted(uncertainties),
              'ordering_note': 'Same-tick presentation order is stable; only verified dependency edges establish causality.',
              'privacy': 'Private memories, beliefs, journals, prompts, prose and UUID social histories excluded.'}
    result['signature'] = fingerprint(result)
    return bounded_report(result)


def compare_checkpoints(left: dict, right: dict) -> dict:
    """State differences never explain causes; absent values are unknown."""
    for report in (left, right):
        if report.get('kind') != 'town_checkpoint' or report.get('schema_version') != SCHEMA_VERSION:
            raise InspectionError('unsupported observatory checkpoint')
    metrics = {}
    for key in sorted(METRIC_DEFINITIONS):
        a, b = left['metrics'][key]['value'], right['metrics'][key]['value']
        metrics[key] = {'before': a, 'after': b, 'delta': b - a if a is not None and b is not None else None}
    def keyed(report: dict) -> dict:
        return {(e['type'], e['id']): e for e in report['entities']}
    a, b = keyed(left), keyed(right)
    return bounded_report({'schema_version': 1, 'kind': 'checkpoint_comparison',
        'before': left['label'], 'after': right['label'], 'metrics': metrics,
        'added': [b[k] for k in sorted(b.keys() - a.keys())],
        'removed': [a[k] for k in sorted(a.keys() - b.keys())],
        'changed': [{'before': a[k], 'after': b[k]} for k in sorted(a.keys() & b.keys()) if a[k] != b[k]],
        'note': 'Differences describe saved state; causes require separate verified dependency evidence.'})
