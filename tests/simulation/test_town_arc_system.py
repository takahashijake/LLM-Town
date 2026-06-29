from types import SimpleNamespace

from src.agents.agent import Agent
from src.simulation.town_arc_system import TownArcSystem
from src.town.town_arc import TownArc


def build_agent(
    name: str,
    location_id: str = "cafe",
    current_activity_tags=None,
) -> Agent:
    return Agent(
        id=f"agent_{name.lower()}",
        name=name,
        personality="curious",
        occupation="resident",
        location_id=location_id,
        goals=[],
        needs={
            "social": 50,
            "wealth": 50,
            "knowledge": 50,
        },
        current_activity_tags=current_activity_tags or [],
    )


def build_arc(
    *,
    arc_id: str = "arc_market_pressure_day_1",
    name: str = "Market Pressure",
    status: str = "active",
    location_id: str | None = "market",
    involved_agents=None,
    tags=None,
    tension: int = 2,
    progress: int = 0,
    created_day: int = 1,
    updated_day: int = 1,
    resolved_day: int | None = None,
) -> TownArc:
    return TownArc(
        id=arc_id,
        name=name,
        description="Test town arc.",
        status=status,
        location_id=location_id,
        involved_agents=involved_agents or [],
        tags=tags or ["market", "business", "wealth"],
        tension=tension,
        progress=progress,
        created_day=created_day,
        updated_day=updated_day,
        resolved_day=resolved_day,
    )


def build_system(town_arcs=None):
    town_arcs = town_arcs or []
    town_arc_change_records = []

    system = TownArcSystem(
        town_arcs=town_arcs,
        town_arc_change_records=town_arc_change_records,
    )

    return system, town_arcs, town_arc_change_records


def test_create_town_arc_from_market_daily_event():
    system, _town_arcs, _records = build_system()

    daily_event = SimpleNamespace(
        tags=["market", "business"],
    )

    arc = system.create_town_arc_from_daily_event(
        day=3,
        daily_event=daily_event,
    )

    assert arc is not None
    assert arc.id == "arc_market_pressure_day_3"
    assert arc.name == "Market Pressure"
    assert arc.status == "active"
    assert arc.location_id == "market"
    assert arc.tags == ["market", "business", "wealth"]
    assert arc.tension == 2
    assert arc.progress == 0
    assert arc.created_day == 3
    assert arc.updated_day == 3


def test_create_town_arc_from_daily_event_prevents_duplicate_active_arc():
    existing_arc = build_arc(name="Market Pressure")
    system, _town_arcs, _records = build_system([existing_arc])

    daily_event = SimpleNamespace(
        tags=["market", "business"],
    )

    arc = system.create_town_arc_from_daily_event(
        day=4,
        daily_event=daily_event,
    )

    assert arc is None


def test_create_town_arc_from_community_daily_event():
    system, _town_arcs, _records = build_system()

    daily_event = SimpleNamespace(
        tags=["community", "volunteer"],
    )

    arc = system.create_town_arc_from_daily_event(
        day=2,
        daily_event=daily_event,
    )

    assert arc is not None
    assert arc.id == "arc_community_project_day_2"
    assert arc.name == "Community Project"
    assert arc.location_id == "town_square"
    assert arc.tags == ["community", "volunteer", "social"]
    assert arc.tension == 1
    assert arc.progress == 0


def test_create_town_arc_from_learning_daily_event():
    system, _town_arcs, _records = build_system()

    daily_event = SimpleNamespace(
        tags=["learning", "rules"],
    )

    arc = system.create_town_arc_from_daily_event(
        day=5,
        daily_event=daily_event,
    )

    assert arc is not None
    assert arc.id == "arc_public_questions_day_5"
    assert arc.name == "Public Questions"
    assert arc.location_id == "library"
    assert arc.tags == ["knowledge", "rules", "learning"]
    assert arc.tension == 2
    assert arc.progress == 0


def test_get_active_town_arcs_excludes_resolved_arcs():
    active_arc = build_arc(
        arc_id="active_arc",
        name="Market Pressure",
        status="active",
        resolved_day=None,
    )
    resolved_arc = build_arc(
        arc_id="resolved_arc",
        name="Community Project",
        status="resolved",
        location_id="town_square",
        tags=["community", "volunteer", "social"],
        resolved_day=4,
    )

    system, _town_arcs, _records = build_system([active_arc, resolved_arc])

    active_arcs = system.get_active_town_arcs()

    assert active_arcs == [active_arc]


def test_should_create_town_arc_returns_true_when_no_active_arcs():
    system, _town_arcs, _records = build_system()

    assert system.should_create_town_arc(day=1)


def test_should_create_town_arc_returns_false_when_two_active_arcs():
    first_arc = build_arc(
        arc_id="arc_1",
        name="Market Pressure",
    )
    second_arc = build_arc(
        arc_id="arc_2",
        name="Community Project",
        location_id="town_square",
        tags=["community", "volunteer", "social"],
    )

    system, _town_arcs, _records = build_system([first_arc, second_arc])

    assert not system.should_create_town_arc(day=3)


def test_should_create_town_arc_uses_random_when_one_active_arc(monkeypatch):
    existing_arc = build_arc()
    system, _town_arcs, _records = build_system([existing_arc])

    monkeypatch.setattr("random.random", lambda: 0.10)

    assert system.should_create_town_arc(day=2)

    monkeypatch.setattr("random.random", lambda: 0.90)

    assert not system.should_create_town_arc(day=2)


def test_update_town_arcs_creates_new_arc_and_remembers_for_all_agents():
    system, town_arcs, _records = build_system()

    agents = [
        build_agent("Maya"),
        build_agent("Ethan"),
        build_agent("Lena"),
    ]

    daily_event = SimpleNamespace(
        tags=["community", "volunteer"],
    )

    system.update_town_arcs(
        day=1,
        current_daily_event=daily_event,
        agents=agents,
    )

    assert len(town_arcs) == 1

    new_arc = town_arcs[0]

    assert new_arc.name == "Community Project"
    assert new_arc.location_id == "town_square"

    for agent in agents:
        assert any(
            memory.type == "town_arc"
            and "Town arc created: Community Project" in memory.description
            and "created" in memory.tags
            for memory in agent.memory
        )


def test_update_town_arcs_resolves_old_progressed_arc_and_remembers_for_all_agents(monkeypatch):
    arc = build_arc(
        name="Community Project",
        location_id="town_square",
        tags=["community", "volunteer", "social"],
        tension=1,
        progress=2,
        created_day=1,
        updated_day=1,
    )

    system, _town_arcs, _records = build_system([arc])

    agents = [
        build_agent("Maya"),
        build_agent("Ethan"),
    ]

    monkeypatch.setattr("random.choice", lambda choices: 0)

    system.update_town_arcs(
        day=4,
        current_daily_event=None,
        agents=agents,
    )

    assert arc.status == "resolved"
    assert arc.resolved_day == 4

    for agent in agents:
        assert any(
            memory.type == "town_arc"
            and "Town arc resolved: Community Project" in memory.description
            and "resolved" in memory.tags
            for memory in agent.memory
        )


def test_remember_town_arc_for_all_agents_created_reason_adds_memory_to_everyone():
    arc = build_arc(
        name="Market Pressure",
        location_id="market",
        tags=["market", "business", "wealth"],
    )

    system, _town_arcs, _records = build_system([arc])

    agents = [
        build_agent("Maya", location_id="cafe"),
        build_agent("Ethan", location_id="library"),
        build_agent("Lena", location_id="town_square"),
    ]

    system.remember_town_arc_for_all_agents(
        day=2,
        arc=arc,
        reason="created",
        agents=agents,
    )

    for agent in agents:
        assert len(agent.memory) == 1
        assert agent.memory[0].type == "town_arc"
        assert "created" in agent.memory[0].tags


def test_remember_town_arc_for_all_agents_updated_reason_only_adds_relevant_memories():
    arc = build_arc(
        name="Market Pressure",
        location_id="market",
        tags=["market", "business", "wealth"],
        involved_agents=["Carlos"],
    )

    system, _town_arcs, _records = build_system([arc])

    at_location = build_agent("Maya", location_id="market")
    matching_activity_tags = build_agent(
        "Ethan",
        location_id="library",
        current_activity_tags=["business"],
    )
    involved_agent = build_agent("Carlos", location_id="cafe")
    unrelated_agent = build_agent("Lena", location_id="library")

    agents = [
        at_location,
        matching_activity_tags,
        involved_agent,
        unrelated_agent,
    ]

    system.remember_town_arc_for_all_agents(
        day=3,
        arc=arc,
        reason="updated",
        agents=agents,
    )

    assert len(at_location.memory) == 1
    assert len(matching_activity_tags.memory) == 1
    assert len(involved_agent.memory) == 1
    assert len(unrelated_agent.memory) == 0


def test_create_town_arc_memory_returns_expected_memory():
    arc = build_arc(
        name="Market Pressure",
        location_id="market",
        tags=["market", "business", "wealth"],
        involved_agents=["Maya", "Ethan"],
        tension=3,
        progress=2,
    )

    system, _town_arcs, _records = build_system([arc])

    memory = system.create_town_arc_memory(
        day=5,
        arc=arc,
    )

    assert memory.day == 5
    assert memory.hour == 0
    assert memory.type == "town_arc"
    assert "Town arc: Market Pressure." in memory.description
    assert memory.participants == ["Maya", "Ethan"]
    assert memory.location == "market"
    assert memory.importance == 3
    assert memory.sentiment == 3
    assert memory.tags == [
        "town_arc",
        "arc_market_pressure_day_1",
        "market",
        "business",
        "wealth",
    ]


def test_get_relevant_town_arcs_for_context_filters_by_location_and_active_status():
    market_arc = build_arc(
        arc_id="market_arc",
        name="Market Pressure",
        location_id="market",
        tags=["market", "business", "wealth"],
    )
    library_arc = build_arc(
        arc_id="library_arc",
        name="Public Questions",
        location_id="library",
        tags=["knowledge", "rules", "learning"],
    )
    resolved_market_arc = build_arc(
        arc_id="resolved_market_arc",
        name="Old Market Issue",
        location_id="market",
        status="resolved",
        resolved_day=5,
    )

    system, _town_arcs, _records = build_system(
        [
            market_arc,
            library_arc,
            resolved_market_arc,
        ]
    )

    relevant_arcs = system.get_relevant_town_arcs_for_context("market")

    assert len(relevant_arcs) == 1
    assert relevant_arcs[0]["id"] == "market_arc"
    assert relevant_arcs[0]["name"] == "Market Pressure"
    assert relevant_arcs[0]["location_id"] == "market"
    assert relevant_arcs[0]["tags"] == ["market", "business", "wealth"]
    assert relevant_arcs[0]["tension"] == 2
    assert relevant_arcs[0]["progress"] == 0


def test_get_relevant_town_arcs_for_context_limits_results_to_two():
    first_arc = build_arc(
        arc_id="arc_1",
        name="Arc One",
        location_id=None,
    )
    second_arc = build_arc(
        arc_id="arc_2",
        name="Arc Two",
        location_id=None,
    )
    third_arc = build_arc(
        arc_id="arc_3",
        name="Arc Three",
        location_id=None,
    )

    system, _town_arcs, _records = build_system(
        [
            first_arc,
            second_arc,
            third_arc,
        ]
    )

    relevant_arcs = system.get_relevant_town_arcs_for_context("market")

    assert len(relevant_arcs) == 2
    assert relevant_arcs[0]["id"] == "arc_1"
    assert relevant_arcs[1]["id"] == "arc_2"


def test_apply_conversation_to_town_arcs_offer_help_advances_progress_and_reduces_tension(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    arc = build_arc(
        name="Market Pressure",
        location_id="market",
        tags=["market", "business", "wealth"],
        tension=2,
        progress=0,
    )

    system, _town_arcs, records = build_system([arc])

    speaker = build_agent("Maya", location_id="market")
    listener = build_agent("Ethan", location_id="market")

    system.apply_conversation_to_town_arcs(
        day=2,
        location_id="market",
        speaker=speaker,
        listener=listener,
        action="offer_help",
        conversation_tags=["conversation", "market"],
    )

    assert arc.progress == 1
    assert arc.tension == 1
    assert arc.updated_day == 2
    assert arc.involved_agents == ["Maya", "Ethan"]

    assert len(records) == 1
    assert records[0]["arc_id"] == arc.id
    assert records[0]["action"] == "offer_help"
    assert records[0]["old_progress"] == 0
    assert records[0]["new_progress"] == 1
    assert records[0]["old_tension"] == 2
    assert records[0]["new_tension"] == 1

    assert any(
        memory.type == "town_arc_participation"
        and "affected the town arc 'Market Pressure'" in memory.description
        and "offer_help" in memory.tags
        for memory in speaker.memory
    )
    assert any(
        memory.type == "town_arc_participation"
        and "affected the town arc 'Market Pressure'" in memory.description
        and "offer_help" in memory.tags
        for memory in listener.memory
    )

    log_path = tmp_path / "logs" / "town_arc_changes.jsonl"
    assert log_path.exists()
    assert "offer_help" in log_path.read_text()


def test_apply_conversation_to_town_arcs_argue_increases_tension(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    arc = build_arc(
        name="Market Pressure",
        location_id="market",
        tags=["market", "business", "wealth"],
        tension=2,
        progress=0,
    )

    system, _town_arcs, records = build_system([arc])

    speaker = build_agent("Maya", location_id="market")
    listener = build_agent("Ethan", location_id="market")

    system.apply_conversation_to_town_arcs(
        day=2,
        location_id="market",
        speaker=speaker,
        listener=listener,
        action="argue",
        conversation_tags=["conversation", "market"],
    )

    assert arc.progress == 0
    assert arc.tension == 3
    assert arc.updated_day == 2
    assert len(records) == 1
    assert records[0]["action"] == "argue"
    assert records[0]["new_tension"] == 3


def test_apply_conversation_to_town_arcs_ignores_irrelevant_location_and_tags(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    arc = build_arc(
        name="Market Pressure",
        location_id="market",
        tags=["market", "business", "wealth"],
        tension=2,
        progress=0,
    )

    system, _town_arcs, records = build_system([arc])

    speaker = build_agent("Maya", location_id="library")
    listener = build_agent("Ethan", location_id="library")

    system.apply_conversation_to_town_arcs(
        day=2,
        location_id="library",
        speaker=speaker,
        listener=listener,
        action="offer_help",
        conversation_tags=["conversation", "learning"],
    )

    assert arc.progress == 0
    assert arc.tension == 2
    assert arc.involved_agents == []
    assert records == []
    assert speaker.memory == []
    assert listener.memory == []


def test_adjust_action_weights_for_community_arc_boosts_helping_actions():
    arc = build_arc(
        name="Community Project",
        location_id="town_square",
        tags=["community", "volunteer", "social"],
    )

    system, _town_arcs, _records = build_system([arc])

    weights = {
        "chat": 3,
        "cooperate": 1,
        "offer_help": 1,
        "ask_for_help": 1,
    }

    adjusted = system.adjust_action_weights_for_town_arcs(
        weights=weights,
        location_id="town_square",
        conversation_tags=[],
    )

    assert adjusted["chat"] == 3
    assert adjusted["cooperate"] == 3
    assert adjusted["offer_help"] == 3
    assert adjusted["ask_for_help"] == 2
    assert weights["cooperate"] == 1


def test_adjust_action_weights_for_market_arc_boosts_market_pressure_actions():
    arc = build_arc(
        name="Market Pressure",
        location_id="market",
        tags=["market", "business", "wealth"],
    )

    system, _town_arcs, _records = build_system([arc])

    weights = {
        "chat": 3,
        "ask_for_help": 1,
        "share_rumor": 1,
        "argue": 1,
        "cooperate": 1,
    }

    adjusted = system.adjust_action_weights_for_town_arcs(
        weights=weights,
        location_id="market",
        conversation_tags=[],
    )

    assert adjusted["chat"] == 3
    assert adjusted["ask_for_help"] == 3
    assert adjusted["share_rumor"] == 2
    assert adjusted["argue"] == 2
    assert adjusted["cooperate"] == 2


def test_adjust_action_weights_for_learning_arc_boosts_question_actions():
    arc = build_arc(
        name="Public Questions",
        location_id="library",
        tags=["knowledge", "rules", "learning"],
    )

    system, _town_arcs, _records = build_system([arc])

    weights = {
        "chat": 3,
        "ask_for_help": 1,
        "cooperate": 1,
        "share_rumor": 1,
    }

    adjusted = system.adjust_action_weights_for_town_arcs(
        weights=weights,
        location_id="library",
        conversation_tags=[],
    )

    assert adjusted["chat"] == 3
    assert adjusted["ask_for_help"] == 3
    assert adjusted["cooperate"] == 2
    assert adjusted["share_rumor"] == 2