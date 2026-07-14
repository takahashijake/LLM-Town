from src.agents.memory import Memory
from src.town.daily_event import choose_daily_event


class SimulationLoop:
    def finish_day(
        self,
        engine,
        day: int,
        final_hour: int,
    ) -> None:
        engine.journal_system.create_journals_for_day(
            agents=engine.agents,
            day=day,
            activity_records=engine.activity_records,
            relationship_events=engine.relationship_events,
            intent_history=engine.intent_history,
            town_arc_change_records=engine.town_arc_change_records,
        )

        for agent in engine.agents:
            engine.journal_system.compress_old_memories(
                agent=agent,
                current_day=day,
                raw_memory_retention_days=7,
            )

        # Positional arguments preserve compatibility with older test fakes.
        engine.state.save(
            engine,
            day,
            final_hour,
            day_complete=True,
        )
    
    def create_daily_event_memory(self, day: int, event) -> Memory:
        return Memory(
            day=day,
            hour=0,
            type="daily_event",
            description=f"Town event today: {event.name}. {event.description}",
            participants=[],
            location=event.location_id,
            importance=3,
            sentiment=0,
            tags=["event", event.id] + event.tags,
        )

    def get_active_hours(self, engine, day: int, hours: list[int]) -> list[int]:
        if day == engine.start_day and engine.start_hour:
            return [
                hour
                for hour in hours
                if hour > engine.start_hour
            ]

        return hours

    def is_resuming_saved_day(self, engine, day: int) -> bool:
        return (
            day == engine.start_day
            and engine.start_hour > 0
            and engine.current_daily_event is not None
        )

    def resolve_first_run_day(
        self,
        engine,
        hours: list[int],
    ) -> int:
        if getattr(engine, "resume_day_complete", False):
            return engine.start_day + 1
    
        remaining_hours = self.get_active_hours(
            engine=engine,
            day=engine.start_day,
            hours=hours,
        )
    
        if engine.start_hour > 0 and not remaining_hours:
            self.finish_day(
                engine=engine,
                day=engine.start_day,
                final_hour=engine.start_hour,
            )
    
            return engine.start_day + 1
    
        return engine.start_day
        
    def start_new_day(self, engine, day: int) -> None:
        engine.current_daily_event = choose_daily_event()

        engine.daily_event_history.append({
            "day": day,
            "id": engine.current_daily_event.id,
            "name": engine.current_daily_event.name,
        })

        engine.update_town_arcs(day)

        event_memory = self.create_daily_event_memory(
            day,
            engine.current_daily_event,
        )

        for agent in engine.agents:
            agent.remember(event_memory)

        engine.update_agent_intents(day)

    def run_tick(self, engine, day: int, hour: int) -> None:
        engine.run_agent_activities(day, hour)
        engine.generate_conversations(day, hour)
        engine.maintain_agent_memories()
        engine.relationships.decay_all_relationships(probability=0.03)
        engine.sync_agent_relationships_from_manager()

    def run(self, engine, days: int, hours: list[int]) -> None:
        first_day = self.resolve_first_run_day(
            engine=engine,
            hours=hours,
        )
        
        end_day = first_day + days - 1
        
        for day in range(first_day, end_day + 1):
            active_hours = self.get_active_hours(
                engine=engine,
                day=day,
                hours=hours,
            )

            if not active_hours:
                continue

            print(f"\n=== Day {day} ===")

            if not self.is_resuming_saved_day(engine, day):
                self.start_new_day(engine, day)

            print(
                f"Daily Event: {engine.current_daily_event.name} - "
                f"{engine.current_daily_event.description}"
            )

            for hour in active_hours:
                print(f"\n--- {hour}:00 ---")
                engine.run_tick(day, hour)
                engine.state.save(
                    engine,
                    day,
                    hour,
                    day_complete=False,
                )
        
            self.finish_day(
                engine=engine,
                day=day,
                final_hour=active_hours[-1],
            )

        engine.print_relationships()
        engine.reporter.summarize(engine)
        print("\nSimulation finished.")