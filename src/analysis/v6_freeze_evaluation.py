"""Integrated bounded V6 release gate using two real procedural branches."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from unittest.mock import patch
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from src.simulation.engine import SimulationEngine

from src.analysis.procedural_commerce_evaluation import (
    StaticProceduralCommerceProvider, _write_config as _commerce_config,
)
from src.analysis.procedural_institution_evaluation import _engine, _run, _horizon
from src.analysis.growth_audits import (
    authoritative_signature, authority_checks, conservation_checks,
)
from src.systems.growth_proposals import GrowthProposalSystem, payload_digest
from src.systems.materials import MaterialError

HORIZON_DAYS = 180
KINDS = ('resident', 'location', 'event', 'institution', 'commerce')


class MultiBranchProvider(StaticProceduralCommerceProvider):
    """Only semantic proposals; the target comes exclusively from the engine."""
    provider_kind = 'deterministic_multi_branch'

    def propose_resident(self, context: dict) -> dict:
        row = super().propose_resident(context)
        row['name'] = ('Mira', 'Mina')[self.calls['resident'] - 1]
        return row

    def propose_location(self, context: dict) -> dict:
        row = super().propose_location(context)
        row['name'] = ('Story Grove', 'Story Glade')[self.calls['location'] - 1]
        return row

    def propose_event(self, context: dict) -> dict:
        row = super().propose_event(context)
        row['name'] = ('Story Exchange', 'Story Circle')[self.calls['event'] - 1]
        return row

    def propose_institution(self, context: dict) -> dict:
        row = dict(super().propose_institution(context))
        suffix = ('Grove', 'Glade')[self.calls['institution'] - 1]
        row.update(name=f'Story {suffix} Commons', role_title=f'{suffix} coordinator',
                   work_activity_name=f'Coordinate {suffix} programs')
        return row


class ReplayGuard:
    """Count calls as well as throwing: proposal review records provider failures."""
    provider_kind = 'no_historical_replay'

    def __init__(self) -> None:
        self.calls = 0

    def __getattr__(self, name: str) -> Callable[[dict], object]:
        if not name.startswith('propose_'):
            raise AttributeError(name)
        def fail(_context):
            self.calls += 1
            raise AssertionError('historical model replay')
        return fail


def write_config(root: Path) -> Path:
    path = _commerce_config(root)
    data = json.loads(path.read_text())
    data['policy']['resident_capacity'] = 8
    data['location_growth']['policy']['location_capacity'] = 8
    data['institution_growth']['policy']['institution_capacity'] = 4
    data['commerce_growth']['policy']['commerce_capacity'] = 3
    for kind in KINDS:
        data['procedural_growth']['policy'][kind + '_proposal_capacity'] = 2
    data['procedural_growth']['policy']['history_limit'] = 10
    path.write_text(json.dumps(data))
    return path


def boundary_days(engine: SimulationEngine) -> dict[str, int]:
    """Derive checkpoints from records, never from assumed fixture dates."""
    days = {'before_first_admission': 0}
    for row in engine.growth_proposals.records:
        days[f'{row.generated_template_id}:admission'] = row.admission_day
        days[f'{row.generated_template_id}:before_admission'] = row.admission_day - 1
    for name, records in (
        ('location', engine.location_growth.activation_records),
        ('institution', engine.institution_growth.formation_records),
        ('commerce', engine.commerce_growth.activation_records),
    ):
        for row in records:
            if row.template_id.startswith('generated_') and row.status == 'activated':
                days[f'{name}:{row.id}:activation'] = row.activation_day
                days[f'{name}:{row.id}:before_activation'] = row.activation_day - 1
    for template in engine.growth_proposals.event_templates.values():
        occurrences = [row.day for row in engine.event_ecology.occurrence_history
                       if row.template_id == template.id]
        if occurrences:
            days[f'{template.id}:occurrence'] = min(occurrences)
    for row in engine.commerce_growth.activation_records:
        if not row.template_id.startswith('generated_'):
            continue
        groups = {
            'procurement': [item.day for item in engine.materials.exchanges
                            if item.buyer_inventory_id == row.inventory_id],
            'production': [item.day for item in engine.materials.production_records
                           if item.recipe_id == row.recipe_id],
            'revenue': [item.day for item in engine.materials.exchanges
                        if item.seller_id == row.seller_id],
        }
        for label, dates in groups.items():
            if dates:
                days[f'{row.template_id}:{label}'] = min(dates)
    return days


def branch_checks(engine: SimulationEngine) -> dict[str, bool]:
    checks = {}
    activations = [row for row in engine.commerce_growth.activation_records
                   if row.template_id.startswith('generated_') and row.status == 'activated']
    checks['two_commerce_branches'] = len(activations) == 2
    for field in ('institution_id', 'location_id', 'operator_agent_id',
                  'operator_employment_id', 'institution_account_id', 'inventory_id',
                  'seller_id', 'recipe_id', 'purchase_activity_id'):
        checks[f'independent_{field}'] = len({getattr(row, field) for row in activations}) == 2
    for activation in activations:
        label = activation.template_id
        template = engine.growth_proposals.commerce_templates[label]
        formation = next(row for row in engine.institution_growth.formation_records
                         if row.id == activation.institution_formation_id)
        institution = engine.growth_proposals.institution_templates[formation.template_id]
        admissions = {row.generated_template_id: row.admission_day
                      for row in engine.growth_proposals.records}
        checks[f'{label}:later_activation'] = activation.review_day > admissions[label]
        checks[f'{label}:later_formation'] = formation.review_day > admissions[institution.id]
        checks[f'{label}:local_events'] = all(
            engine.growth_proposals.event_templates[key].location_template_id
            == template.location_template_id
            for key in institution.relevant_dynamic_event_template_ids)
        recipe = engine.materials.production_recipes[activation.recipe_id]
        checks[f'{label}:exact_operator'] = (
            recipe.eligible_actor_ids == (formation.employee_agent_id,)
            and recipe.eligible_employment_ids == (formation.employment_id,))
        procurement = [row for row in engine.materials.exchanges
                       if row.buyer_inventory_id == activation.inventory_id]
        produced = [row for row in engine.materials.production_records
                    if row.recipe_id == activation.recipe_id]
        sales = [row for row in engine.materials.exchanges if row.seller_id == activation.seller_id]
        input_lots = {key for row in procurement
                      for key in engine.materials.lot_ids_moved_by_transfer(row.inventory_transfer_id)}
        checks[f'{label}:procurement'] = bool(procurement) and all(
            row.seller_id == 'seller:market_stall' for row in procurement)
        checks[f'{label}:production_lineage'] = bool(produced) and all(
            set(row.input_lot_ids).issubset(input_lots)
            and all(engine.materials.lots[key].parent_lot_ids == row.input_lot_ids
                    for key in row.output_lot_ids) for row in produced)
        ledger = {row.id: row for row in engine.economy.ledger}
        checks[f'{label}:sales_revenue'] = bool(sales) and all(
            ledger[row.monetary_transaction_id].destination_account_id
            == formation.employer_account_id for row in sales)
        checks[f'{label}:wages'] = any(row.event_key.startswith(f'wage:{formation.employment_id}:')
                                    for row in engine.economy.ledger)
        checks[f'{label}:local_work'] = all(
            row['location'] == activation.location_id
            and row['agent_id'] == activation.operator_agent_id
            for row in engine.activity_records
            if row.get('activity_id') == template.production_activity_id)
    checks['garden_commerce_remains_configured'] = any(
        row.template_id == 'commerce_template_001' and row.status == 'activated'
        for row in engine.commerce_growth.activation_records)
    checks['pavilion_not_granted_commerce'] = all(
        row.institution_template_id != 'institution_template_002'
        for row in engine.commerce_growth.templates.values())
    return checks


def corruption_cases(saved: dict) -> dict[str, tuple[tuple, object, str]]:
    """Generate field-shape attacks from the actual persisted schemas."""
    cases = {}
    groups = {
        'growth_proposals': ('records', 'resident_templates', 'location_templates',
                             'event_templates', 'institution_templates', 'commerce_templates'),
        'town_growth': ('migration_records', 'review_history'),
        'location_growth': ('activation_records', 'review_history'),
        'event_ecology': ('occurrence_history',),
        'institution_growth': ('formation_records', 'review_history'),
        'commerce_growth': ('activation_records', 'review_history'),
    }
    for system, collections in groups.items():
        for collection in collections:
            rows = saved[system][collection]
            if not rows:
                continue
            # Exercise each kind of proposal, not only the first resident row.
            indices = range(len(rows)) if collection == 'records' else (0,)
            for index in indices:
                row = rows[index]
                for field, value in row.items():
                    path = (system, collection, index, field)
                    label = f'{system}.{collection}.{index}.{field}'
                    cases[label + ':missing'] = (path, None, 'delete')
                    bad = {} if isinstance(value, list) else []
                    if isinstance(value, int):
                        bad = True if not isinstance(value, bool) else 'invalid'
                    cases[label + ':type'] = (path, bad, 'set')
                cases[f'{system}.{collection}.{index}:extra'] = (
                    (system, collection, index, 'forged_authority'), 'authority', 'set')
                cases[f'{system}.{collection}.{index}:duplicate'] = (
                    (system, collection), deepcopy(row), 'append')
    for system in groups:
        cases[f'{system}:future_schema'] = ((system, 'schema_version'), 999, 'set')
        cases[f'{system}:boolean_schema'] = ((system, 'schema_version'), True, 'set')
        for key in saved[system]:
            if key.startswith('next_'):
                for label, value in (('rollback', 1), ('jump', saved[system][key] + 20)):
                    cases[f'{system}.{key}:{label}'] = ((system, key), value, 'set')
    # Swap valid authority from branch B into branch A at every layer.
    for system, collection, selector, fields in (
        ('growth_proposals', 'event_templates', None, ('location_template_id',)),
        ('growth_proposals', 'institution_templates', None,
         ('location_template_id', 'relevant_dynamic_event_template_ids', 'role')),
        ('growth_proposals', 'commerce_templates', None,
         ('institution_template_id', 'location_template_id', 'production_activity_id',
          'purchase_activity_id', 'recipe_id_suffix')),
        ('location_growth', 'activation_records', 'template_id', ('template_id', 'location_id')),
        ('institution_growth', 'formation_records', 'template_id',
         ('template_id', 'location_activation_id', 'location_id', 'employee_agent_id',
          'employment_id', 'employer_account_id', 'role_template_id')),
        ('commerce_growth', 'activation_records', 'template_id',
         ('template_id', 'institution_formation_id', 'location_activation_id', 'location_id',
          'operator_agent_id', 'operator_employment_id', 'institution_account_id',
          'inventory_id', 'seller_id', 'recipe_id', 'purchase_activity_id')),
        ('materials', 'inventories', 'commerce_activation_id', ('owner_id', 'account_id', 'commerce_activation_id')),
        ('materials', 'sellers', 'commerce_activation_id',
         ('inventory_id', 'account_id', 'location_id', 'operator_employment_id', 'commerce_activation_id')),
        ('materials', 'production_recipes', 'commerce_activation_id',
         ('output_inventory_id', 'activity_id', 'required_location_id',
          'eligible_actor_ids', 'eligible_employment_ids', 'commerce_activation_id')),
        ('materials', 'purchase_activity_rules', 'commerce_activation_id', ('activity_id', 'seller_id', 'commerce_activation_id')),
    ):
        rows = saved[system][collection]
        indices = [index for index, row in enumerate(rows)
                   if selector is None or (str(row.get(selector, '')).startswith('generated_')
                                           if selector == 'template_id' else row.get(selector))]
        if len(indices) < 2:
            continue
        a, b = indices[:2]
        for field in fields:
            cases[f'cross_branch:{system}.{collection}.{field}'] = (
                (system, collection, a, field), deepcopy(rows[b][field]), 'set')
    for kind in ('event', 'institution', 'commerce'):
        rows = [(index, row) for index, row in enumerate(saved['growth_proposals']['records'])
                if row['kind'] == kind]
        for field in ('target_location_template_id', 'generated_template_id', 'canonical_payload_hash'):
            if rows[0][1][field] != rows[1][1][field]:
                cases[f'cross_branch:proposal:{kind}:{field}'] = (
                    ('growth_proposals', 'records', rows[0][0], field), rows[1][1][field], 'set')
        if kind == 'commerce':
            cases['cross_branch:proposal:commerce:institution'] = (
                ('growth_proposals', 'records', rows[0][0], 'target_institution_template_id'),
                rows[1][1]['target_institution_template_id'], 'set')
    return cases


def mutate_path(data: dict, case: tuple) -> None:
    path, value, operation = case
    parent = data
    for key in path[:-1]:
        parent = parent[key]
    if operation == 'delete':
        del parent[path[-1]]
    elif operation == 'append':
        parent[path[-1]].append(value)
    else:
        parent[path[-1]] = value


def memory_corruption_cases(saved: dict) -> dict:
    """Recompute stable IDs so rejection cannot rely on an obvious ID mismatch."""
    cases = {}
    for source in ('town_growth', 'location_growth', 'institution_growth', 'commerce_growth'):
        rows = [(agent_index, collection, index, row)
                for agent_index, agent in enumerate(saved['agents'])
                for collection in ('memory', 'memory_archive')
                for index, row in enumerate(agent[collection])
                if row.get('source_system') == source and row.get('causal')]
        if not rows:
            continue
        agent_index, collection, index, original = rows[0]
        path = ('agents', agent_index, collection, index)
        variants = {
            'wrong_system': ('source_system', 'dialogue'),
            'nonexistent_source': ('source_id', 'authority:missing'),
            'similar_name_source': ('source_id', 'Story Glade Commons'),
            'future_authority': ('day', 1),
            'wrong_branch_location': ('location', 'library'),
            'wrong_owner_container': ('owner_id', saved['agents'][-1]['id']),
        }
        other = next((row for _, _, _, row in rows
                      if row['source_id'] != original['source_id']), None)
        if other and source != 'town_growth':
            variants['valid_wrong_branch_source'] = ('source_id', other['source_id'])
        for label, (field, value) in variants.items():
            forged = dict(original)
            forged[field] = value
            forged['id'] = (f"memory:{forged['owner_id']}:{forged['source_system']}:"
                            f"{forged['source_id']}:{forged['event_type']}")
            cases[f'memory:{source}:{label}'] = (path, forged, 'set')
    # Private employment/operator memories cannot be projected to another owner.
    for event in ('employment_started', 'commerce_operator_authorized'):
        for agent_index, agent in enumerate(saved['agents']):
            for collection in ('memory', 'memory_archive'):
                for index, row in enumerate(agent[collection]):
                    if row.get('event_type') != event:
                        continue
                    other = (agent_index + 1) % len(saved['agents'])
                    forged = dict(row, owner_id=saved['agents'][other]['id'])
                    forged['id'] = (f"memory:{forged['owner_id']}:{forged['source_system']}:"
                                    f"{forged['source_id']}:{event}")
                    cases[f'memory:private:{event}'] = (
                        ('agents', other, 'memory'), forged, 'append')
                    break
    return cases


def boundary_corruption_cases(saved: dict) -> dict:
    cases = {}
    admissions = {row['generated_template_id']: row['admission_day']
                  for row in saved['growth_proposals']['records']}
    for system, collection in (
        ('town_growth', 'migration_records'), ('location_growth', 'activation_records'),
        ('institution_growth', 'formation_records'), ('commerce_growth', 'activation_records'),
    ):
        for index, row in enumerate(saved[system][collection]):
            if row['template_id'].startswith('generated_'):
                cases[f'ordering:{system}:admission_day'] = (
                    (system, collection, index, 'review_day'), admissions[row['template_id']], 'set')
                break
    events = saved['growth_proposals']['event_templates']
    if len(events) == 2:
        index = next(i for i, row in enumerate(saved['event_ecology']['occurrence_history'])
                     if row['template_id'] == events[0]['id'])
        original = saved['event_ecology']['occurrence_history'][index]
        forged = dict(original, template_id=events[1]['id'])
        forged['occurrence_id'] = (f"daily-event:{forged['day']}:"
                                  f"{forged['template_id']}:{forged['location_id']}")
        cases['cross_branch:coherent_occurrence_identity'] = (
            ('event_ecology', 'occurrence_history', index), forged, 'set')
    # Even a coherently rebound template and proposal must replay the real target selection.
    records = saved['growth_proposals']['records']
    commerce_indices = [i for i, row in enumerate(records) if row['kind'] == 'commerce']
    a, b = commerce_indices
    forged = deepcopy(saved['growth_proposals'])
    forged['records'][a]['target_institution_template_id'] = records[b]['target_institution_template_id']
    forged['records'][a]['target_location_template_id'] = records[b]['target_location_template_id']
    for field in ('institution_template_id', 'location_template_id', 'production_activity_id'):
        forged['commerce_templates'][0][field] = forged['commerce_templates'][1][field]
    cases['cross_branch:coherent_commerce_parent'] = (('growth_proposals',), forged, 'set')
    forged = deepcopy(saved['growth_proposals'])
    forged['records'][a]['canonical_payload'] = {'offer': 'arbitrary_goods'}
    forged['records'][a]['canonical_payload_hash'] = payload_digest({'offer': 'arbitrary_goods'})
    cases['proposal:invalid_offer_matching_digest'] = (('growth_proposals',), forged, 'set')
    for kind in KINDS:
        index = next(i for i, row in enumerate(records) if row['kind'] == kind)
        for field, value in (('status', 'invented'), ('kind', 'government'),
                             ('canonical_payload_hash', '0' * 64)):
            cases[f'proposal:{kind}:invalid_{field}'] = (
                ('growth_proposals', 'records', index, field), value, 'set')
        collection = kind + '_templates'
        cases[f'{kind}:admitted_without_template'] = (
            ('growth_proposals', collection), [], 'set')
    return cases


def legacy_checks(root: Path, config: Path, engine: SimulationEngine) -> dict[str, bool]:
    """Use genuine admission prefixes; migrations only add null/empty structure."""
    results = {}
    modern = engine.growth_proposals.to_dict()
    config_data = json.loads(config.read_text())
    def restore(state):
        return GrowthProposalSystem.from_config(
            config_data, agents=engine.agents,
            locations=[row for row in engine.locations
                       if row.id in engine.location_growth.base_location_ids], state=state,
            provider=ReplayGuard())
    for version, kinds in ((1, KINDS[:2]), (2, KINDS[:3]), (3, KINDS[:4])):
        legacy = deepcopy(modern)
        legacy['schema_version'] = version
        cutoff = next(i for i, row in enumerate(modern['records']) if row['kind'] not in kinds)
        legacy['records'] = legacy['records'][:cutoff]
        admitted = {row['generated_template_id'] for row in legacy['records']}
        for kind in KINDS:
            collection = kind + '_templates'
            counter = f'next_{kind}_template_sequence'
            if kind not in kinds:
                legacy.pop(collection)
                legacy.pop(counter)
            else:
                legacy[collection] = [row for row in legacy[collection] if row['id'] in admitted]
                legacy[counter] = len(legacy[collection]) + 1
        for row in legacy['records']:
            row.pop('target_institution_template_id')
            if version == 1:
                row.pop('target_location_template_id')
        legacy['next_proposal_sequence'] = len(legacy['records']) + 1
        legacy['last_attempt_day'] = legacy['records'][-1]['proposal_day']
        original = deepcopy(legacy)
        restored = restore(legacy).to_dict()
        results[f'legacy_v{version}:valid_empty_migration'] = (
            legacy == original
            and all(restored[kind + '_templates'] == [] for kind in KINDS if kind not in kinds)
            and all(all(migrated[key] == value for key, value in prior.items())
                    for prior, migrated in zip(original['records'], restored['records'])))
        for field in set(modern) - set(legacy):
            attacked = deepcopy(legacy)
            attacked[field] = modern[field]
            try:
                restore(attacked)
            except (KeyError, TypeError, ValueError):
                results[f'legacy_v{version}:reject_{field}'] = True
            else:
                results[f'legacy_v{version}:reject_{field}'] = False
        for field in set(modern['records'][0]) - set(legacy['records'][0]):
            attacked = deepcopy(legacy)
            attacked['records'][0][field] = None
            try:
                restore(attacked)
            except (KeyError, TypeError, ValueError):
                results[f'legacy_v{version}:reject_record_{field}'] = True
            else:
                results[f'legacy_v{version}:reject_record_{field}'] = False
    return results


def atomic_checks(root: Path, config: Path, fresh: SimulationEngine) -> dict[str, bool]:
    """Inject after real mutations in branch B while preserving branch A."""
    results = {}
    formations = [row for row in fresh.institution_growth.formation_records
                  if row.template_id.startswith('generated_')]
    commerce = [row for row in fresh.commerce_growth.activation_records
                if row.template_id.startswith('generated_')]
    if len(formations) != 2 or len(commerce) != 2:
        return {'atomic_fixture_has_two_branches': False}
    def checkpoint(day):
        (root / 'atomic.json').write_text((root / f'checkpoint-{day}.json').read_text())
        return _engine(root, 'atomic', config, ReplayGuard(), load=True)
    def snapshot(engine):
        return deepcopy({
            'economy': engine.economy.to_dict(), 'materials': engine.materials.to_dict(),
            'memories': [[row.to_dict() for row in agent.memory + agent.memory_archive]
                         for agent in engine.agents],
        })
    def fail_after(original):
        def failing(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('injected after authoritative mutation')
        return failing
    for domain, record, stages, review in (
        ('institution', formations[1],
         (('economy', 'register_employer_account'), ('economy', 'register_employment'),
          ('economy', 'transfer'), ('outcome_memory', 'project')),
         'review_institution_growth'),
        ('commerce', commerce[1],
         (('materials', 'register_institution_inventory'), ('materials', 'register_seller'),
          ('materials', 'register_purchase_activity_rule'), ('materials', 'register_production_recipe'),
          ('outcome_memory', 'project')),
         'review_commerce_growth'),
    ):
        for system, method in stages:
            engine = checkpoint(record.activation_day - 1)
            before = snapshot(engine)
            target = getattr(engine, system)
            with patch.object(target, method, side_effect=fail_after(getattr(target, method))) as injected:
                getattr(engine, review)(record.activation_day)
            records = (engine.institution_growth.formation_records if domain == 'institution'
                       else engine.commerce_growth.activation_records)
            rejected = any(row.template_id == record.template_id and row.status == 'rejected'
                           for row in records)
            results[f'atomic:{domain}:{method}'] = (
                injected.call_count > 0 and rejected and before == snapshot(engine)
                and all(conservation_checks(engine).values()))
    engine = checkpoint(commerce[1].activation_day)
    activation = next(row for row in engine.commerce_growth.activation_records
                      if row.template_id == commerce[1].template_id)
    template = engine.growth_proposals.commerce_templates[activation.template_id]
    procurement = dict(
        buyer_inventory_id=activation.inventory_id,
        buyer_account_id=activation.institution_account_id,
        seller_id=template.upstream_seller_id, good_id=template.input_good_id,
        quantity=template.input_quantity, day=activation.activation_day + 1,
        hour=8, event_key='freeze:procurement')
    production = dict(
        recipe_id=activation.recipe_id, actor_id=activation.operator_agent_id,
        employment_id=activation.operator_employment_id,
        inventory_id=activation.inventory_id, day=activation.activation_day + 1,
        hour=8, activity_id=template.production_activity_id,
        location_id=activation.location_id, event_key='freeze:production')
    buyer = next(agent for agent in engine.agents
                 if engine.economy.account_for_agent(agent.id).balance >=
                 engine.materials.price_for_good(template.output_good_id))
    purchase = dict(
        buyer_inventory_id=engine.materials.inventory_for_agent(buyer.id).id,
        buyer_account_id=engine.economy.account_for_agent(buyer.id).id,
        seller_id=activation.seller_id, good_id=template.output_good_id, quantity=1,
        day=activation.activation_day + 1, hour=8, event_key='freeze:sale')
    for label, method, arguments in (
        ('procurement', 'purchase', procurement), ('production', 'produce', production),
        ('purchase', 'purchase', purchase),
    ):
        before = snapshot(engine)
        original = engine.materials._move_allocations
        raised = False
        with patch.object(engine.materials, '_move_allocations', side_effect=fail_after(original)) as injected:
            try:
                getattr(engine.materials, method)(**arguments)
            except RuntimeError:
                raised = True
        results[f'atomic:{label}:lot_commit'] = (
            raised and injected.call_count > 0 and before == snapshot(engine))
        getattr(engine.materials, method)(**arguments)
        after = snapshot(engine)
        try:
            getattr(engine.materials, method)(**arguments)
        except MaterialError as error:
            duplicate = error.code == 'duplicate_event'
        else:
            duplicate = False
        # Rejection diagnostics may grow, but authority may not.
        current = snapshot(engine)
        after['materials'].pop('rejected_operations')
        current['materials'].pop('rejected_operations')
        results[f'replay:{label}:once'] = duplicate and after == current
        results[f'atomic:{label}:conservation'] = all(conservation_checks(engine).values())
    return results


def evaluate_v6_freeze(*, comprehensive: bool = False) -> dict:
    """Fast gate resumes at every boundary; comprehensive also forks each save."""
    scenarios = {}
    checkpoints = {}
    mutations = {}
    with TemporaryDirectory() as directory:
        root = Path(directory)
        config = write_config(root)
        provider = MultiBranchProvider()
        fresh = _horizon(root, 'fresh', config, (HORIZON_DAYS,), provider)
        scenarios.update(branch_checks(fresh))
        invariants = conservation_checks(fresh) | authority_checks(fresh)
        repeat = _horizon(root, 'repeat', config, (HORIZON_DAYS,), MultiBranchProvider())
        signature = deepcopy(authoritative_signature(fresh))
        scenarios['uninterrupted_determinism'] = signature == authoritative_signature(repeat)
        boundaries = boundary_days(fresh)
        days = sorted({day for day in boundaries.values() if 0 < day < HORIZON_DAYS})
        resumed_provider = MultiBranchProvider()
        # An independently run trajectory saves and reloads at ALL boundaries.
        random_state = random.getstate()
        random.seed(23)
        try:
            resumed = _engine(root, 'resumed', config, resumed_provider)
            initial = deepcopy(authoritative_signature(resumed))
            resumed.state.save(resumed, 0, 8, day_complete=True)
            guard = ReplayGuard()
            initial_loaded = _engine(root, 'resumed', config, guard, load=True)
            checkpoints['0'] = initial == authoritative_signature(initial_loaded) and guard.calls == 0
            previous = 0
            for day in days:
                _run(resumed, day - previous)
                (root / f'checkpoint-{day}.json').write_text((root / 'resumed.json').read_text())
                before = deepcopy(authoritative_signature(resumed))
                guard = ReplayGuard()
                loaded = _engine(root, 'resumed', config, guard, load=True)
                checks = conservation_checks(loaded) | authority_checks(loaded)
                checkpoints[str(day)] = (before == authoritative_signature(loaded)
                                         and guard.calls == 0 and all(checks.values()))
                if comprehensive:
                    # Future proposals are allowed; only reconstruction is guarded.
                    fork_provider = MultiBranchProvider()
                    fork_provider.calls = dict(resumed_provider.calls)
                    (root / 'fork.json').write_text((root / 'resumed.json').read_text())
                    fork_random_state = random.getstate()
                    try:
                        loaded = _engine(root, 'fork', config, fork_provider, load=True)
                        _run(loaded, HORIZON_DAYS - day)
                        checkpoints[f'{day}:independent_convergence'] = (
                            signature == authoritative_signature(loaded))
                    finally:
                        random.setstate(fork_random_state)
                resumed = _engine(root, 'resumed', config, resumed_provider, load=True)
                previous = day
            _run(resumed, HORIZON_DAYS - previous)
        finally:
            random.setstate(random_state)
        scenarios['multi_checkpoint_convergence'] = signature == authoritative_signature(resumed)
        scenarios['exactly_two_attempts_per_kind'] = provider.calls == resumed_provider.calls == {
            kind: 2 for kind in KINDS}
        saved = json.loads((root / 'fresh.json').read_text())
        # Journals and noncausal UUID memories carry no authority. Excluding
        # those texts keeps hundreds of real-engine corruption loads practical;
        # all causal memories, residents and authoritative records are retained.
        for agent in saved['agents']:
            agent['daily_journals'] = []
            agent['memory_summary'] = ''
            for collection in ('memory', 'memory_archive'):
                agent[collection] = [row for row in agent[collection] if row.get('causal')]
        (root / 'control.json').write_text(json.dumps(saved))
        control_guard = ReplayGuard()
        control = _engine(root, 'control', config, control_guard, load=True)
        scenarios['corruption_control_preserves_authority'] = (
            all((authority_checks(control) | conservation_checks(control)).values())
            and control_guard.calls == 0)
        cases = corruption_cases(saved)
        cases.update(memory_corruption_cases(saved))
        for system in ('economy', 'materials'):
            for label, version in (('future', 999), ('boolean', True), ('float', float(saved[system]['schema_version']))):
                cases[f'{system}:schema:{label}'] = ((system, 'schema_version'), version, 'set')
            for field, value in saved[system].items():
                if field.startswith('next_'):
                    for label, replacement in (('rollback', 1), ('jump', value + 20),
                                                ('boolean', True), ('float', float(value))):
                        cases[f'{system}:{field}:{label}'] = ((system, field), replacement, 'set')
        cases.update(boundary_corruption_cases(saved))
        for system in ('growth_proposals', 'town_growth', 'location_growth', 'event_ecology',
                       'institution_growth', 'commerce_growth', 'materials'):
            cases[f'missing_parent:{system}'] = ((system,), None, 'delete')
        for label, case in cases.items():
            data = deepcopy(saved)
            mutate_path(data, case)
            path = root / 'attack.json'
            path.write_text(json.dumps(data))
            guard = ReplayGuard()
            try:
                _engine(root, 'attack', config, guard, load=True)
            except (KeyError, TypeError, ValueError):
                mutations[label] = guard.calls == 0
            else:
                mutations[label] = False
        migration_checks = legacy_checks(root, config, fresh)
        scenarios.update(migration_checks)
        scenarios.update(atomic_checks(root, config, fresh))
        # Reviews of persisted days must remain inert, including money/memories.
        guard = ReplayGuard()
        replayed = _engine(root, 'fresh', config, guard, load=True)
        before = deepcopy(authoritative_signature(replayed))
        for day in sorted({row.admission_day for row in replayed.growth_proposals.records}):
            replayed.review_growth_proposals(day)
        for system_name, method in (
            ('town_growth', 'review_town_growth'), ('location_growth', 'review_location_growth'),
            ('institution_growth', 'review_institution_growth'), ('commerce_growth', 'review_commerce_growth'),
        ):
            reviews = list(getattr(replayed, system_name).review_history)
            for row in reviews:
                getattr(replayed, method)(row.day)
        for occurrence in list(replayed.event_ecology.occurrence_history):
            try:
                replayed.event_ecology.select_daily_event(
                    day=occurrence.day, locations=replayed.locations,
                    location_growth=replayed.location_growth,
                    activity_records=replayed.activity_records)
            except ValueError:
                pass  # Historical selection fails closed without mutating state.
        scenarios['historical_review_idempotency'] = before == authoritative_signature(replayed)
        scenarios['historical_provider_calls_zero'] = guard.calls == 0
        counters = replayed.growth_proposals.to_dict()
        _run(replayed, 210)
        scenarios['exhaustion_no_proposals_or_calls'] = (
            counters == replayed.growth_proposals.to_dict() and guard.calls == 0)
        scenarios['event_history_reaches_bound'] = (
            len(replayed.event_ecology.occurrence_history) == replayed.event_ecology.policy.history_limit)
        guard = ReplayGuard()
        long_loaded = _engine(root, 'fresh', config, guard, load=True)
        scenarios['long_run_reload_without_model'] = (
            authoritative_signature(replayed) == authoritative_signature(long_loaded) and guard.calls == 0)
        scenarios['bounded_review_histories'] = (
            len(replayed.town_growth.review_history) <= replayed.town_growth.REVIEW_HISTORY_LIMIT
            and len(replayed.location_growth.review_history) <= replayed.location_growth.REVIEW_HISTORY_LIMIT
            and len(replayed.institution_growth.review_history) <= replayed.institution_growth.policy.history_limit
            and len(replayed.commerce_growth.review_history) <= replayed.commerce_growth.policy.history_limit)
        invariants.update({f'long_run:{key}': value for key, value in
                           (conservation_checks(replayed) | authority_checks(replayed)).items()})
        diagnostics = {'horizon_days': HORIZON_DAYS, 'boundary_labels': boundaries,
                       'provider_calls': provider.calls,
                       'signature_digest': payload_digest(signature),
                       'branches': [asdict(row) for row in fresh.commerce_growth.activation_records
                                    if row.template_id.startswith('generated_')]}
    failed = {
        'scenarios': sorted(key for key, value in scenarios.items() if not value),
        'invariants': sorted(key for key, value in invariants.items() if not value),
        'checkpoints': sorted(key for key, value in checkpoints.items() if not value),
        'mutations': sorted(key for key, value in mutations.items() if not value),
    }
    return {'passed': not any(failed.values()),
            'scenario_count': len(scenarios), 'scenarios_passed': sum(scenarios.values()),
            'invariant_count': len(invariants), 'invariants_passed': sum(invariants.values()),
            'replay_checkpoint_count': len(checkpoints), 'replay_checkpoints_passed': sum(checkpoints.values()),
            'mutation_count': len(mutations), 'mutations_rejected': sum(mutations.values()),
            'scenarios': scenarios, 'invariants': invariants,
            'replay_checkpoints': checkpoints, 'mutations': mutations,
            'diagnostics': diagnostics | {'failed': failed}}
