"""Pure civic evidence checks; no engine construction, transitions or prose."""
from src.analysis.causal_evidence import EvidenceGraph
from src.systems.collective_projects import ProjectPolicy, validate_authority


def add_project_edges(graph: EvidenceGraph, save: dict) -> None:
    state = save.get('collective_projects')
    refs = graph.index.of_type('project')
    if state is None:
        for ref in graph.index.of_type('civic_activity'):
            graph.unknown(ref, 'project_authority_missing')
        return
    try:
        policy = ProjectPolicy.from_config(state.get('policy'))
        validate_authority(state, policy,
                           save.get('institution_growth', {}).get('formation_records', []),
                           {a['id'] for a in save.get('agents', [])},
                           {r['location_id'] for r in save.get('location_growth', {}).get('activation_records', [])
                            if r.get('status') == 'activated'},
                           save.get('activity_records', []),
                           {r['agent_id']: r['activation_day']
                            for r in save.get('town_growth', {}).get('migration_records', [])
                            if r.get('status') == 'activated'})
        expected_review = save.get('current_day', -1) - (not save.get('day_complete', False))
        if ((state['projects'] and state['last_review_day'] != expected_review)
                or any(r.get('day', 0) > save.get('current_day', -1)
                       or (r.get('day') == save.get('current_day')
                           and r.get('hour', 0) > save.get('current_hour', -1))
                       for r in save.get('activity_records', []) if r.get('civic_execution_key'))
                or state['last_review_day'] > save.get('current_day', -1)):
            raise ValueError('future project review')
    except (ValueError, TypeError, KeyError):
        graph.project_authority_valid = False
        for ref in refs + graph.index.of_type('contribution') + graph.index.of_type('project_effect'):
            graph.unknown(ref, 'project_contract_invalid')
        return
    graph.project_authority_valid = True
    index = graph.index
    for ref in refs:
        row = index.row(ref)
        formation = index.get('institution', row['formation_id'])
        # V8 must independently verify the institution's registered authority.
        dependencies = {e.relationship for e in graph.edges if e.effect == formation}
        if not formation or not {'startup_funding', 'activated_location'} <= dependencies:
            graph.unknown(ref, 'project_institution_authority_unresolved')
            continue
        contributions = state['contributions']
        graph.project_audits[ref] = {
            'project': ref.to_dict(), 'evidence': 'derived_from_verified_records',
            'requirements': {'work_sessions': policy.required_units,
                             'distinct_residents': policy.minimum_residents, 'distinct_days': 2,
                             'daily_capacity': policy.daily_capacity},
            'verified_progress': {'work_sessions': len(contributions),
                                  'distinct_residents': len({c['actor_id'] for c in contributions}),
                                  'distinct_days': len({c['day'] for c in contributions})},
            'status': row['status'],
            'reason_code': {'active': ('completion_review_pending'
                            if len(contributions) == policy.required_units
                            else 'verified_work_requirements_pending'),
                            'completed': 'all_verified_requirements_met',
                            'expired': 'deadline_passed_without_completion',
                            'cancelled': 'operator_cancelled_without_benefit'}[row['status']],
        }
        graph.add(formation, ref, 'project_eligibility',
                  'Finite garden template: activated exact institution and location; population >= required residents')
        for c in index.of_type('contribution'):
            contribution = index.row(c)
            execution = index.get('civic_activity', contribution['execution_key'])
            graph.add(execution, c, 'verified_civic_work',
                      'Exact actor/project/location/day/hour/index; unique bounded executed work session')
            graph.add(c, ref, 'project_progress',
                      'Distinct resident and day requirements; bounded work evidence, no narrative authority')
        if row['status'] == 'completed':
            effect = index.of_type('project_effect')[0]
            graph.add(ref, effect, 'unlocked_learning_activity',
                      'All work requirements met; exactly one effect from the following day')
            for execution in index.of_type('civic_activity'):
                if index.row(execution).get('source_project_effect_id') == effect.identity:
                    graph.add(effect, execution, 'enabled_workshop_execution',
                              'Exact active location, actor and future day; capacity one per tick')
        elif row['status'] == 'active':
            graph.unknown(ref, 'project_requirements_pending')
        else:
            graph.unknown(ref, 'project_terminal_without_benefit')
