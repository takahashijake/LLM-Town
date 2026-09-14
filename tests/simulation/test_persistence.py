from src.agents.memory import Memory
from src.agents.relationship_event import RelationshipEvent
from src.agents.relationships import RelationshipManager
from src.agents.intent import AgentIntent
from src.simulation.persistence import SimulationPersistence
from src.town.daily_event import DailyEvent
from src.town.town_arc import TownArc


def test_persistence_reconstructs_agents_from_saved_state():
    persistence = SimulationPersistence()

    saved_state = {
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
                    {
                        "day": 3,
                        "hour": 18,
                        "type": "conversation",
                        "description": "Maya found a useful record.",
                        "participants": ["Maya"],
                        "location": "library",
                        "importance": 3,
                        "sentiment": 0,
                        "tags": ["learning"],
                    }
                ],
                "memory_archive": [
                    {
                        "day": 1,
                        "hour": 8,
                        "type": "conversation",
                        "description": "Archived memory.",
                        "participants": ["Maya"],
                        "location": "market",
                        "importance": 1,
                        "sentiment": 0,
                        "tags": ["archived"],
                    }
                ],
                "memory_summary": "Maya remembers old market activity.",
                "recent_topics": ["learning"],
                "relationships": {"Ethan": 2},
                "current_activity": "Check records for leads",
                "current_activity_reason": "Maya is looking for background information.",
                "current_activity_tags": ["journalism", "learning"],
            }
        ]
    }

    agents = persistence.load_agents_from_state(saved_state)

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
    assert agent.memory_summary == "Maya remembers old market activity."

    assert len(agent.memory) == 1
    assert len(agent.memory_archive) == 1
    assert isinstance(agent.memory[0], Memory)
    assert agent.memory[0].description == "Maya found a useful record."
    assert agent.memory_archive[0].description == "Archived memory."
    assert agent.reputation_beliefs == {}


def test_persistence_reconstructs_relationship_scores_from_saved_state():
    persistence = SimulationPersistence()
    relationships = RelationshipManager()

    saved_state = {
        "relationship_scores": {
            "Ethan|Maya": 5,
        },
    }

    persistence.load_relationships_from_state(
        saved_state=saved_state,
        relationships=relationships,
    )

    assert relationships.get_score("Maya", "Ethan") == 5
    assert relationships.describe_relationship("Maya", "Ethan") == "friendly"


def test_persistence_reconstructs_agent_intents_from_saved_state():
    persistence = SimulationPersistence()

    saved_state = {
        "agent_intents": {
            "Maya": {
                "agent_name": "Maya",
                "intent_type": "build_friendship",
                "target_agent": "Lena",
                "target_location": None,
                "description": "Maya wants to strengthen her bond with Lena.",
                "created_day": 1,
                "expires_day": 3,
                "priority": 4,
                "status": "active",
                "id": "intent_001",
            }
        }
    }

    intents = persistence.load_agent_intents_from_state(saved_state)

    assert isinstance(intents["Maya"], AgentIntent)
    assert intents["Maya"].intent_type == "build_friendship"
    assert intents["Maya"].target_agent == "Lena"


def test_persistence_reconstructs_relationship_events_from_saved_state():
    persistence = SimulationPersistence()

    saved_state = {
        "relationship_events": [
            {
                "day": 2,
                "hour": 12,
                "agent_a": "Maya",
                "agent_b": "Ethan",
                "action": "offer_help",
                "relationship_change": 1,
                "relationship_score": 3,
                "relationship_label": "neutral",
                "description": "Maya helped Ethan at the library.",
                "location": "library",
                "tags": ["conversation", "help"],
                "conversation": "I can help you with that.",
                "id": "relationship_event_001",
            }
        ]
    }

    events = persistence.load_relationship_events_from_state(saved_state)

    assert len(events) == 1
    assert isinstance(events[0], RelationshipEvent)
    assert events[0].agent_a == "Maya"
    assert events[0].agent_b == "Ethan"
    assert events[0].location == "library"
    assert events[0].relationship_score == 3

def test_persistence_reconstructs_daily_event_and_run_continuity():
    persistence = SimulationPersistence()

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

    daily_event = persistence.load_daily_event_from_state(saved_state)
    continuity = persistence.load_run_continuity_from_state(saved_state)

    assert isinstance(daily_event, DailyEvent)
    assert daily_event.id == "farmers_market"

    assert continuity["current_daily_event"].id == "farmers_market"
    assert continuity["daily_event_history"][0]["id"] == "farmers_market"
    assert continuity["recent_dialogues"] == ["the town feels busy today."]
    assert continuity["recent_actions"] == ["chat"]
    assert continuity["activity_records"][0]["activity_name"] == "Attend Farmers Market"


def test_persistence_reconstructs_town_arcs_from_saved_state():
    persistence = SimulationPersistence()

    saved_state = {
        "town_arcs": [
            {
                "id": "arc_market_pressure_day_1",
                "name": "Market Pressure",
                "description": "Residents are watching market prices.",
                "status": "active",
                "location_id": "market",
                "involved_agents": [],
                "tags": ["market", "business"],
                "tension": 2,
                "progress": 1,
                "created_day": 1,
                "updated_day": 1,
                "resolved_day": None,
            }
        ]
    }

    town_arcs = persistence.load_town_arcs_from_state(saved_state)

    assert len(town_arcs) == 1
    assert isinstance(town_arcs[0], TownArc)
    assert town_arcs[0].id == "arc_market_pressure_day_1"
    assert town_arcs[0].status == "active"
