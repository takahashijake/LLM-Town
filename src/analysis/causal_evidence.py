"""Immutable typed identities and deterministic bounded evidence traversal."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256
import json

from src.analysis.inspection_records import ALLOWED_FIELDS, safe_fields, safe_identity, safe_scalar
from src.analysis.inspection_save import InspectionError, MAX_RECORDS, records, bounded_report

EVIDENCE_VERSION = 1
COLLECTIONS = {
    'project': ('collective_projects', 'projects'),
    'contribution': ('collective_projects', 'contributions'),
    'project_effect': ('collective_projects', 'effects'),
    'occurrence': ('event_ecology', 'occurrence_history'),
    'institution': ('institution_growth', 'formation_records'),
    'location': ('location_growth', 'activation_records'),
    'commerce': ('commerce_growth', 'activation_records'),
    'account': ('economy', 'accounts'),
    'employment': ('economy', 'employments'),
    'transaction': ('economy', 'ledger'),
    'lot': ('materials', 'lots'),
    'movement': ('materials', 'lot_movements'),
    'transfer': ('materials', 'inventory_transfers'),
    'exchange': ('materials', 'exchanges'),
    'production': ('materials', 'production_records'),
    'consumption': ('materials', 'consumptions'),
    'inventory': ('materials', 'inventories'),
    'seller': ('materials', 'sellers'),
    'recipe': ('materials', 'production_recipes'),
    'commitment': ('commitments', 'commitments'),
    'attempt': ('commitments', 'attempt_records'),
    'execution': ('commitments', 'execution_records'),
    'plan': ('plans', 'plans'),
    'plan_execution': ('plans', 'execution_records'),
}
KEY_FIELDS = {'civic_activity': 'civic_execution_key', 'occurrence': 'occurrence_id', 'attempt': 'event_key', 'execution': 'event_key',
              'plan_execution': 'execution_key'}


@dataclass(frozen=True, order=True)
class RecordRef:
    namespace: str
    identity: str

    def to_dict(self) -> dict:
        return {'type': self.namespace, 'id': self.identity}


@dataclass(frozen=True)
class EvidenceNode:
    ref: RecordRef
    source_path: str
    fields: tuple[tuple[str, object], ...]

    def to_dict(self) -> dict:
        return {'ref': self.ref.to_dict(), 'evidence': 'persisted_fact',
                'source_path': self.source_path, 'fields': dict(self.fields)}


@dataclass(frozen=True, order=True)
class EvidenceEdge:
    cause: RecordRef
    effect: RecordRef
    relationship: str
    contract: str

    def to_dict(self) -> dict:
        payload = {'source': self.cause.to_dict(), 'target': self.effect.to_dict(),
                   'relationship': self.relationship, 'contract': self.contract,
                   'evidence': 'verified_dependency'}
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return {'id': sha256(encoded.encode()).hexdigest(), **payload}


@dataclass(frozen=True, order=True)
class UnresolvedEvidence:
    ref: RecordRef
    code: str

    def to_dict(self) -> dict:
        return {'ref': self.ref.to_dict(), 'evidence': 'unresolved', 'code': self.code}


@dataclass(frozen=True, order=True)
class EvidenceAssociation:
    source: RecordRef
    target: RecordRef
    code: str

    def to_dict(self) -> dict:
        return {'source': self.source.to_dict(), 'target': self.target.to_dict(),
                'evidence': 'association_only', 'code': self.code}


@dataclass(frozen=True, order=True)
class OwnershipFact:
    lot: RecordRef
    inventory: RecordRef
    owner_type: str
    owner_id: str
    quantity: int

    def to_dict(self) -> dict:
        return {'evidence': 'persisted_fact', 'lot': self.lot.to_dict(),
                'inventory': self.inventory.to_dict(), 'owner_type': self.owner_type,
                'owner_id': self.owner_id, 'quantity': self.quantity,
                'source_path': 'materials.lot_holdings',
                'contract': 'MaterialSystem.provenance_history_reconstructs_holdings: current snapshot reconciled'}


class RecordIndex:
    """Namespace-local identity resolution. Never join arbitrary field values."""

    def __init__(self, save: dict) -> None:
        self.rows: dict[RecordRef, dict] = {}
        self.nodes: dict[RecordRef, EvidenceNode] = {}
        self.by_type: dict[str, list[RecordRef]] = defaultdict(list)
        total = 0
        for namespace, path in list(COLLECTIONS.items()) + [("civic_activity", ("activity_records",))]:
            for ordinal, row in enumerate(records(save, path)):
                if namespace == "civic_activity" and not row.get("civic_execution_key"):
                    continue
                total += 1
                if total > MAX_RECORDS:
                    raise InspectionError('causal records exceed input budget')
                for key in ALLOWED_FIELDS & row.keys():
                    value = row[key]
                    if key.endswith('_ids'):
                        if not isinstance(value, list) or not all(safe_identity(v) for v in value):
                            raise InspectionError('invalid causal reference list')
                    elif value is not None and not safe_scalar(value):
                        raise InspectionError('invalid causal scalar field')
                    if key.endswith('_id') and value is not None and not safe_identity(value):
                        raise InspectionError('invalid causal reference identity')
                identity = row.get(KEY_FIELDS.get(namespace, 'id'))
                if not safe_identity(identity):
                    raise InspectionError('causal record requires a safe typed identity')
                ref = RecordRef(namespace, identity)
                if ref in self.rows:
                    raise InspectionError('duplicate identity in causal namespace')
                self.rows[ref] = row
                self.by_type[namespace].append(ref)
                fields = tuple((key, tuple(value) if isinstance(value, list) else value)
                               for key, value in safe_fields(row).items())
                self.nodes[ref] = EvidenceNode(ref, '.'.join(path) + f'[{ordinal}]', fields)

    def get(self, namespace: str, identity: object) -> RecordRef | None:
        if not safe_identity(identity):
            return None
        ref = RecordRef(namespace, identity)
        return ref if ref in self.rows else None

    def row(self, ref: RecordRef | None) -> dict:
        return self.rows[ref] if ref else {}

    def of_type(self, namespace: str) -> list[RecordRef]:
        return self.by_type[namespace]

    def root(self, namespace: str, identity: str) -> RecordRef:
        if namespace not in COLLECTIONS and namespace != "civic_activity":
            raise InspectionError('unsupported causal query type')
        if not safe_identity(identity):
            raise InspectionError('invalid causal query identity')
        direct = self.get(namespace, identity)
        if direct:
            return direct
        if namespace == 'institution':
            matches = [ref for ref in self.of_type(namespace)
                       if self.row(ref).get('institution_id') == identity]
            if len(matches) == 1:
                return matches[0]
        raise InspectionError('causal query identity is missing or ambiguous')


class EvidenceGraph:
    """Build once, index adjacency once; return independently bounded reports."""

    def __init__(self, index: RecordIndex) -> None:
        self.index = index
        self.edges: set[EvidenceEdge] = set()
        self.unresolved: set[UnresolvedEvidence] = set()
        self.associations: set[EvidenceAssociation] = set()
        self.ownership: list[OwnershipFact] = []
        self.project_audits: dict[RecordRef, dict] = {}
        self.audit_errors: dict[str, str | None] = {}

    def add(self, cause: RecordRef, effect: RecordRef, label: str, contract: str) -> None:
        if len(self.edges) >= MAX_RECORDS:
            raise InspectionError('graph exceeds relationship budget')
        self.edges.add(EvidenceEdge(cause, effect, label, contract))

    def unknown(self, ref: RecordRef, code: str) -> None:
        self.unresolved.add(UnresolvedEvidence(ref, code))

    def investigate(self, root: RecordRef, *, depth: int = 6, limit: int = 100,
                    direction: str = 'both') -> dict:
        if type(depth) is not int or not 0 <= depth <= 32:
            raise InspectionError('depth must be 0..32')
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise InspectionError('limit must be 1..1000')
        if direction not in {'upstream', 'downstream', 'both'}:
            raise InspectionError('unsupported traversal direction')
        adjacency = defaultdict(list)
        for edge in sorted(self.edges):
            if direction in {'both', 'downstream'}:
                adjacency[edge.cause].append((edge.effect, edge))
            if direction in {'both', 'upstream'}:
                adjacency[edge.effect].append((edge.cause, edge))
        queue = deque([(root, 0)])
        visited = {root}
        selected = set()
        truncated = False
        while queue:
            ref, level = queue.popleft()
            for neighbor, edge in sorted(adjacency[ref]):
                if level == depth:
                    if neighbor not in visited or edge not in selected:
                        truncated = True
                    continue
                if len(selected) >= limit and edge not in selected:
                    truncated = True
                    continue
                if neighbor not in visited:
                    if len(visited) >= limit:
                        truncated = True
                        continue
                    visited.add(neighbor)
                    queue.append((neighbor, level + 1))
                selected.add(edge)
        diagnostics = [item for item in sorted(self.unresolved) if item.ref in visited]
        if len(diagnostics) > limit:
            truncated = True
        associations = [item for item in sorted(self.associations) if item.target in visited or item.source in visited]
        if len(associations) > limit:
            truncated = True
        ownership = [item for item in sorted(self.ownership) if item.lot in visited]
        if len(ownership) > limit:
            truncated = True
        payload = {
            'schema_version': EVIDENCE_VERSION, 'kind': 'causal_trace',
            'root': root.to_dict(), 'direction': direction, 'depth': depth, 'limit': limit,
            'nodes': [self.index.nodes[ref].to_dict() for ref in sorted(visited)],
            'edges': [edge.to_dict() for edge in sorted(selected)],
            'unresolved': [item.to_dict() for item in diagnostics[:limit]],
            'ownership': [item.to_dict() for item in ownership[:limit]],
            'associations': [item.to_dict() for item in associations[:limit]], 'truncated': truncated,
            'policy': 'Verified edges check persisted contracts; full eligibility and file authenticity are not proven. Private knowledge and narrative are excluded.',
        }
        audits = [self.project_audits[ref] for ref in sorted(visited) if ref in self.project_audits]
        if audits:
            payload["project_audits"] = audits
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        payload['signature'] = sha256(encoded.encode()).hexdigest()
        return bounded_report(payload)
