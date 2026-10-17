"""Narrow persisted growth dependency contracts, never inferred eligibility."""
from __future__ import annotations

import re

from src.analysis.causal_evidence import EvidenceGraph, RecordRef, EvidenceAssociation
from src.analysis.causal_materials import integer, complete
from src.systems.institution_growth import InstitutionFormationRecord
from src.systems.location_growth import LocationActivationRecord
from src.systems.commerce_growth import CommerceActivationRecord
from src.systems.economy import Employment


def active(row: dict) -> bool:
    return (row.get('status') == 'activated' and integer(row.get('review_day'), 1)
            and integer(row.get('activation_day'), 1)
            and row['activation_day'] >= row['review_day'])


def add_growth_edges(graph: EvidenceGraph, save: dict, ledger_error: str | None, *, material_valid: bool) -> None:
    index = graph.index
    valid_formations: set[RecordRef] = set()
    for ref in index.of_type('institution'):
        row = index.row(ref)
        graph.unknown(ref, 'eligibility_witness_not_persisted')
        if not complete(row, InstitutionFormationRecord) or not active(row) or row.get('event_key') != f"institution-review:day:{row.get('review_day')}":
            graph.unknown(ref, 'formation_activation_incomplete')
            continue
        sequence = re.fullmatch(r'institution-formation:(\d{4,})', ref.identity)
        if not sequence or any(row.get(key) != pattern + sequence.group(1) for key, pattern in (
            ('institution_id', 'institution:'), ('employer_account_id', 'account:institution:'),
            ('employment_id', 'employment:institution:'))):
            graph.unknown(ref, 'formation_identity_mismatch')
            continue
        employment = index.get('employment', row.get('employment_id'))
        job = index.row(employment)
        activities = job.get('qualifying_activity_ids')
        activity_locations = job.get('activity_locations')
        location_binding = (isinstance(activities, list) and bool(activities)
                            and all(isinstance(value, str) for value in activities)
                            and isinstance(activity_locations, dict)
                            and set(activity_locations) == set(activities)
                            and all(place == row.get('location_id') for place in activity_locations.values()))
        location = index.get('location', row.get('location_activation_id'))
        loc = index.row(location)
        if (location_binding and location and complete(loc, LocationActivationRecord) and active(loc) and loc.get('location_id') == row.get('location_id')
                and loc['activation_day'] <= row['review_day']):
            graph.add(location, ref, 'activated_location',
                      'InstitutionGrowthSystem.validate: exact activation, location and employment activity binding')
        else:
            graph.unknown(ref, 'location_activation_missing_or_mismatched')
        account = index.get('account', row.get('employer_account_id'))
        employment = index.get('employment', row.get('employment_id'))
        tx = index.get('transaction', row.get('startup_transaction_id'))
        a, e, t = index.row(account), index.row(employment), index.row(tx)
        metadata = t.get('metadata', {})
        initial = save.get('economy', {}).get('initial_balances', {})
        valid = (not ledger_error and location_binding and account and employment and tx and complete(e, Employment)
                 and a.get('owner_type') == 'institution' and a.get('owner_id') == row.get('institution_id')
                 and isinstance(initial, dict) and initial.get(account.identity) == 0
                 and e.get('institution_id') == row.get('institution_id')
                 and e.get('formation_id') == ref.identity and e.get('agent_id') == row.get('employee_agent_id')
                 and e.get('employer_account_id') == account.identity
                 and isinstance(row.get('role_template_id'), str) and e.get('role_template_id') == row['role_template_id']
                 and e.get('active') is True and e.get('start_day') == row['activation_day'] + 1
                 and t.get('event_key') == f'institution-startup:{ref.identity}'
                 and t.get('transaction_type') == 'institution_startup'
                 and t.get('destination_account_id') == account.identity
                 and t.get('day') == row['activation_day'] and t.get('hour') is None
                 and isinstance(metadata, dict) and metadata.get('formation_id') == ref.identity
                 and metadata.get('institution_id') == row.get('institution_id')
                 and metadata.get('template_id') == row.get('template_id'))
        if valid:
            graph.add(tx, ref, 'startup_funding',
                      'InstitutionGrowthSystem.validate: reciprocal startup transaction + ledger replay')
            graph.add(ref, account, 'registered_account',
                      'InstitutionGrowthSystem.validate: canonical account and zero baseline')
            graph.add(ref, employment, 'registered_employment',
                      'InstitutionGrowthSystem.validate: reciprocal employee, role, account, start day')
            if location_binding and location and complete(loc, LocationActivationRecord) and active(loc) and loc.get('location_id') == row.get('location_id') and loc['activation_day'] <= row['review_day']:
                valid_formations.add(ref)
        else:
            graph.unknown(ref, ledger_error or 'formation_economy_missing_or_mismatched')
    by_location = {}
    for occurrence in index.of_type('occurrence'):
        event = index.row(occurrence)
        by_location.setdefault(event.get('location_id'), []).append(occurrence)
    for formation in index.of_type('institution'):
        row = index.row(formation)
        if len(by_location.get(row.get('location_id'), [])) > 64:
            graph.unknown(formation, 'occurrence_associations_bounded')
        for occurrence in by_location.get(row.get('location_id'), [])[:64]:
            event = index.row(occurrence)
            if integer(event.get('day')) and integer(row.get('review_day')) and event['day'] < row['review_day']:
                graph.associations.add(EvidenceAssociation(occurrence, formation, 'same_location_prior_occurrence_not_eligibility_proof'))
    productions_by_recipe = {}
    for production in index.of_type('production'):
        productions_by_recipe.setdefault(index.row(production).get('recipe_id'), []).append(production)
    for ref in index.of_type('commerce'):
        row = index.row(ref)
        graph.unknown(ref, 'commerce_readiness_witness_not_persisted')
        formation = index.get('institution', row.get('institution_formation_id'))
        parent = index.row(formation)
        if not (complete(row, CommerceActivationRecord) and active(row) and formation in valid_formations
                and parent['activation_day'] < row['review_day']
                and all(row.get(child) == parent.get(field) for child, field in (
                    ('institution_id', 'institution_id'), ('location_id', 'location_id'),
                    ('location_activation_id', 'location_activation_id'),
                    ('operator_agent_id', 'employee_agent_id'), ('operator_employment_id', 'employment_id'),
                    ('institution_account_id', 'employer_account_id')))):
            graph.unknown(ref, 'commerce_parent_missing_or_mismatched')
            continue
        sequence = re.fullmatch(r'commerce-activation:(\d{4,})', ref.identity)
        inventory, seller, recipe = (index.get(kind, row.get(field)) for kind, field in (
            ('inventory', 'inventory_id'), ('seller', 'seller_id'), ('recipe', 'recipe_id')))
        inv, sel, rec = index.row(inventory), index.row(seller), index.row(recipe)
        initial = save.get('materials', {}).get('initial_quantities', {})
        valid = (sequence and row.get('inventory_id') == f'inventory:institution:{sequence.group(1)}'
                 and row.get('seller_id') == f'seller:institution:{sequence.group(1)}'
                 and inventory and seller and recipe and isinstance(initial, dict)
                 and initial.get(inventory.identity) == {}
                 and inv.get('owner_type') == 'institution' and inv.get('owner_id') == row['institution_id']
                 and inv.get('account_id') == row['institution_account_id']
                 and inv.get('institution_id') == row['institution_id']
                 and all(item.get('commerce_activation_id') == ref.identity for item in (inv, sel, rec))
                 and sel.get('institution_id') == row['institution_id']
                 and sel.get('inventory_id') == inventory.identity and sel.get('account_id') == row['institution_account_id']
                 and sel.get('location_id') == row['location_id']
                 and sel.get('operator_employment_id') == row['operator_employment_id']
                 and rec.get('output_inventory_id') == inventory.identity
                 and rec.get('required_location_id') == row['location_id']
                 and rec.get('eligible_actor_ids') == [row['operator_agent_id']]
                 and rec.get('eligible_employment_ids') == [row['operator_employment_id']])
        if not valid:
            graph.unknown(ref, 'commerce_registry_missing_or_mismatched')
            continue
        graph.add(formation, ref, 'institution_commerce',
                  'SimulationEngine.validate_commerce_authorities: exact formation branch')
        for child in (inventory, seller, recipe):
            graph.add(ref, child, 'registered_commerce_resource',
                      'SimulationEngine.validate_commerce_authorities: reciprocal inventory/seller/recipe')
        for production in productions_by_recipe.get(recipe.identity, []):
            p = index.row(production)
            if material_valid and p.get('recipe_id') == recipe.identity:
                if integer(p.get('day')) and p['day'] >= row['activation_day'] and p.get('inventory_id') == inventory.identity:
                    graph.add(recipe, production, 'authorized_recipe',
                              'SimulationEngine.validate_commerce_authorities: recipe, inventory, activation day')
                else:
                    graph.unknown(production, 'production_predates_commerce_or_wrong_inventory')
