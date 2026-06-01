import json
import random
from pathlib import Path

from src.agents.agent import Agent
from src.town.location import Location
from src.utils.logger import TownLogger
from src.agents.relationships import RelationshipManager

class SimulationEngine:
    def __init__(self, agents_path: str, locations_path: str):
        self.agents = self.load_agents(agents_path)
        self.locations = self.load_locations(locations_path)
        self.logger = TownLogger()
        self.logger.clear_logs()
        self.relationships = RelationshipManager()


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

            speaker = random.choice(agents_here)

            possible_listeners = [
                agent for agent in agents_here
                if agent.name != speaker.name
            ]
            
            weights = [
                self.relationships.get_conversation_weight(speaker.name, listener.name)
                for listener in possible_listeners
            ]
            
            listener = random.choices(
                possible_listeners,
                weights=weights,
                k=1
            )[0]
            relationship_change = random.choice([-1, 0, 1, 1])
            new_score = self.relationships.change_score(
                speaker.name,
                listener.name,
                relationship_change,
            )
            
            relationship_label = self.relationships.describe_relationship(
                speaker.name,
                listener.name,
            )
            conversation = speaker.speak_to(listener, relationship_label)

            event = (
                f"Day {day}, {hour}:00 at {location_id}: {conversation} "
                f"Relationship is now {relationship_label} "
                f"({new_score:+d})."
            )

            speaker.remember(event)
            listener.remember(event)
            
            conversation_record = {
                "day": day,
                "hour": hour,
                "location": location_id,
                "speaker": speaker.name,
                "listener": listener.name,
                "conversation": conversation,
                "relationship_change": relationship_change,
                "relationship_score": new_score,
                "relationship_label": relationship_label,
            }            
            self.logger.log_conversation(conversation_record)
            
            event_record = {
                "type": "conversation",
                "day": day,
                "hour": hour,
                "location": location_id,
                "participants": [
                    speaker.name,
                    listener.name
                ]
            }
            
            self.logger.log_event(event_record)
            
            print(event)