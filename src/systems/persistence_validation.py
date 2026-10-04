"""Exact persisted record shape checks, separate from configuration defaults."""
from __future__ import annotations

from dataclasses import fields


def require_record_fields(data: object, record_type: type) -> dict:
    """Persisted dataclasses must include even explicitly nullable fields."""
    expected = {field.name for field in fields(record_type)}
    if not isinstance(data, dict) or set(data) != expected:
        raise ValueError(f'{record_type.__name__} persisted record has invalid fields')
    return data


def require_sequence(sequences: list[int], next_sequence: int, label: str) -> None:
    """For retained complete histories, identities are contiguous and monotonic."""
    if (isinstance(next_sequence, bool) or not isinstance(next_sequence, int)
            or sorted(sequences) != list(range(1, len(sequences) + 1))
            or next_sequence != len(sequences) + 1):
        raise ValueError(f'{label} sequence is inconsistent')
