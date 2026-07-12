from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.simulation.simulation_loop import SimulationLoop


def build_engine():
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )


def test_get_active_hours_skips_completed_resume_hour():
    engine = build_engine()
    loop = SimulationLoop()

    engine.start_day = 2
    engine.start_hour = 12

    active_hours = loop.get_active_hours(
        engine=engine,
        day=2,
        hours=[8, 12, 18, 22],
    )

    assert active_hours == [18, 22]


def test_get_active_hours_returns_all_hours_for_non_resume_day():
    engine = build_engine()
    loop = SimulationLoop()

    engine.start_day = 2
    engine.start_hour = 12

    active_hours = loop.get_active_hours(
        engine=engine,
        day=3,
        hours=[8, 12, 18, 22],
    )

    assert active_hours == [8, 12, 18, 22]


def test_is_resuming_saved_day_requires_existing_daily_event():
    engine = build_engine()
    loop = SimulationLoop()

    engine.start_day = 2
    engine.start_hour = 12
    engine.current_daily_event = None

    assert not loop.is_resuming_saved_day(engine, day=2)


def test_create_daily_event_memory_uses_event_metadata():
    engine = build_engine()
    loop = SimulationLoop()

    event = engine.current_daily_event
    if event is None:
        from src.town.daily_event import choose_daily_event
        event = choose_daily_event()

    memory = loop.create_daily_event_memory(day=1, event=event)

    assert memory.day == 1
    assert memory.hour == 0
    assert memory.type == "daily_event"
    assert memory.location == event.location_id
    assert "event" in memory.tags
    assert event.id in memory.tags

def test_run_calls_finish_day_after_last_tick(monkeypatch):
    engine = build_engine()
    loop = SimulationLoop()
    calls = []

    engine.start_day = 1
    engine.start_hour = 0
    engine.current_daily_event = None

    monkeypatch.setattr(
        loop,
        "start_new_day",
        lambda engine, day: setattr(
            engine,
            "current_daily_event",
            type(
                "Event",
                (),
                {
                    "name": "Test Event",
                    "description": "Test description",
                },
            )(),
        ),
    )

    monkeypatch.setattr(
        engine,
        "run_tick",
        lambda day, hour: calls.append(
            ("tick", day, hour)
        ),
    )

    monkeypatch.setattr(
        engine.state,
        "save",
        lambda engine, day, hour: calls.append(
            ("hourly_save", day, hour)
        ),
    )

    monkeypatch.setattr(
        loop,
        "finish_day",
        lambda engine, day, final_hour: calls.append(
            ("finish_day", day, final_hour)
        ),
    )

    monkeypatch.setattr(
        engine,
        "print_relationships",
        lambda: None,
    )

    monkeypatch.setattr(
        engine.reporter,
        "summarize",
        lambda engine: None,
    )

    loop.run(
        engine=engine,
        days=1,
        hours=[8, 12],
    )

    assert calls == [
        ("tick", 1, 8),
        ("hourly_save", 1, 8),
        ("tick", 1, 12),
        ("hourly_save", 1, 12),
        ("finish_day", 1, 12),
    ]


def test_run_finishes_each_simulated_day_once(
    monkeypatch,
):
    engine = build_engine()
    loop = SimulationLoop()
    completed_days = []

    engine.start_day = 1
    engine.start_hour = 0

    def fake_start_new_day(engine, day):
        engine.current_daily_event = type(
            "Event",
            (),
            {
                "name": f"Event {day}",
                "description": "Description",
            },
        )()

    monkeypatch.setattr(
        loop,
        "start_new_day",
        fake_start_new_day,
    )

    monkeypatch.setattr(
        engine,
        "run_tick",
        lambda day, hour: None,
    )

    monkeypatch.setattr(
        engine.state,
        "save",
        lambda engine, day, hour: None,
    )

    monkeypatch.setattr(
        loop,
        "finish_day",
        lambda engine, day, final_hour: (
            completed_days.append(day)
        ),
    )

    monkeypatch.setattr(
        engine,
        "print_relationships",
        lambda: None,
    )

    monkeypatch.setattr(
        engine.reporter,
        "summarize",
        lambda engine: None,
    )

    loop.run(
        engine=engine,
        days=3,
        hours=[8],
    )

    assert completed_days == [1, 2, 3]