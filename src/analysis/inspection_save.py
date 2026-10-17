"""Bounded, non-migrating JSON input for read-only investigation."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

MAX_SAVE_BYTES = 64 * 1024 * 1024
MAX_NODES = 2_000_000
MAX_DEPTH = 64
MAX_RECORDS = 200_000
MAX_REPORT_BYTES = 4 * 1024 * 1024


class InspectionError(ValueError):
    """A controlled diagnostic that never interpolates untrusted save contents."""


def _object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InspectionError('duplicate JSON object key')
        result[key] = value
    return result


def _constant(_value: str) -> None:
    raise InspectionError('non-finite JSON number')


def load_save(source: str | Path | dict) -> dict:
    """Read without changing inputs; reject resource excess and invalid JSON."""
    if not isinstance(source, (str, Path, dict)):
        raise InspectionError('inspection source must be a path or JSON object')
    if isinstance(source, dict):
        save = source
    else:
        try:
            with open(source, 'rb') as handle:
                payload = handle.read(MAX_SAVE_BYTES + 1)
            if len(payload) > MAX_SAVE_BYTES:
                raise InspectionError('save exceeds 64 MiB input limit')
            save = json.loads(payload, object_pairs_hook=_object,
                              parse_constant=_constant)
        except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
            raise InspectionError('cannot read a valid JSON save') from None
        except ValueError as error:
            if isinstance(error, InspectionError):
                raise
            raise InspectionError('invalid JSON value') from None
    if not isinstance(save, dict):
        raise InspectionError('simulation save must be a JSON object')
    stack = [(save, 0)]
    count = 0
    text_bytes = 0
    # Iterative validation also catches cyclic in-memory inputs by budget/depth.
    while stack:
        value, depth = stack.pop()
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise InspectionError('save exceeds structural input budget')
        if isinstance(value, dict):
            if any(type(key) is not str for key in value):
                raise InspectionError('save object keys must be strings')
            text_bytes += sum(len(key) for key in value)
            if count + len(stack) + len(value) > MAX_NODES:
                raise InspectionError('save exceeds structural input budget')
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            if len(value) > MAX_RECORDS:
                raise InspectionError('save collection exceeds record budget')
            if count + len(stack) + len(value) > MAX_NODES:
                raise InspectionError('save exceeds structural input budget')
            stack.extend((child, depth + 1) for child in value)
        elif type(value) is str:
            text_bytes += len(value)
            if len(value) > 1_000_000:
                raise InspectionError('save string exceeds input budget')
        elif type(value) is float:
            if not math.isfinite(value):
                raise InspectionError('non-finite save number')
        elif type(value) is int and value.bit_length() > 512:
            raise InspectionError('save integer exceeds input budget')
        elif value is not None and type(value) not in (int, bool):
            raise InspectionError('save contains a non-JSON value')
        if text_bytes > MAX_SAVE_BYTES:
            raise InspectionError('save exceeds text input budget')
    return save


def records(save: dict, path: tuple[str, ...]) -> list[dict]:
    """Absent legacy sections are empty; present malformed sections fail closed."""
    node: Any = save
    for key in path:
        if not isinstance(node, dict):
            raise InspectionError('invalid inspection section shape')
        if key not in node:
            return []
        node = node[key]
    if not isinstance(node, list) or any(not isinstance(row, dict) for row in node):
        raise InspectionError('inspection collection must contain objects')
    return node


def check_versions(save: dict) -> None:
    supported = {'economy': {1}, 'materials': {1, 2}, 'town_growth': {1},
                 'location_growth': {1}, 'event_ecology': {1},
                 'institution_growth': {1}, 'commerce_growth': {1},
                 'plans': set(range(1, 8)), 'growth_proposals': {1, 2, 3, 4}}
    for section, versions in supported.items():
        if section not in save:
            continue
        node = save[section]
        if section == 'growth_proposals' and node is None:
            continue
        if not isinstance(node, dict):
            raise InspectionError('invalid inspection section shape')
        if 'schema_version' in node and (
            type(node['schema_version']) is not int or node['schema_version'] not in versions
        ):
            raise InspectionError('unsupported persisted subsystem schema')


def bounded_report(report: dict) -> dict:
    """Independent serialization cap; callers can lower their query limit."""
    encoded = json.dumps(report, sort_keys=True, separators=(',', ':'))
    if len(encoded.encode('utf-8')) > MAX_REPORT_BYTES:
        raise InspectionError('report exceeds 4 MiB output limit; reduce query limit')
    return report
