from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def build_engine():
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )


def test_calculate_relationship_change_combines_action_and_drift(monkeypatch):
    engine = build_engine()

    monkeypatch.setattr(
        engine,
        "get_relationship_change",
        lambda relationship_label: 1,
    )

    change = engine.calculate_relationship_change(
        action="compliment",
        old_relationship_label="neutral",
    )

    assert change == 2


def test_calculate_relationship_change_allows_chat_drift(monkeypatch):
    engine = build_engine()

    monkeypatch.setattr(
        engine,
        "get_relationship_change",
        lambda relationship_label: -1,
    )

    change = engine.calculate_relationship_change(
        action="chat",
        old_relationship_label="neutral",
    )

    assert change == -1


def test_calculate_relationship_change_clamps_high(monkeypatch):
    engine = build_engine()

    monkeypatch.setattr(
        engine,
        "get_relationship_change",
        lambda relationship_label: 5,
    )

    change = engine.calculate_relationship_change(
        action="apologize",
        old_relationship_label="tense",
    )

    assert change == 3


def test_calculate_relationship_change_clamps_low(monkeypatch):
    engine = build_engine()

    monkeypatch.setattr(
        engine,
        "get_relationship_change",
        lambda relationship_label: -5,
    )

    change = engine.calculate_relationship_change(
        action="insult",
        old_relationship_label="neutral",
    )

    assert change == -3