from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.agents.relationships import RelationshipManager


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
        old_relationship_score=0,
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
        old_relationship_score=0,
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
        old_relationship_score=4,
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
        old_relationship_score=0,
    )

    assert change == -3

def test_positive_change_blocked_when_already_close_friends(monkeypatch):
    engine = build_engine()

    monkeypatch.setattr(
        engine,
        "get_relationship_change",
        lambda relationship_label: 1,
    )

    change = engine.calculate_relationship_change(
        action="cooperate",
        old_relationship_label="close friends",
        old_relationship_score=9,
    )

    assert change == 0


def test_enemy_chat_does_not_repair_relationship(monkeypatch):
    engine = build_engine()

    monkeypatch.setattr(
        engine,
        "get_relationship_change",
        lambda relationship_label: 1,
    )

    change = engine.calculate_relationship_change(
        action="chat",
        old_relationship_label="enemies",
        old_relationship_score=-9,
    )

    assert change == 0


def test_non_chat_action_can_still_repair_bad_relationship(monkeypatch):
    engine = build_engine()

    monkeypatch.setattr(
        engine,
        "get_relationship_change",
        lambda relationship_label: 0,
    )

    change = engine.calculate_relationship_change(
        action="apologize",
        old_relationship_label="enemies",
        old_relationship_score=-9,
    )

    assert change > 0

def test_relationship_decay_moves_positive_score_toward_neutral(monkeypatch):
    relationships = RelationshipManager()
    relationships.change_score("Maya", "Ethan", 5)

    monkeypatch.setattr("random.random", lambda: 0.0)

    relationships.decay_all_relationships(probability=1.0)

    assert relationships.get_score("Maya", "Ethan") == 4


def test_relationship_decay_moves_negative_score_toward_neutral(monkeypatch):
    relationships = RelationshipManager()
    relationships.change_score("Maya", "Ethan", -5)

    monkeypatch.setattr("random.random", lambda: 0.0)

    relationships.decay_all_relationships(probability=1.0)

    assert relationships.get_score("Maya", "Ethan") == -4

def test_repeated_dialogue_uses_fallback():
    engine = build_engine()

    maya = next(agent for agent in engine.agents if agent.name == "Maya")
    lena = next(agent for agent in engine.agents if agent.name == "Lena")

    repeated = "This place has had a lot going on today."
    engine.remember_dialogue(repeated)

    fallback = engine.get_non_repeated_fallback_dialogue(
        speaker=maya,
        listener=lena,
        relationship_label="neutral",
    )

    assert fallback != repeated

def test_fallback_dialogue_uses_activity_context():
    engine = build_engine()

    maya = next(agent for agent in engine.agents if agent.name == "Maya")
    lena = next(agent for agent in engine.agents if agent.name == "Lena")

    maya.current_activity = "Investigate a possible story"
    maya.occupation = "local journalist"

    fallback = engine.get_non_repeated_fallback_dialogue(
        speaker=maya,
        listener=lena,
        relationship_label="neutral",
        location_id="library",
        suggested_action="chat",
    )

    assert "investigate a possible story" in fallback.lower() or "library" in fallback.lower()
    assert fallback not in {
        "There is a lot happening around town today.",
        "This place feels more active than usual.",
        "The town has felt lively lately.",
    }


def test_fallback_dialogue_respects_suggested_action():
    engine = build_engine()

    maya = next(agent for agent in engine.agents if agent.name == "Maya")
    lena = next(agent for agent in engine.agents if agent.name == "Lena")

    maya.current_activity = "Organize community support"

    fallback = engine.get_non_repeated_fallback_dialogue(
        speaker=maya,
        listener=lena,
        relationship_label="friendly",
        location_id="town_square",
        suggested_action="offer_help",
    )

    assert "help" in fallback.lower()