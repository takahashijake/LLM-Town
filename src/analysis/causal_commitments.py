"""Bounded commitment repair, transfer fulfillment and source-plan evidence."""
from __future__ import annotations

from src.analysis.causal_evidence import EvidenceGraph
from src.analysis.causal_materials import integer, complete
from src.analysis.inspection_records import safe_identity
from src.systems.commitments import SocialCommitment, COMMITMENT_STATUSES, COMMITMENT_TYPES
from src.systems.plans import AgentPlan, PlanStep, TEMPLATE_ACTIONS, KNOWN_PLAN_TYPES, PLAN_STATUSES


def commitment_contract(row: dict) -> bool:
    return (complete(row, SocialCommitment) and safe_identity(row.get('proposer_id'))
            and safe_identity(row.get('counterpart_id')) and row['proposer_id'] != row['counterpart_id']
            and row.get('commitment_type') in COMMITMENT_TYPES
            and row.get('status') in COMMITMENT_STATUSES and integer(row.get('created_day'), 1))


def add_commitment_edges(graph: EvidenceGraph, *, material_valid: bool) -> None:
    index = graph.index
    fulfilled = set()
    valid_actions = set()
    for ref in index.of_type('commitment'):
        row = index.row(ref)
        graph.unknown(ref, 'creation_dialogue_not_inspected')
        if not commitment_contract(row):
            graph.unknown(ref, 'commitment_contract_incomplete')
            continue
        parent_id = row.get('repair_of_commitment_id')
        if parent_id is not None:
            parent_ref = index.get('commitment', parent_id)
            parent = index.row(parent_ref)
            cursor, seen = ref, set()
            acyclic = True
            for _ in range(33):
                if cursor in seen:
                    acyclic = False
                    break
                seen.add(cursor)
                next_id = index.row(cursor).get('repair_of_commitment_id')
                if next_id is None:
                    break
                cursor = index.get('commitment', next_id)
                if cursor is None:
                    acyclic = False
                    break
            else:
                acyclic = False
            valid = (parent_ref and commitment_contract(parent) and acyclic
                     and parent.get('status') in {'failed', 'expired', 'cancelled'}
                     and row.get('commitment_type') in {'transfer', 'help', 'meet'}
                     and parent.get('commitment_type') == row['commitment_type']
                     and row.get('proposer_id') != row.get('counterpart_id')
                     and {row.get('proposer_id'), row.get('counterpart_id')}
                     == {parent.get('proposer_id'), parent.get('counterpart_id')}
                     and integer(parent.get('resolution_day'), 1) and integer(row.get('created_day'), 1)
                     and parent['resolution_day'] <= row['created_day']
                     and (parent['resolution_day'] < row['created_day']
                          or parent.get('resolution_tick') is None or row.get('created_tick') is None
                          or integer(parent.get('resolution_tick')) and integer(row.get('created_tick'))
                          and parent['resolution_tick'] <= row['created_tick']))
            if valid:
                graph.add(parent_ref, ref, 'repair_successor',
                          'CommitmentSystem.validate_invariants: terminal parent, same pair/type, acyclic chronology')
            else:
                graph.unknown(ref, 'repair_lineage_missing_invalid_or_too_deep')
        if row.get('status') == 'cancelled':
            graph.unknown(ref, 'cancellation_dialogue_evidence_excluded')
        if row.get('status') != 'fulfilled':
            continue
        evidence, metadata = row.get('evidence'), row.get('metadata')
        if not isinstance(evidence, list) or not all(isinstance(e, dict) for e in evidence) or not isinstance(metadata, dict):
            graph.unknown(ref, 'fulfillment_evidence_incomplete')
            continue
        found = False
        if material_valid and row.get('commitment_type') == 'transfer':
            proofs = {e.get('material_transfer_id') for e in evidence
                      if type(e.get('material_transfer_id')) is str}
            matches = [t for t in index.of_type('transfer') if t.identity in proofs
                       and index.row(t).get('authorization_type') == 'commitment'
                       and index.row(t).get('authorization_id') == ref.identity]
            if len(matches) == 1:
                transfer, t = matches[0], index.row(matches[0])
                valid = (t.get('source_inventory_id') == f"inventory:agent:{row.get('counterpart_id')}"
                         and t.get('destination_inventory_id') == f"inventory:agent:{row.get('proposer_id')}"
                         and t.get('good_id') == metadata.get('good_id')
                         and integer(metadata.get('quantity'), 1) and t.get('quantity') == metadata['quantity']
                         and t.get('event_key') == f'commitment:{ref.identity}:fulfillment'
                         and t.get('day') == row.get('resolution_day') and t.get('hour') == row.get('resolution_tick')
                         and integer(row.get('created_day'), 1) and t['day'] >= row['created_day'])
                if valid:
                    graph.add(transfer, ref, 'fulfilled_transfer',
                              'CommitmentSystem.fulfill_transfer + validate_invariants: exact authorized goods proof')
                    found = True
                    fulfilled.add(ref)
        # Non-material execution facts lack persisted co-location authority;
        # expose their records, but do not certify fulfillment from an ID alone.
        if not found:
            graph.unknown(ref, 'fulfillment_authority_not_verified')
    for kind in ('attempt', 'execution'):
        for ref in index.of_type(kind):
            row = index.row(ref)
            source = index.get('commitment', row.get('commitment_id'))
            commitment = index.row(source)
            valid = (source and commitment_contract(commitment) and row.get('agent_id') == commitment.get('counterpart_id')
                     and integer(commitment.get('created_day'), 1) and integer(row.get('day'), 1)
                     and row['day'] >= commitment['created_day']
                     and (row.get('tick') is None or integer(row['tick'])))
            if kind == 'execution':
                valid = valid and row.get('source_commitment_id') == source.identity and row.get('event_key') == f'commitment-action:{source.identity}'
            else:
                valid = valid and row.get('event_key') == f"commitment-attempt:{source.identity}:{row.get('kind')}:{row['day']}:{row.get('tick')}"
            if valid:
                graph.add(source, ref, 'recorded_attempt' if kind == 'attempt' else 'recorded_execution',
                          'CommitmentSystem.record_attempt / execute_activity: exact source, actor and event key')
                valid_actions.add(ref)
                graph.unknown(ref, 'attempt_or_execution_record_is_not_full_outcome_proof')
            else:
                graph.unknown(ref, 'commitment_action_binding_mismatch')
    valid_plans = set()
    for ref in index.of_type('plan'):
        row = index.row(ref)
        source = index.get('commitment', row.get('source_id'))
        parent = index.row(source)
        steps = row.get('steps')
        plan_type = row.get('plan_type')
        step_contract = (isinstance(steps, list) and 1 <= len(steps) <= 4
                         and all(isinstance(step, dict) and complete(step, PlanStep) for step in steps)
                         and plan_type in KNOWN_PLAN_TYPES
                         and tuple(step['action_type'] for step in steps) == TEMPLATE_ACTIONS[plan_type.removeprefix('commitment_')])
        if (source and commitment_contract(parent) and complete(row, AgentPlan) and step_contract
                and row.get('status') in PLAN_STATUSES and row.get('source_type') == 'commitment'
                and row.get('agent_id') == parent.get('counterpart_id')
                and integer(row.get('created_day'), 1) and integer(parent.get('created_day'), 1)
                and row['created_day'] >= parent['created_day']):
            graph.add(source, ref, 'source_plan',
                      'PlanSystem.validate_invariants: exact commitment source and actor ownership')
            valid_plans.add(ref)
        else:
            graph.unknown(ref, 'plan_source_missing_or_mismatched')
        graph.unknown(ref, 'plan_step_outcomes_not_verified')

    actions_by_source = {}
    for action in sorted(valid_actions):
        a = index.row(action)
        actions_by_source.setdefault((a['commitment_id'], a['day'], a.get('tick')), []).append(action)
    verified_exchanges = {edge.effect for edge in graph.edges if edge.relationship == 'payment_leg'}
    for ref in index.of_type('plan_execution'):
        row = index.row(ref)
        plan = index.get('plan', row.get('plan_id'))
        p = index.row(plan)
        if plan not in valid_plans:
            graph.unknown(ref, 'plan_execution_source_incomplete')
            continue
        source = index.get('commitment', p['source_id'])
        c = index.row(source)
        steps = [step for step in p['steps'] if step.get('id') == row.get('step_id')]
        step = steps[0] if len(steps) == 1 else {}
        valid = (step and row.get('source_commitment_id') == p['source_id']
                 and row.get('action_type') == step['action_type']
                 and step.get('status') == 'completed' and step.get('execution_key') == ref.identity
                 and integer(row.get('day'), 1) and row['day'] >= p['created_day'])
        proof = None
        if valid:
            for action in actions_by_source.get((p['source_id'], row.get('day'), row.get('tick')), []):
                a = index.row(action)
                if (a.get('day'), a.get('tick')) != (row.get('day'), row.get('tick')):
                    continue
                if step['action_type'] == 'commitment_acquire_resource':
                    exchange = index.get('exchange', a.get('exchange_id'))
                    e = index.row(exchange)
                    meta = c.get('metadata', {})
                    if (action.namespace == 'attempt' and a.get('kind') == 'preparation'
                            and exchange in verified_exchanges and exchange.identity == ref.identity
                            and e.get('event_key') == f"commitment:{source.identity}:preparation"
                            and e.get('buyer_inventory_id') == f"inventory:agent:{p['agent_id']}"
                            and isinstance(meta, dict) and e.get('good_id') == meta.get('good_id')
                            and integer(meta.get('quantity'), 1) and e.get('quantity') == meta['quantity']):
                        proof = exchange
                        break
                elif (source in fulfilled and action.namespace == 'execution'
                      and a.get('activity_id') == step['action_type']
                      and ref.identity in {a.get('event_key'), a.get('material_transfer_id')}):
                    proof = action
                    break
        if proof:
            graph.add(plan, ref, 'plan_step_execution',
                      'PlanSystem.record_execution: exact source, step, action and execution key')
            graph.add(proof, ref, 'plan_execution_proof',
                      'PlanSystem._has_authoritative_proof: validated acquisition or fulfilled transfer')
        else:
            graph.unknown(ref, 'plan_execution_authority_not_verified')
