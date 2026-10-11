"""Explicit public projections of persisted authority, with no nested text."""
from __future__ import annotations

import re

SCHEMA_VERSION = 1
# Only explicitly admitted authoritative collections are inspected. No agent
# memory, journal, prompt, dialogue, belief or LLM proposal text enters reports.
SOURCES = {
    "relationship_events": ("relationship_events",),
    "reputation_updates": ("reputation_updates",),
    "ledger": ("economy", "ledger"),
    "employment": ("economy", "employments"),
    "exchanges": ("materials", "exchanges"),
    "inventory_transfers": ("materials", "inventory_transfers"),
    "production": ("materials", "production_records"),
    "consumption": ("materials", "consumptions"),
    "lot_movements": ("materials", "lot_movements"),
    "migrations": ("town_growth", "migration_records"),
    "locations": ("location_growth", "activation_records"),
    "occurrences": ("event_ecology", "occurrence_history"),
    "institutions": ("institution_growth", "formation_records"),
    "commerce": ("commerce_growth", "activation_records"),
    "commitments": ("commitments", "commitments"),
    "plans": ("plans", "plans"),
}
# Exclude free-text and nested belief fields, even if they appear on an
# authoritative record. Relationships among events use exact matching IDs.
ALLOWED_FIELDS = frozenset({
    "eligible_actor_ids", "project_id", "actor_id", "deadline_day", "resolution_day", "available_day",
    "activity_index", "execution_key", "source_project_id", "source_project_effect_id",
    "civic_execution_key", "civic_status",
    "id", "day", "hour", "tick", "sequence", "status", "event_key",
    "agent_id", "resident_id", "actor_id", "owner_id", "target_id",
    "source_id", "destination_id", "from_id", "to_id", "account_id",
    "from_account_id", "to_account_id", "sender_id", "receiver_id",
    "inventory_id", "from_inventory_id", "to_inventory_id",
    "lot_id", "lot_ids", "input_lot_ids", "output_lot_ids",
    "production_id", "transaction_id", "purchase_id", "exchange_id",
    "formation_id", "institution_id", "employment_id", "commitment_id",
    "plan_id", "goal_id", "location_id", "template_id", "recipe_id",
    "commerce_id", "seller_id", "goods_id", "good_id", "quantity",
    "amount", "price", "balance", "delta", "score_before", "score_after",
    "relationship_delta", "type", "kind", "action", "outcome",
    "reason_code", "activity_id", "event_id", "occurrence_id",
    "migration_id", "activation_id", "reference_id", "record_id",
    "payer_account_id", "payee_account_id", "counterparty_id",
    "source_account_id", "destination_account_id", "transaction_type",
    "source_inventory_id", "destination_inventory_id", "authorization_type",
    "authorization_id", "monetary_transaction_id", "inventory_transfer_id",
    "buyer_inventory_id", "seller_inventory_id", "buyer_account_id", "seller_account_id",
    "unit_price", "total_price", "location_activation_id", "employee_agent_id",
    "employer_account_id", "role_template_id", "review_day", "activation_day",
    "startup_transaction_id", "institution_formation_id", "operator_agent_id",
    "operator_employment_id", "institution_account_id", "purchase_activity_id",
    "upstream_seller_id", "created_day", "created_hour", "created_tick", "start_day",
    "resolution_day", "resolution_tick", "proposer_id", "commitment_type",
    "repair_of_commitment_id", "source_type", "plan_type", "completed_day",
    "source_commitment_id", "activity_event_key", "material_transfer_id",
    "step_id", "action_type", "execution_key", "movement_type", "parent_lot_ids",
    "origin_type", "origin_id", "initial_quantity", "owner_type", "active",
})
# These fields can contain prose even on authoritative rows and are never emitted.
TEXT_FIELDS = frozenset({"reason", "description", "text", "summary", "name", "content", "dialogue", "metadata"})


def safe_identity(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_:./|\-]{1,200}", value) is not None


def safe_scalar(value: object) -> bool:
    return type(value) in (int, float, bool) or safe_identity(value)


def safe_fields(row: dict) -> dict:
    result = {}
    for key in sorted(ALLOWED_FIELDS - TEXT_FIELDS):
        value = row.get(key)
        if safe_scalar(value) or value is None:
            if key in row:
                result[key] = value
        elif isinstance(value, (tuple, list)) and len(value) <= 64 and all(
            safe_scalar(x) for x in value
        ):
            result[key] = list(value)
    return result


def chronology(row: dict) -> tuple[int | None, int | None]:
    day = next((row[key] for key in ('day', 'activation_day', 'review_day',
                                    'created_day', 'start_day')
                if type(row.get(key)) is int), None)
    hour = next((row[key] for key in ('hour', 'tick', 'created_hour', 'created_tick')
                 if type(row.get(key)) is int), None)
    return day, hour
