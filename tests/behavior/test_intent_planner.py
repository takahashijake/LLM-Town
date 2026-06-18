from src.behavior.intent_planner import IntentPlanner
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


def build_engine():
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )


def get_agent(engine, name):
    return next(agent for agent in engine.agents if agent.name == name)


def test_negative_relationship_creates_repair_intent():
    engine = build_engine()
    planner = IntentPlanner()

    maya = get_agent(engine, "Maya")
    engine.relationships.change_score("Maya", "Carlos", -3)

    intent = planner.create_intent_for_agent(
        agent=maya,
        engine=engine,
        current_day=2,
    )

    assert intent.intent_type == "repair_relationship"
    assert intent.target_agent == "Carlos"


def test_positive_relationship_creates_build_friendship_intent():
    engine = build_engine()
    planner = IntentPlanner()

    maya = get_agent(engine, "Maya")
    engine.relationships.change_score("Maya", "Lena", 4)

    intent = planner.create_intent_for_agent(
        agent=maya,
        engine=engine,
        current_day=2,
    )

    assert intent.intent_type == "build_friendship"
    assert intent.target_agent == "Lena"


def test_knowledge_need_creates_investigate_intent_when_no_strong_relationships():
    engine = build_engine()
    planner = IntentPlanner()

    maya = get_agent(engine, "Maya")
    maya.needs = {
        "social": 80,
        "knowledge": 20,
        "wealth": 80,
    }

    intent = planner.create_intent_for_agent(
        agent=maya,
        engine=engine,
        current_day=2,
    )

    assert intent.intent_type == "investigate"
    assert intent.target_location == "library"