from types import SimpleNamespace

from src.town.town_arc import TownArc
from src.agents.agent import Agent
from src.agents.memory import Memory
from src.agents.relationships import RelationshipManager
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.simulation.state import SimulationState
from src.agents.intent import AgentIntent
from src.town.daily_event import DailyEvent

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
    agent.get_relationship_state("Ethan").apply(
        {"trust": 0.2, "helpfulness": 0.3}, day=2
    )

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
    assert loaded_agent["relationship_states"]["Ethan"]["trust"] == 0.2
    assert loaded_agent["relationship_states"]["Ethan"]["helpfulness"] == 0.3
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

def test_engine_reconstructs_memory_archive_from_saved_state(memory_factory):
    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )

    active_memory = memory_factory(
        day=3,
        hour=18,
        description="Active memory.",
        participants=["Maya"],
        location="library",
        importance=3,
        sentiment=0,
        tags=["active"],
    )

    archived_memory = memory_factory(
        day=1,
        hour=8,
        description="Archived memory.",
        participants=["Maya"],
        location="market",
        importance=1,
        sentiment=0,
        tags=["archived"],
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
                "goals": [],
                "needs": {"social": 50, "wealth": 50, "knowledge": 50},
                "memory": [active_memory.to_dict()],
                "memory_archive": [archived_memory.to_dict()],
                "memory_summary": "",
                "recent_topics": [],
                "relationships": {},
                "current_activity": "idle",
                "current_activity_reason": "",
                "current_activity_tags": [],
            }
        ],
        "relationship_scores": {},
    }

    agents = engine.load_agents_from_state(saved_state)
    agent = agents[0]

    assert len(agent.memory) == 1
    assert len(agent.memory_archive) == 1
    assert agent.memory[0].description == "Active memory."
    assert agent.memory_archive[0].description == "Archived memory."

def test_loaded_state_resumes_after_saved_hour(monkeypatch):
    from src.llm.client import FakeLLMClient
    from src.simulation.engine import SimulationEngine

    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )

    engine.start_day = 3
    engine.start_hour = 18

    ticks = []

    def fake_run_tick(day, hour):
        ticks.append((day, hour))

    def fake_save(
        engine_arg,
        day,
        hour,
        day_complete=False,
    ):
        pass

    monkeypatch.setattr(engine, "run_tick", fake_run_tick)
    monkeypatch.setattr(engine.state, "save", fake_save)

    engine.run(days=1, hours=[8, 12, 18, 22])

    assert ticks == [(3, 22)]

def test_loaded_state_continues_to_next_day_when_saved_hour_is_last(
    monkeypatch,
):
    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )

    engine.start_day = 3
    engine.start_hour = 22
    engine.resume_day_complete = True

    ticks = []

    def fake_run_tick(day, hour):
        ticks.append((day, hour))

    def fake_save(
        engine_arg,
        day,
        hour,
        *,
        day_complete=False,
    ):
        pass

    monkeypatch.setattr(
        engine,
        "run_tick",
        fake_run_tick,
    )

    monkeypatch.setattr(
        engine.state,
        "save",
        fake_save,
    )

    engine.run(
        days=2,
        hours=[8, 12, 18, 22],
    )

    assert ticks == [
        (4, 8),
        (4, 12),
        (4, 18),
        (4, 22),
        (5, 8),
        (5, 12),
        (5, 18),
        (5, 22),
    ]
def test_save_preserves_run_continuity_fields(tmp_path):
    state = SimulationState(path=str(tmp_path / "save_state.json"))

    daily_event = DailyEvent(
        id="farmers_market",
        name="Farmers Market",
        description="Local vendors are setting up booths.",
        location_id="market",
        tags=["market", "community", "wealth"],
    )

    fake_engine = SimpleNamespace(
        agents=[],
        relationships=RelationshipManager(),
        current_daily_event=daily_event,
        daily_event_history=[
            {
                "day": 1,
                "id": "farmers_market",
                "name": "Farmers Market",
            }
        ],
        recent_dialogues=["the town feels busy today."],
        recent_actions=["chat"],
        activity_records=[
            {
                "type": "activity",
                "day": 1,
                "hour": 8,
                "agent": "Maya",
                "activity_id": "attend_event",
                "activity_name": "Attend Farmers Market",
                "location": "market",
                "reason": "Maya is interested in today's event.",
                "tags": ["event", "farmers_market"],
            }
        ],
    )

    state.save(fake_engine, current_day=1, current_hour=18)
    loaded = state.load()

    assert loaded["current_daily_event"]["id"] == "farmers_market"
    assert loaded["current_daily_event"]["name"] == "Farmers Market"
    assert loaded["daily_event_history"] == [
        {
            "day": 1,
            "id": "farmers_market",
            "name": "Farmers Market",
        }
    ]
    assert loaded["recent_dialogues"] == ["the town feels busy today."]
    assert loaded["recent_actions"] == ["chat"]
    assert loaded["activity_records"][0]["activity_name"] == "Attend Farmers Market"


def test_engine_loads_run_continuity_from_saved_state():
    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )

    saved_state = {
        "current_daily_event": {
            "id": "farmers_market",
            "name": "Farmers Market",
            "description": "Local vendors are setting up booths.",
            "location_id": "market",
            "tags": ["market", "community", "wealth"],
        },
        "daily_event_history": [
            {
                "day": 1,
                "id": "farmers_market",
                "name": "Farmers Market",
            }
        ],
        "recent_dialogues": ["the town feels busy today."],
        "recent_actions": ["chat"],
        "activity_records": [
            {
                "type": "activity",
                "day": 1,
                "hour": 8,
                "agent": "Maya",
                "activity_id": "attend_event",
                "activity_name": "Attend Farmers Market",
                "location": "market",
                "reason": "Maya is interested in today's event.",
                "tags": ["event", "farmers_market"],
            }
        ],
    }

    engine.load_run_continuity_from_state(saved_state)

    assert engine.current_daily_event is not None
    assert engine.current_daily_event.id == "farmers_market"
    assert engine.current_daily_event.name == "Farmers Market"
    assert engine.daily_event_history[0]["id"] == "farmers_market"
    assert engine.recent_dialogues == ["the town feels busy today."]
    assert engine.recent_actions == ["chat"]
    assert engine.activity_records[0]["activity_name"] == "Attend Farmers Market"


def test_loaded_state_reuses_saved_daily_event_for_remaining_hours(monkeypatch):
    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )

    saved_event = DailyEvent(
        id="farmers_market",
        name="Farmers Market",
        description="Local vendors are setting up booths.",
        location_id="market",
        tags=["market", "community", "wealth"],
    )

    engine.start_day = 1
    engine.start_hour = 18
    engine.current_daily_event = saved_event
    engine.daily_event_history = [
        {
            "day": 1,
            "id": "farmers_market",
            "name": "Farmers Market",
        }
    ]

    ticks = []

    def fake_run_tick(day, hour):
        ticks.append((day, hour))

    def fake_save(
        engine_arg,
        day,
        hour,
        day_complete=False,
    ):
        pass

    def fail_if_called(day):
        raise AssertionError("Day-start logic should not rerun when resuming saved day.")

    monkeypatch.setattr(engine, "run_tick", fake_run_tick)
    monkeypatch.setattr(engine.state, "save", fake_save)
    monkeypatch.setattr(engine, "update_town_arcs", fail_if_called)
    monkeypatch.setattr(engine, "update_agent_intents", fail_if_called)

    engine.run(days=1, hours=[8, 12, 18, 22])

    assert ticks == [(1, 22)]
    assert engine.current_daily_event.id == "farmers_market"
    assert engine.daily_event_history == [
        {
            "day": 1,
            "id": "farmers_market",
            "name": "Farmers Market",
        }
    ]
