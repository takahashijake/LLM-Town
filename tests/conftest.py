import pytest

from src.agents.agent import Agent
from src.agents.memory import Memory
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


@pytest.fixture
def location_ids():
    return ["town_square", "cafe", "library", "market"]


@pytest.fixture
def base_agent():
    return Agent(
        id="agent_test",
        name="Test Agent",
        personality="curious",
        occupation="unemployed",
        location_id="cafe",
        goals=[],
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
    )


@pytest.fixture
def memory_factory():
    def make_memory(
        *,
        day=1,
        hour=8,
        memory_type="conversation",
        description="Test memory.",
        participants=None,
        location="cafe",
        importance=1,
        sentiment=0,
        tags=None,
    ):
        return Memory(
            day=day,
            hour=hour,
            type=memory_type,
            description=description,
            participants=participants or [],
            location=location,
            importance=importance,
            sentiment=sentiment,
            tags=tags or [],
        )

    return make_memory


@pytest.fixture
def fake_engine():
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )