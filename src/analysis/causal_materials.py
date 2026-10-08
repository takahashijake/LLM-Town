"""Pure material/ledger contract checks, including ownership at commit order.

No system is constructed: immutable record definitions specify persisted fields;
all replay counters below are local observations, never simulation authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import fields

from src.analysis.causal_evidence import EvidenceGraph, RecordIndex, RecordRef, OwnershipFact
from src.analysis.inspection_records import safe_identity
from src.analysis.inspection_save import records
from src.systems.economy import EconomicAccount, TransactionRecord
from src.systems.materials import (
    GoodDefinition, Inventory, InventoryTransferRecord, ExchangeRecord, ProductionRecord,
    ProductionRecipe, MaterialLot, LotMovement, ConsumptionRecord, Seller,
)


class IncompleteEvidence(ValueError):
    """Internal controlled contract diagnostic."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise IncompleteEvidence(code)


def integer(value: object, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def quantities(value: object) -> bool:
    return isinstance(value, dict) and all(safe_identity(k) and integer(v, 1)
                                           for k, v in value.items())


def stamp(row: dict) -> tuple[int, int]:
    require(integer(row.get('day')), 'invalid_chronology')
    hour = row.get('hour')
    require(hour is None or integer(hour), 'invalid_chronology')
    return row['day'], -1 if hour is None else hour


def complete(row: dict, model: type) -> bool:
    return {item.name for item in fields(model)} <= row.keys()


def audit_ledger(save: dict, index: RecordIndex) -> str | None:
    """Reconcile saved monetary baselines and exact ledger sequence."""
    try:
        section = save.get('economy', {})
        require(section.get('schema_version') == 1, 'ledger_history_incomplete')
        accounts = {ref.identity: index.row(ref) for ref in index.of_type('account')}
        initial = section.get('initial_balances')
        require(isinstance(initial, dict) and set(initial) == set(accounts),
                'ledger_history_incomplete')
        require(all(integer(v) for v in initial.values()), 'invalid_ledger_baseline')
        balances = Counter(initial)
        for row in accounts.values():
            require(complete(row, EconomicAccount) and integer(row.get('balance'))
                    and row.get('owner_type') in {'agent', 'employer', 'institution', 'system'}
                    and safe_identity(row.get('owner_id')),
                    'invalid_account_contract')
        for number, ref in enumerate(index.of_type('transaction'), 1):
            row = index.row(ref)
            require(complete(row, TransactionRecord) and ref.identity == f'txn-{number:08d}',
                    'invalid_ledger_sequence')
            stamp(row)
            source, target = row.get('source_account_id'), row.get('destination_account_id')
            require(safe_identity(source) and safe_identity(target)
                    and source in accounts and target in accounts and source != target,
                    'invalid_account_reference')
            require(integer(row.get('amount'), 1), 'invalid_ledger_amount')
            require(isinstance(row.get('metadata'), dict), 'invalid_ledger_metadata')
            balances[source] -= row['amount']
            balances[target] += row['amount']
            require(balances[source] >= 0, 'ledger_replay_shortfall')
        require(all(balances[key] == row['balance'] for key, row in accounts.items()),
                'ledger_replay_mismatch')
        require(sum(initial.values()) == section.get('initial_total_currency')
                and integer(section.get('initial_total_currency')),
                'currency_baseline_mismatch')
        return None
    except IncompleteEvidence as error:
        return str(error)


def audit_materials(save: dict, index: RecordIndex) -> str | None:
    """Withhold material dependencies unless modern provenance fully replays."""
    try:
        section = save.get('materials', {})
        require(section.get('schema_version') == 2, 'material_history_incomplete')
        models = {'inventory': Inventory, 'transfer': InventoryTransferRecord,
                  'exchange': ExchangeRecord, 'production': ProductionRecord,
                  'recipe': ProductionRecipe, 'lot': MaterialLot, 'movement': LotMovement,
                  'consumption': ConsumptionRecord, 'seller': Seller}
        rows = {kind: {ref.identity: index.row(ref) for ref in index.of_type(kind)}
                for kind in models}
        for kind, model in models.items():
            require(all(complete(row, model) for row in rows[kind].values()),
                    'material_history_incomplete')
        prefixes = {'transfer': 'material-transfer', 'exchange': 'exchange',
                    'production': 'production', 'consumption': 'consumption'}
        for kind, prefix in prefixes.items():
            for number, ref in enumerate(index.of_type(kind), 1):
                row = index.row(ref)
                stamp(row)
                require(ref.identity == f'{prefix}-{number:08d}', 'invalid_material_record_sequence')
        inventories, lots = rows['inventory'], rows['lot']
        catalog = records(save, ('materials', 'goods'))
        require(all(complete(row, GoodDefinition) and safe_identity(row.get('id'))
                    and integer(row.get('unit_price'), 1) for row in catalog),
                'goods_catalog_incomplete')
        goods = {row['id']: row for row in catalog}
        require(len(goods) == len(catalog), 'duplicate_goods_identity')
        initial, holdings = section.get('initial_quantities'), section.get('lot_holdings')
        require(isinstance(initial, dict) and set(initial) == set(inventories)
                and all(quantities(v) for v in initial.values()), 'invalid_material_baseline')
        require(isinstance(holdings, dict) and set(holdings) <= set(inventories)
                and all(quantities(v) for v in holdings.values()), 'invalid_lot_holdings')
        replay = {key: Counter() for key in inventories}
        baseline = {key: Counter() for key in inventories}
        for row in inventories.values():
            require(safe_identity(row.get('owner_type')) and safe_identity(row.get('owner_id')),
                    'invalid_inventory_owner')
            require(quantities(row['quantities']), 'invalid_inventory_quantities')
            account = index.get('account', row.get('account_id'))
            require(row.get('account_id') is None or account is not None,
                    'invalid_inventory_account')
            if row['owner_type'] in {'agent', 'institution'}:
                require(account is not None and index.row(account).get('owner_type') == row['owner_type']
                        and index.row(account).get('owner_id') == row['owner_id'],
                        'inventory_owner_mismatch')
        for row in lots.values():
            require(row.get('good_id') in goods and integer(row['initial_quantity'], 1) and integer(row['created_day'])
                    and isinstance(row['parent_lot_ids'], list)
                    and all(safe_identity(k) for k in row['parent_lot_ids'])
                    and len(set(row['parent_lot_ids'])) == len(row['parent_lot_ids']),
                    'invalid_lot_contract')
            if row['origin_type'] == 'production':
                require(row['production_id'] in rows['production'], 'missing_lot_production')
                continue
            require(row['origin_type'] == 'initial_configuration' and row['origin_id'] in inventories
                    and row['production_id'] is None and row['recipe_id'] is None
                    and row['parent_lot_ids'] == []
                    and row['id'] == f"lot:initial:{row['origin_id']}:{row['good_id']}"
                    and row['created_day'] == 0 and row['created_hour'] is None,
                    'unsupported_lot_origin')
            replay[row['origin_id']][row['id']] = row['initial_quantity']
            baseline[row['origin_id']][row['good_id']] += row['initial_quantity']
        require(all(dict(baseline[key]) == initial[key] for key in inventories),
                'lot_baseline_mismatch')
        groups: dict[RecordRef, list[dict]] = defaultdict(list)
        ordered: list[RecordRef] = []
        previous_time = (-1, -1)
        previous_ref = None
        for number, ref in enumerate(index.of_type('movement'), 1):
            row = index.row(ref)
            require(ref.identity == f'lot-movement-{number:08d}', 'invalid_movement_sequence')
            time = stamp(row)
            require(time >= previous_time, 'corrupted_movement_chronology')
            previous_time = time
            kind = ('production' if row['movement_type'] == 'production_input' else
                    'consumption' if row['movement_type'] == 'consumption' else 'transfer')
            parent = index.get(kind, row['reference_id'])
            require(parent is not None, 'missing_movement_parent')
            lot = rows['lot'].get(row['lot_id']) if safe_identity(row['lot_id']) else None
            require(lot is not None and row['good_id'] == lot['good_id']
                    and integer(row['quantity'], 1), 'movement_lot_mismatch')
            require(stamp(index.row(parent)) == time, 'movement_time_mismatch')
            if parent != previous_ref:
                require(parent not in groups, 'interleaved_movement_groups')
                ordered.append(parent)
            previous_ref = parent
            groups[parent].append(row)
        expected = {ref for kind in ('production', 'transfer', 'consumption')
                    for ref in index.of_type(kind)}
        require(set(groups) == expected, 'missing_historical_movements')
        generated = set()
        for ref in ordered:
            row, movements = index.row(ref), groups[ref]
            totals = Counter()
            for movement in movements:
                totals[movement['good_id']] += movement['quantity']
            if ref.namespace == 'production':
                recipe = rows['recipe'].get(row['recipe_id']) if safe_identity(row['recipe_id']) else None
                require(recipe is not None and quantities(row['inputs']) and quantities(row['outputs'])
                        and row['inputs'] == recipe['inputs'] and row['outputs'] == recipe['outputs']
                        and row['inventory_id'] == recipe['output_inventory_id']
                        and row['activity_id'] == recipe['activity_id'], 'production_recipe_mismatch')
                for field, subject in [('eligible_actor_ids', 'actor_id'),
                                       ('eligible_employment_ids', 'employment_id')]:
                    allowed = recipe[field]
                    require(isinstance(allowed, list) and (not allowed or row[subject] in allowed),
                            'production_operator_mismatch')
                require(isinstance(row['input_lot_ids'], list)
                        and set(row['input_lot_ids']) == {m['lot_id'] for m in movements}
                        and len(set(row['input_lot_ids'])) == len(row['input_lot_ids'])
                        and dict(totals) == row['inputs'], 'production_input_mismatch')
                require(row['output_lot_ids'] == [f"lot:production:{ref.identity}:{key}"
                                                 for key in sorted(row['outputs'])],
                        'production_output_mismatch')
            else:
                if ref.namespace == 'consumption':
                    inventory = inventories.get(row['inventory_id'])
                    good = goods.get(row['good_id'])
                    require(inventory is not None and inventory['owner_type'] == 'agent'
                            and inventory['owner_id'] == row['agent_id'] and good is not None
                            and good.get('consumable') is True and safe_identity(good.get('need_effect'))
                            and row.get('need') == good['need_effect']
                            and integer(good.get('need_effect_amount'))
                            and integer(row.get('quantity'), 1)
                            and row.get('need_effect_amount') == good['need_effect_amount'] * row['quantity'],
                            'consumption_owner_or_good_mismatch')
                require(integer(row['quantity'], 1) and dict(totals) == {row['good_id']: row['quantity']},
                        'movement_quantity_mismatch')
            for movement in movements:
                if ref.namespace == 'transfer':
                    source, target = row['source_inventory_id'], row['destination_inventory_id']
                    require(safe_identity(row.get('authorization_type'))
                            and safe_identity(row.get('authorization_id'))
                            and source != target and movement['movement_type'] == row['authorization_type'],
                            'movement_authorization_mismatch')
                else:
                    source, target = row['inventory_id'], None
                    require(movement['movement_type'] == ('production_input' if ref.namespace == 'production'
                                                         else 'consumption'), 'movement_type_mismatch')
                require(safe_identity(source) and source in replay and
                        (target is None or safe_identity(target) and target in replay)
                        and movement['source_inventory_id'] == source
                        and movement['destination_inventory_id'] == target, 'movement_inventory_mismatch')
                replay[source][movement['lot_id']] -= movement['quantity']
                require(replay[source][movement['lot_id']] >= 0, 'lot_replay_shortfall')
                if target is not None:
                    replay[target][movement['lot_id']] += movement['quantity']
            if ref.namespace == 'production':
                for lot_id in row['output_lot_ids']:
                    lot = lots.get(lot_id)
                    require(lot is not None and lot['origin_type'] == 'production'
                            and lot['origin_id'] == ref.identity and lot['production_id'] == ref.identity
                            and lot['recipe_id'] == row['recipe_id'] and lot['parent_lot_ids'] == row['input_lot_ids']
                            and lot['initial_quantity'] == row['outputs'].get(lot['good_id'])
                            and (lot['created_day'], lot['created_hour']) == (row['day'], row['hour']),
                            'production_lot_ancestry_mismatch')
                    replay[row['inventory_id']][lot_id] += lot['initial_quantity']
                    generated.add(lot_id)
        require(generated == {key for key, lot in lots.items() if lot['origin_type'] == 'production'},
                'orphan_production_lot')
        for key, inventory in inventories.items():
            require(dict(+replay[key]) == holdings.get(key, {}), 'lot_holdings_replay_mismatch')
            good_totals = Counter()
            for lot_id, quantity in (+replay[key]).items():
                good_totals[lots[lot_id]['good_id']] += quantity
            require(dict(good_totals) == inventory['quantities'], 'inventory_replay_mismatch')
        return None
    except IncompleteEvidence as error:
        return str(error)


def add_material_edges(graph: EvidenceGraph, save: dict, ledger_error: str | None) -> str | None:
    index = graph.index
    material_error = audit_materials(save, index)
    if material_error:
        for kind in ('lot', 'movement', 'production', 'transfer', 'consumption', 'exchange'):
            for ref in index.of_type(kind):
                graph.unknown(ref, material_error)
        return material_error
    for inventory_id, lots in save['materials']['lot_holdings'].items():
        inventory = index.get('inventory', inventory_id)
        owner = index.row(inventory)
        for lot_id, quantity in lots.items():
            graph.ownership.append(OwnershipFact(index.get('lot', lot_id), inventory,
                                                 owner['owner_type'], owner['owner_id'], quantity))
    for ref in index.of_type('production'):
        row = index.row(ref)
        for identity in row['input_lot_ids']:
            graph.add(index.get('lot', identity), ref, 'consumed_input',
                      'MaterialSystem.production_records_are_valid + movement ownership replay')
        for identity in row['output_lot_ids']:
            graph.add(ref, index.get('lot', identity), 'produced_lot',
                      'MaterialSystem.production_records_are_valid: exact output and ancestry')
    for ref in index.of_type('movement'):
        row = index.row(ref)
        kind = ('production' if row['movement_type'] == 'production_input' else
                'consumption' if row['movement_type'] == 'consumption' else 'transfer')
        graph.add(index.get(kind, row['reference_id']), ref, 'committed_movement',
                  'MaterialSystem.lot_movements_reconcile_with_events + ownership replay')
        graph.add(index.get('lot', row['lot_id']), ref, 'moved_lot',
                  'MaterialSystem.provenance_history_reconstructs_holdings')
    prices = {row['id']: row['unit_price'] for row in records(save, ('materials', 'goods'))}
    for ref in index.of_type('exchange'):
        row = index.row(ref)
        tx, transfer = index.get('transaction', row['monetary_transaction_id']), index.get('transfer', row['inventory_transfer_id'])
        t, goods = index.row(tx), index.row(transfer)
        seller, buyer = index.row(index.get('seller', row['seller_id'])), index.row(index.get('inventory', row['buyer_inventory_id']))
        seller_inventory = index.row(index.get('inventory', row['seller_inventory_id']))
        valid = not ledger_error and tx and transfer and (
            t['transaction_type'] == 'purchase' and t['source_account_id'] == row['buyer_account_id']
            and t['destination_account_id'] == row['seller_account_id'] and t['amount'] == row['total_price']
            and t['metadata'].get('exchange_id') == ref.identity
            and goods['authorization_type'] == 'exchange' and goods['authorization_id'] == ref.identity
            and goods['source_inventory_id'] == row['seller_inventory_id']
            and goods['destination_inventory_id'] == row['buyer_inventory_id']
            and goods['good_id'] == row['good_id'] and goods['quantity'] == row['quantity']
            and integer(row['unit_price'], 1) and row['unit_price'] == prices.get(row['good_id'])
            and row['total_price'] == row['unit_price'] * row['quantity']
            and seller.get('inventory_id') == row['seller_inventory_id']
            and seller.get('account_id') == row['seller_account_id']
            and seller_inventory.get('account_id') == row['seller_account_id']
            and buyer.get('account_id') == row['buyer_account_id']
            and stamp(t) == stamp(row) == stamp(goods))
        if valid:
            graph.add(tx, ref, 'payment_leg', 'MaterialSystem.exchanges_reconcile_with_ledger: reciprocal payment')
            graph.add(ref, transfer, 'goods_leg', 'MaterialSystem.exchanges_reconcile_with_ledger: reciprocal goods')
        else:
            graph.unknown(ref, ledger_error or 'exchange_contract_mismatch')
