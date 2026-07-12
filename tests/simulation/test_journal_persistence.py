from types import SimpleNamespace

from src.agents.agent import Agent
from src.agents.journal_entry import JournalEntry
from src.agents.relationships import RelationshipManager
from src.simulation.persistence import SimulationPersistence
from src.simulation.state import SimulationState


def build_engine(agent: Agent):
    return SimpleNamespace(
        current_daily_event=None,
        daily_event_history=[],
        recent_dialogues=[],
        recent_actions=[],
        activity_records=[],
        agents=[agent],
        relationships=RelationshipManager(),
        relationship_events=[],
        agent_intents={},
        intent_history=[],
        town_arcs=[],
    )


def build_agent() -> Agent:
    return Agent(
        id="maya",
        name="Maya",
        personality="curious",
        location_id="cafe",
        daily_journals=[
            JournalEntry(
                day=1,
                summary="Maya helped Ethan at the market.",
                important_people=["Ethan"],
                important_locations=["market"],
                important_events=["Market Festival"],
                relationship_changes={"Ethan": 4},
                completed_intents=["help: succeeded."],
                unresolved_topics=["vendor prices"],
                tags=["market", "help"],
            )
        ],
    )


def test_state_save_serializes_daily_journals(tmp_path):
    path = tmp_path / "save_state.json"
    state = SimulationState(path=str(path))
    engine = build_engine(build_agent())

    state.save(
        engine,
        current_day=1,
        current_hour=22,
    )

    saved = state.load()

    journals = saved["agents"][0]["daily_journals"]

    assert len(journals) == 1
    assert journals[0]["day"] == 1

    assert (
        journals[0]["summary"]
        == "Maya helped Ethan at the market."
    )

    assert journals[0]["important_people"] == [
        "Ethan"
    ]

    assert journals[0]["important_locations"] == [
        "market"
    ]

    assert journals[0]["relationship_changes"] == {
        "Ethan": 4
    }


def test_state_save_preserves_multiple_journals(tmp_path):
    agent = build_agent()

    agent.upsert_daily_journal(
        JournalEntry(
            day=2,
            summary="Maya followed up with Ethan.",
        )
    )

    path = tmp_path / "save_state.json"
    state = SimulationState(path=str(path))
    engine = build_engine(agent)

    state.save(
        engine,
        current_day=2,
        current_hour=22,
    )

    saved = state.load()

    journals = saved["agents"][0]["daily_journals"]

    assert [
        journal["day"]
        for journal in journals
    ] == [1, 2]


def test_persistence_reconstructs_daily_journals():
    agent = build_agent()

    saved_state = {
        "agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "personality": agent.personality,
                "location_id": agent.location_id,
                "occupation": agent.occupation,
                "goals": agent.goals,
                "needs": agent.needs,
                "memory": [],
                "memory_archive": [],
                "memory_summary": "",
                "recent_topics": [],
                "relationships": {},
                "current_activity": "idle",
                "current_activity_reason": "",
                "current_activity_tags": [],
                "daily_journals": [
                    journal.to_dict()
                    for journal in agent.daily_journals
                ],
            }
        ]
    }

    loaded_agents = (
        SimulationPersistence()
        .load_agents_from_state(saved_state)
    )

    assert len(loaded_agents) == 1
    assert len(loaded_agents[0].daily_journals) == 1

    loaded_journal = (
        loaded_agents[0].daily_journals[0]
    )

    assert isinstance(
        loaded_journal,
        JournalEntry,
    )

    assert loaded_journal == agent.daily_journals[0]


def test_persistence_preserves_all_journal_fields():
    original_journal = JournalEntry(
        day=4,
        summary="Maya investigated market prices.",
        important_people=["Ethan", "Carlos"],
        important_locations=["market", "cafe"],
        important_events=["Vendor dispute"],
        relationship_changes={
            "Ethan": 3,
            "Carlos": -2,
        },
        completed_intents=[
            "investigate: succeeded"
        ],
        unresolved_topics=[
            "vendor honesty"
        ],
        tags=[
            "market",
            "investigation",
        ],
    )

    saved_state = {
        "agents": [
            {
                "id": "maya",
                "name": "Maya",
                "personality": "curious",
                "location_id": "market",
                "memory": [],
                "memory_archive": [],
                "daily_journals": [
                    original_journal.to_dict()
                ],
            }
        ]
    }

    loaded_agent = (
        SimulationPersistence()
        .load_agents_from_state(saved_state)[0]
    )

    assert loaded_agent.daily_journals == [
        original_journal
    ]


def test_old_save_without_daily_journals_remains_compatible():
    saved_state = {
        "agents": [
            {
                "id": "maya",
                "name": "Maya",
                "personality": "curious",
                "location_id": "cafe",
                "memory": [],
                "memory_archive": [],
            }
        ]
    }

    loaded_agents = (
        SimulationPersistence()
        .load_agents_from_state(saved_state)
    )

    assert len(loaded_agents) == 1
    assert loaded_agents[0].daily_journals == []


def test_save_and_reload_round_trip_preserves_journals(
    tmp_path,
):
    original_agent = build_agent()
    engine = build_engine(original_agent)

    state = SimulationState(
        path=str(tmp_path / "save_state.json")
    )

    state.save(
        engine,
        current_day=1,
        current_hour=22,
    )

    saved_state = state.load()

    loaded_agents = (
        SimulationPersistence()
        .load_agents_from_state(saved_state)
    )

    assert len(loaded_agents) == 1

    assert (
        loaded_agents[0].daily_journals
        == original_agent.daily_journals
    )