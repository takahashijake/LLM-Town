import json
import random
from pathlib import Path

from src.agents.agent import Agent
from src.town.location import Location
from src.utils.logger import TownLogger

class SimulationEngine:
    def __init__(self, agents_path: str, locations_path: str):
        self.agents = self.load_agents(agents_path)
        self.locations = self.load_locations(locations_path)

    def load_agents(self, path: str) -> list[Agent]:
        with open(path, "r") as f:
            data = json.load(f)

        return [Agent(**agent_data) for agent_data in data]

    def load_locations(self, path: str) -> list[Location]:
        with open(path, "r") as f:
            data = json.load(f)

        return [Location(**location_data) for location_data in data]

    def run(self, days: int, hours: list[int]) -> None:
        print("Starting town simulation...")

        for day in range(1, days + 1):
            print(f"\n=== Day {day} ===")

            for hour in hours:
                print(f"\n--- {hour}:00 ---")
                self.run_tick(day, hour)

        print("\nSimulation finished.")

    def run_tick(self, day: int, hour: int) -> None:
        location_ids = [location.id for location in self.locations]

        for agent in self.agents:
            agent.move(location_ids)

        self.generate_conversations(day, hour)

    def generate_conversations(self, day: int, hour: int) -> None:
        agents_by_location = {}

        for agent in self.agents:
            agents_by_location.setdefault(agent.location_id, []).append(agent)

        for location_id, agents_here in agents_by_location.items():
            if len(agents_here) < 2:
                continue

            speaker, listener = random.sample(agents_here, 2)
            conversation = speaker.speak_to(listener)

            event = f"Day {day}, {hour}:00 at {location_id}: {conversation}"

            speaker.remember(event)
            listener.remember(event)

            print(event)