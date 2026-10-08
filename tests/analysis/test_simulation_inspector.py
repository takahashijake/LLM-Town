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
    b["economy"]["ledger"][0]["amount"] += 1
    report = compare(a, b)
    assert not report["sources"]["ledger"]["same_projection"]
    assert report["sources"]["institutions"]["same_projection"]
    assert a["economy"]["ledger"][0]["amount"] == 50

def test_bound_and_unknown_source():
    with pytest.raises(ValueError):
        timeline(fixture(), limit=1001)
    with pytest.raises(ValueError):
        timeline(fixture(), kinds={"made_up"})
    with pytest.raises(ValueError):
        inspect(fixture(), scope="institution")


def test_real_persisted_schema_projects_ledger_and_occurrences(tmp_path):
    from src.llm.client import FakeLLMClient
    from src.simulation.engine import SimulationEngine
    from src.analysis.simulation_inspector import SOURCES, _records

    engine = SimulationEngine(
        'data/agents.json', 'data/locations.json', llm_client=FakeLLMClient(),
        state_path=tmp_path / 'save.json', logs_dir=tmp_path / 'logs',
    )
    engine.economy.transfer(
        'account:agent:agent_001', 'account:agent:agent_002', 1,
        day=1, hour=8, transaction_type='test', reason='schema contract',
    )
    engine.state.save(engine, 1, 8)
    save = json.loads((tmp_path / 'save.json').read_text())
    for kind, path in SOURCES.items():
        node = save
        for component in path:
            assert component in node, (kind, path)
            node = node[component]
        assert isinstance(node, list), (kind, path)
    rows = _records(save, SOURCES['ledger'])
    assert rows == engine.economy.to_dict()['ledger']
    assert timeline(save, kinds={'ledger'})['total'] == 1
    changed = copy.deepcopy(save)
    changed['economy']['ledger'][0]['amount'] += 1
    assert not compare(save, changed)['sources']['ledger']['same_projection']


def test_documented_cli_runs_without_pythonpath(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys

    path = tmp_path / 'save.json'
    path.write_text(json.dumps(fixture()))
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    script = Path(__file__).resolve().parents[2] / 'scripts/inspect_town.py'
    result = subprocess.run([sys.executable, str(script), 'timeline', str(path)],
                            cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['total'] == 2
