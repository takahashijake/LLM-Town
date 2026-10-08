import copy
import json

import pytest

from src.analysis.simulation_inspector import compare, inspect, timeline

def fixture():
    return {
        "economy": {"ledger": [
            {"id": "transaction-1", "day": 2, "hour": 8, "amount": 50,
             "from_account_id": "treasury", "to_account_id": "resident-1",
             "metadata": {"secret": "forbidden"}},
        ]},
        "institution_growth": {"formation_records": [
            {"id": "formation-1", "day": 3, "institution_id": "garden",
             "description": "private narrative"},
        ]},
        "agents": [{"id": "resident-1", "memory": [{"text": "PRIVATE"}],
                    "reputation_beliefs": {"resident-2": {"secret": "PRIVATE"}}}],
        "recent_dialogues": [{"text": "PRIVATE"}],
        "growth_proposals": {"records": [{"text": "UNTRUSTED"}]},
    }

def test_read_only_repetition_and_unchanged_inputs():
    state = fixture()
    original = copy.deepcopy(state)
    assert inspect(state) == inspect(state)
    assert timeline(state) == timeline(state)
    assert state == original

def test_private_and_llm_material_excluded():
    encoded = json.dumps(inspect(fixture()))
    for forbidden in ("PRIVATE", "UNTRUSTED", "forbidden", "private narrative"):
        assert forbidden not in encoded

def test_chronology_provenance_and_pagination():
    first = timeline(fixture(), limit=1)
    assert first["total"] == 2
    assert first["events"][0]["authority_id"] == "transaction-1"
    assert first["events"][0]["provenance"] == "authoritative_history"
    second = timeline(fixture(), limit=1, offset=1)
    assert second["events"][0]["authority_id"] == "formation-1"

def test_exact_identity_not_substring():
    state = fixture()
    assert inspect(state, scope="resident", identity="resident-1")["matched"] == 1
    assert inspect(state, scope="resident", identity="resident")["matched"] == 0

def test_comparison_detects_change_without_mutation():
    a = fixture()
    b = copy.deepcopy(a)
    b["economy"]["transactions"][0]["amount"] += 1
    report = compare(a, b)
    assert not report["sources"]["ledger"]["same_projection"]
    assert report["sources"]["institutions"]["same_projection"]
    assert a["economy"]["transactions"][0]["amount"] == 50

def test_bound_and_unknown_source():
    with pytest.raises(ValueError):
        timeline(fixture(), limit=1001)
    with pytest.raises(ValueError):
        timeline(fixture(), kinds={"made_up"})
    with pytest.raises(ValueError):
        inspect(fixture(), scope="institution")
