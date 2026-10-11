"""Controlled human labels for causal evidence; narrative never enters output."""
from __future__ import annotations

LABELS = {
    'project_eligibility': 'Activated garden institution authorizes this finite project',
    'verified_civic_work': 'Exact independently executed work session supports contribution',
    'project_progress': 'Verified contribution supports project progress',
    'unlocked_learning_activity': 'Completed requirements unlock next-day learning opportunity',
    'enabled_workshop_execution': 'Project effect enabled an actual later workshop session',
    'activated_location': 'Location activation required by formation',
    'startup_funding': 'Startup funding supports institution activation',
    'registered_account': 'Formation registered employer account',
    'registered_employment': 'Formation registered employment',
    'institution_commerce': 'Exact institution branch supports commerce activation',
    'registered_commerce_resource': 'Commerce registered material resource',
    'authorized_recipe': 'Registered recipe authorizes production',
    'consumed_input': 'Production consumed this input lot',
    'produced_lot': 'Production created this output lot',
    'committed_movement': 'Authoritative operation committed lot movement',
    'moved_lot': 'Movement draws from this lot',
    'payment_leg': 'Ledger payment settles exchange',
    'goods_leg': 'Exchange authorizes goods transfer',
    'fulfilled_transfer': 'Exact authorized transfer fulfills commitment',
    'repair_successor': 'Terminal commitment is predecessor of repair',
    'recorded_attempt': 'Commitment identifies actor attempt',
    'recorded_execution': 'Commitment identifies execution record',
    'source_plan': 'Commitment is the actor-owned plan source',
    'plan_step_execution': 'Plan identifies exact completed step execution',
    'plan_execution_proof': 'Authoritative proof supports plan execution',
}


def format_trace(report: dict) -> str:
    """Render only fixed descriptions and already validated typed identities."""
    def label(ref: dict) -> str:
        return f"{ref['type']}:{ref['id']}"
    lines = [f"Investigation: {label(report['root'])}", report['policy']]
    for audit in report.get('project_audits', []):
        progress, required = audit['verified_progress'], audit['requirements']
        lines.append(f"PROJECT {audit['status']}: {progress['work_sessions']}/{required['work_sessions']} sessions, "
                     f"{progress['distinct_residents']}/{required['distinct_residents']} residents, "
                     f"{progress['distinct_days']}/{required['distinct_days']} days; {audit['reason_code']}")
    for edge in report['edges']:
        lines.append(f"VERIFIED {label(edge['source'])} -> {label(edge['target'])}: "
                     + LABELS[edge['relationship']])
    for holding in report['ownership']:
        lines.append(f"CURRENT HOLDER {label(holding['lot'])}: {holding['owner_type']}:{holding['owner_id']} "
                     f"holds {holding['quantity']} in {label(holding['inventory'])}")
    for unresolved in report['unresolved']:
        lines.append(f"UNRESOLVED {label(unresolved['ref'])}: {unresolved['code']}")
    for association in report['associations']:
        lines.append(f"ASSOCIATION {label(association['source'])} ~ {label(association['target'])}: "
                     + association['code'])
    if report['truncated']:
        lines.append('Traversal or association results reached the requested bound.')
    lines.append(f"Signature: {report['signature']}")
    return '\n'.join(lines)
