from types import SimpleNamespace

from src.town.town_arc import TownArc
from src.agents.agent import Agent
from src.agents.memory import Memory
from src.agents.relationships import RelationshipManager
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.simulation.state import SimulationState
from src.agents.intent import AgentIntent

def test_load_returns_none_when_state_file_does_not_exist(tmp_path):
    state = SimulationState(path=str(tmp_path / "missing_state.json"))

    assert state.load() is None


def test_save_and_load_preserves_agent_state(tmp_path, memory_factory):
    state = SimulationState(path=str(tmp_path / "save_state.json"))

    memory = memory_factory(
        day=2,
        hour=12,
        description="Maya talked with Ethan about the market.",
        participants=["Maya", "Ethan"],
        location="market",
        importance=2,
        sentiment=1,
        tags=["conversation", "market", "chat"],
    )

    agent = Agent(
        id="agent_001",
        name="Maya",
        personality="curious",
        occupation="local journalist",
        location_id="market",
        goals=["learn town secrets"],
        needs={
            "social": 60,
            "wealth": 40,
            "knowledge": 70,
        },
        memory=[memory],
        recent_topics=["market"],
        relationships={"Ethan": 4},
        current_activity="Investigate a possible story",
        current_activity_reason="Maya is looking for town stories or rumors.",
        current_activity_tags=["journalism", "rumor", "knowledge"],
    )

    relationships = RelationshipManager()
    relationships.change_score("Maya", "Ethan", 4)

    fake_engine = SimpleNamespace(
        agents=[agent],
        relationships=relationships,
    )

    state.save(fake_engine, current_day=2, current_hour=12)
    loaded = state.load()

    assert loaded["current_day"] == 2
    assert loaded["current_hour"] == 12

    loaded_agent = loaded["agents"][0]

    assert loaded_agent["id"] == "agent_001"
    assert loaded_agent["name"] == "Maya"
    assert loaded_agent["personality"] == "curious"
    assert loaded_agent["occupation"] == "local journalist"
    assert loaded_agent["location_id"] == "market"
    assert loaded_agent["goals"] == ["learn town secrets"]
    assert loaded_agent["needs"] == {
        "social": 60,
        "wealth": 40,
        "knowledge": 70,
    }
    assert loaded_agent["recent_topics"] == ["market"]
    assert loaded_agent["relationships"] == {"Ethan": 4}
    assert loaded_agent["current_activity"] == "Investigate a possible story"
    assert loaded_agent["current_activity_reason"] == (
        "Maya is looking for town stories or rumors."
    )
    assert loaded_agent["current_activity_tags"] == [
        "journalism",
        "rumor",
        "knowledge",
    ]

    loaded_memory = loaded_agent["memory"][0]

    assert loaded_memory["description"] == (
        "Maya talked with Ethan about the market."
    )
    assert loaded_memory["participants"] == ["Maya", "Ethan"]
    assert loaded_memory["tags"] == ["conversation", "market", "chat"]

    assert loaded["relationship_scores"]["Ethan|Maya"] == 4


def test_engine_reconstructs_agents_from_saved_state(memory_factory):
    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )

    saved_state = {
        "current_day": 3,
        "current_hour": 18,
        "agents": [
            {
                "id": "agent_001",
                "name": "Maya",
                "personality": "curious",
                "occupation": "local journalist",
                "location_id": "library",
                "goals": ["learn town secrets"],
                "needs": {
                    "social": 55,
                    "wealth": 45,
                    "knowledge": 80,
                },
                "memory": [
                    memory_factory(
                        day=3,
                        hour=18,
                        description="Maya found a useful record.",
                        participants=["Maya"],
                        location="library",
                        importance=3,
                        sentiment=0,
                        tags=["learning"],
                    ).to_dict()
                ],
                "recent_topics": ["learning"],
                "relationships": {"Ethan": 2},
                "current_activity": "Check records for leads",
                "current_activity_reason": "Maya is looking for background information.",
                "current_activity_tags": ["journalism", "learning"],
            }
        ],
        "relationship_scores": {},
    }

    agents = engine.load_agents_from_state(saved_state)

    assert len(agents) == 1

    agent = agents[0]

    assert agent.name == "Maya"
    assert agent.occupation == "local journalist"
    assert agent.location_id == "library"
    assert agent.goals == ["learn town secrets"]
    assert agent.needs["knowledge"] == 80
    assert agent.recent_topics == ["learning"]
    assert agent.relationships == {"Ethan": 2}
    assert agent.current_activity == "Check records for leads"
    assert agent.current_activity_tags == ["journalism", "learning"]

    assert len(agent.memory) == 1
    assert isinstance(agent.memory[0], Memory)
    assert agent.memory[0].description == "Maya found a useful record."


def test_engine_reconstructs_relationship_scores_from_saved_state():
    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )

    saved_state = {
        "agents": [],
        "relationship_scores": {
            "Ethan|Maya": 5,
        },
    }

    engine.load_relationships_from_state(saved_state)

    assert engine.relationships.get_score("Maya", "Ethan") == 5
    assert engine.relationships.describe_relationship("Maya", "Ethan") == "friendly"

def test_save_preserves_agent_intents(tmp_path):
    state = SimulationState(path=str(tmp_path / "save_state.json"))

    intent = AgentIntent(
        agent_name="Maya",
        intent_type="build_friendship",
        target_agent="Lena",
        target_location=None,
        description="Maya wants to strengthen her bond with Lena.",
        created_day=1,
        expires_day=3,
        priority=4,
    )

    fake_engine = SimpleNamespace(
        agents=[],
        relationships=RelationshipManager(),
        relationship_events=[],
        agent_intents={"Maya": intent},
    )

    state.save(fake_engine, current_day=1, current_hour=8)
    loaded = state.load()

    assert loaded["agent_intents"]["Maya"]["intent_type"] == "build_friendship"
    assert loaded["agent_intents"]["Maya"]["target_agent"] == "Lena"

def test_state_saves_town_arcs(tmp_path):
    from src.simulation.state import SimulationState
    from tests.simulation.test_suggested_actions import build_engine

    engine = build_engine()
    engine.town_arcs = [
        TownArc(
            id="arc_market_pressure_day_1",
            name="Market Pressure",
            description="Residents are watching market prices.",
            status="active",
            location_id="market",
            involved_agents=[],
            tags=["market", "business"],
            tension=2,
            progress=1,
            created_day=1,
            updated_day=1,
        )
    ]

    state = SimulationState(path=str(tmp_path / "save_state.json"))
    state.save(engine, current_day=1, current_hour=8)

    loaded = state.load()

    assert loaded["town_arcs"][0]["id"] == "arc_market_pressure_day_1"
    assert loaded["town_arcs"][0]["status"] == "active"