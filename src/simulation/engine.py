import json
import random
from pathlib import Path

from src.agents.memory import Memory
from src.agents.agent import Agent
from src.town.location import Location
from src.utils.logger import TownLogger
from src.agents.relationships import RelationshipManager
from src.simulation.state import SimulationState
from src.llm.client import FakeLLMClient, TransformersLLMClient
from src.llm.context import build_conversation_context 
from src.llm.parser import clean_conversation_output, parse_llm_conversation_output, infer_conversation_tags
from src.town.daily_event import choose_daily_event
from src.actions.action_system import ActionSystem 

class SimulationEngine:
    def __init__(self, agents_path: str, locations_path: str, load_state: bool = False):
        self.locations = self.load_locations(locations_path)
        self.logger = TownLogger()
        self.relationships = RelationshipManager()
        self.state = SimulationState()
        self.llm = TransformersLLMClient()
        self.actions = ActionSystem()
        self.current_daily_event = None
        saved_state = self.state.load() if load_state else None
    
        if saved_state:
            self.agents = self.load_agents_from_state(saved_state)
            self.load_relationships_from_state(saved_state)
            self.start_day = saved_state["current_day"]
            self.start_hour = saved_state["current_hour"]
        else:
            self.agents = self.load_agents(agents_path)
            self.start_day = 1
            self.start_hour = 0

    def load_agents_from_state(self, saved_state: dict) -> list[Agent]:
        agents = []
    
        for agent_data in saved_state["agents"]:
            memories = [
                Memory(**memory_data)
                for memory_data in agent_data.get("memory", [])
            ]
            agent = Agent(
                id=agent_data["id"],
                name=agent_data["name"],
                personality=agent_data["personality"],
                location_id=agent_data["location_id"],
                goals=agent_data.get("goals", []),
                needs=agent_data.get("needs", {}),
                memory=memories,
                occupation=agent_data.get("occupation", "unemployed"),
                recent_topics=agent_data.get("recent_topics", []),
                relationships=agent_data.get("relationships", {}),
            )
            agents.append(agent)
    
        return agents


    def load_relationships_from_state(self, saved_state: dict) -> None:
        relationship_scores = saved_state.get("relationship_scores", {})
    
        for pair_key, score in relationship_scores.items():
            agent_a, agent_b = pair_key.split("|")
            self.relationships.scores[(agent_a, agent_b)] = score
        
    def load_agents(self, path: str) -> list[Agent]:
        with open(path, "r") as f:
            data = json.load(f)
        agents = [Agent(**agent_data) for agent_data in data]

        for agent in agents:
            agent.initialize_needs()
        
        return agents

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
    def load_locations(self, path: str) -> list[Location]:
        with open(path, "r") as f:
            data = json.load(f)

        return [Location(**location_data) for location_data in data]

    def run(self, days: int, hours: list[int]) -> None:
        print("Starting town simulation...")

        for day in range(1, days + 1):
            print(f"\n=== Day {day} ===")
            self.current_daily_event = choose_daily_event() 
            event_memory = self.create_daily_event_memory(day, self.current_daily_event) 
            for agent in self.agents:
                agent.remember(event_memory)
                
            print(
                f"Daily Event: {self.current_daily_event.name} - "
                f"{self.current_daily_event.description}"
            )
            for hour in hours:
                print(f"\n--- {hour}:00 ---")
                self.run_tick(day, hour)
                self.state.save(self, day, hour)
        self.print_relationships()
        print("\nSimulation finished.")

    def run_tick(self, day: int, hour: int) -> None:
        location_ids = [location.id for location in self.locations]

        for agent in self.agents:
            agent.decay_needs()
            if self.current_daily_event and random.random() < 0.35:
                agent.location_id = self.current_daily_event.location_id
            else:
                agent.move(location_ids)

        self.generate_conversations(day, hour)

    def get_relationship_change(self, relationship_label: str) -> int:
        if relationship_label == "close friends":
            return random.choice([-1, 0, 0, 0, 0])
    
        if relationship_label == "friendly":
            return random.choice([-1, 0, 0, 0, 1])
    
        if relationship_label == "neutral":
            return random.choice([-1, 0, 0, 0, 1])
    
        if relationship_label == "tense":
            return random.choice([-1, 0, 0, 0, 1])
    
        if relationship_label == "enemies":
            return random.choice([0, 0, 1, 1])
    
        return random.choice([-1, 0, 0, 0, 1])

    def group_agents_by_location(self) -> dict[str, list[Agent]]:
        agents_by_location = {}
        
        for agent in self.agents:
            agents_by_location.setdefault(agent.location_id, []).append(agent)

        return agents_by_location

    def choose_conversation_pair(self, agents_here: list[Agent]) -> tuple[Agent, Agent]: 
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
            k=1,
        )[0]

        return speaker, listener

    def apply_relationship_change(
    self,
    speaker: Agent,
    listener: Agent,
    relationship_change: int,
    ) -> tuple[int, str]:
        new_score = self.relationships.change_score(
            speaker.name,
            listener.name,
            relationship_change,
        )
    
        speaker.update_relationship(listener.name, new_score)
        listener.update_relationship(speaker.name, new_score)
    
        relationship_label = self.relationships.describe_relationship(
            speaker.name,
            listener.name,
        )
    
        return new_score, relationship_label

    def create_conversation_memory(
        self,
        day: int,
        hour: int,
        location_id: str,
        speaker: Agent,
        listener: Agent,
        conversation: str,
        relationship_change: int,
        tags: list[str],
    ) -> Memory:
        return Memory(
            day=day,
            hour=hour,
            type="conversation",
            description=conversation,
            participants=[speaker.name, listener.name],
            location=location_id,
            importance=2,
            sentiment=relationship_change,
            tags=tags,
    )

    def log_conversation_event(
        self,
        day: int,
        hour: int,
        location_id: str,
        speaker: Agent,
        listener: Agent,
        conversation: str,
        relationship_change: int,
        new_score: int,
        relationship_label: str,
        action: str,
    ) -> None:
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
            "action" : action,
        }
    
        self.logger.log_conversation(conversation_record)
    
        event_record = {
            "type": "conversation",
            "day": day,
            "hour": hour,
            "location": location_id,
            "participants": [
                speaker.name,
                listener.name,
            ],
        }
    
        self.logger.log_event(event_record)

    def print_conversation_event(
    self,
    day: int,
    hour: int,
    location_id: str,
    conversation: str,
    relationship_label: str,
    new_score: int,
    relationship_change: int,
    action: str,
    ) -> None:
        print(
            f"Day {day}, {hour}:00 at {location_id}: {conversation} "
            f"Relationship is now {relationship_label} "
            f"(score {new_score:+d}, change {relationship_change:+d}). "
            f"Action: {action}."
        )
        
    def generate_conversations(self, day: int, hour: int) -> None:
        agents_by_location = self.group_agents_by_location()
        conversations_created = 0 
        for location_id, agents_here in agents_by_location.items():
            if len(agents_here) < 2:
                continue
            conversations_created = conversations_created + 1 
            speaker, listener = self.choose_conversation_pair(agents_here) 

            old_score = self.relationships.get_score(speaker.name, listener.name) 
            old_relationship_label = self.relationships.describe_relationship(
                speaker.name,
                listener.name,
            )

            allowed_actions = self.actions.get_allowed_actions_for_relationship(old_score)
            
            context = build_conversation_context(
                speaker=speaker,
                listener=listener,
                location_id=location_id,
                relationship_label=old_relationship_label,
                relationship_score=old_score,
                current_day=day,
                daily_event=self.current_daily_event,
                allowed_actions=allowed_actions,
            )                    
            
            raw_output = self.llm.generate_conversation(context)
            parsed_output = parse_llm_conversation_output(raw_output)

            conversation = parsed_output["dialogue"]
            action = parsed_output["action"]

            if old_relationship_label in ["tense", "enemies"] and action in [
                "compliment", 
                "offer_help", 
                "confess_feelings",
            ]:
                action = "chat"
            if not conversation:
                conversation = speaker.speak_to(listener, old_relationship_label)
                action = "chat"
            
            conversation_tags = infer_conversation_tags(conversation) 
            conversation_tags.append(old_relationship_label) 
            conversation_tags.append(action) 

            #NOTE: THIS IS A TEMPORARY COMMENTING 
            #random_relationship_effect = self.get_relationship_change(old_relationship_label) 
            #action_relationship_effect = self.actions.get_relationship_effect(action) 
            #relationship_change = random_relationship_effect + action_relationship_effect 

            relationship_change = self.actions.get_relationship_effect(action)
            
            new_score, relationship_label = self.apply_relationship_change(
                speaker,
                listener,
                relationship_change, 
            )
            

            need_effects = self.actions.get_need_effects(action)
            for need, amount in need_effects.items():
                speaker.satisfy_need(need, amount)
                

            topic_memory = conversation_tags + [conversation[:80]]

            speaker.remember_topics(topic_memory) 
            listener.remember_topics(topic_memory)
            
            memory = self.create_conversation_memory(
                day,
                hour,
                location_id,
                speaker,
                listener,
                conversation,
                relationship_change,
                conversation_tags,
            )
            
            speaker.remember(memory)
            listener.remember(memory)
            
            
            self.log_conversation_event(
                day,
                hour,
                location_id,
                speaker,
                listener,
                conversation,
                relationship_change,
                new_score,
                relationship_label,
                action,
            )
            self.print_conversation_event(
                day,
                hour,
                location_id,
                conversation,
                relationship_label,
                new_score,
                relationship_change,
                action,
            )
        if conversations_created == 0: 
            print("No conversations this tick") 

    def print_relationships(self):
        print("\n=== Final Relationships ===")

        for agent in self.agents:
            print(f"\n{agent.name}:")
            for other_name, score in agent.relationships.items():
                label = self.relationships.describe_relationship(agent.name, other_name)
                print(f"  {other_name}: {label} ({score:+d})")
