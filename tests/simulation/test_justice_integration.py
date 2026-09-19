import json

import pytest

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.justice import JusticeError
from tests.systems.test_justice import witnessed_case


def build(tmp_path, load=False):
    return SimulationEngine("data/agents.json", "data/locations.json", load_state=load,
                            llm_client=FakeLLMClient(), state_path=tmp_path / "state.json",
                            logs_dir=tmp_path / "logs")


def test_engine_persistence_round_trip_and_resume_guards(tmp_path):
    engine = build(tmp_path)
    _incident, _direct, case = witnessed_case(engine)
    decision = engine.justice.adjudicate(case_id=case.id, reviewer_agent_id="agent_001", day=2, hour=16, event_key="decide")
    engine.justice.apply_consequence(adjudication_id=decision.id, day=2, hour=17, event_key="consequence")
    expected = (engine.justice.to_dict(), engine.materials.to_dict(), engine.economy.to_dict())
    engine.state.save(engine, 2, 17)
    resumed = build(tmp_path, True)
    assert (resumed.justice.to_dict(), resumed.materials.to_dict(), resumed.economy.to_dict()) == expected
    counts = (len(resumed.justice.adjudications), len(resumed.justice.restitutions), len(resumed.justice.consequences), len(resumed.materials.inventory_transfers))
    with pytest.raises(JusticeError):
        resumed.justice.adjudicate(case_id=case.id, reviewer_agent_id="agent_001", day=2, hour=18, event_key="decide")
    with pytest.raises(JusticeError):
        resumed.justice.apply_consequence(adjudication_id=decision.id, day=2, hour=18, event_key="consequence")
    assert counts == (len(resumed.justice.adjudications), len(resumed.justice.restitutions), len(resumed.justice.consequences), len(resumed.materials.inventory_transfers))


def test_save_without_justice_loads_empty_configured_layer(tmp_path):
    engine = build(tmp_path)
    engine.state.save(engine, 1, 0)
    data = json.loads((tmp_path / "state.json").read_text())
    data.pop("justice")
    (tmp_path / "state.json").write_text(json.dumps(data))
    resumed = build(tmp_path, True)
    assert resumed.justice.cases == []
    assert resumed.justice.rule_version == "theft-direct-eyewitness-v1"
