import json
import random
from pathlib import Path

from src.behavior.planner import ActivityPlanner
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
from src.analysis.report import SimulationReporter

class SimulationEngine:
    def __init__(
        self,
        agents_path: str,
        locations_path: str,
        load_state: bool = False,
        llm_client=None,
    ):
        self.locations = self.load_locations(locations_path)
        self.logger = TownLogger()
        self.relationships = RelationshipManager()
        self.state = SimulationState()
        self.llm = llm_client or TransformersLLMClient()
        self.actions = ActionSystem()
        self.activity_planner = ActivityPlanner()
        self.current_daily_event = None
        saved_state = self.state.load() if load_state else None
        self.reporter = SimulationReporter()
        self.activity_records = []
        self.recent_dialogues = [] 
        self.recent_actions = []
        self.daily_event_history = []
        if saved_state:
            self.agents = self.load_agents_from_state(saved_state)
            self.load_relationships_from_state(saved_state)
            self.start_day = saved_state["current_day"]
            self.start_hour = saved_state["current_hour"]
        else:
            self.agents = self.load_agents(agents_path)
            self.start_day = 1
            self.start_hour = 0

        def is_narration(self, conversation: str, speaker: Agent, listener: Agent) -> bool:
            text = conversation.strip().lower()
    
            narration_patterns = [
                f"{speaker.name.lower()} noticed",
                f"{listener.name.lower()} noticed",
                f"{speaker.name.lower()} nodded",
                f"{listener.name.lower()} nodded",
                f"{speaker.name.lower()} looked",
                f"{listener.name.lower()} looked",
                f"{speaker.name.lower()} smiled",
                f"{listener.name.lower()} smiled",
            ]

        return any(pattern in text for pattern in narration_patterns)
    def maintain_agent_memories(self) -> None:
        for agent in self.agents:
            agent.prune_memory(active_memory_limit=200)
            agent.summarize_archived_memories(max_archive_size=500)
    def remember_dialogue(self, conversation: str, limit: int = 50) -> None:
        normalized = conversation.strip().lower()

        if not normalized:
            return

        self.recent_dialogues.append(normalized)
        self.recent_dialogues = self.recent_dialogues[-limit:]


    def is_repeated_dialogue(self, conversation: str) -> bool:
        normalized = conversation.strip().lower()

        if not normalized:
            return False

        return normalized in self.recent_dialogues


    def remember_action(self, action: str, limit: int = 50) -> None:
        self.recent_actions.append(action)
        self.recent_actions = self.recent_actions[-limit:]


    def should_cap_action(self, action: str) -> bool:
        if action == "chat":
            return False

        recent_window = self.recent_actions[-20:]

        if len(recent_window) < 5:
            return False

        action_count = recent_window.count(action)
        action_rate = action_count / len(recent_window)

        if action == "share_rumor" and action_rate >= 0.20:
            return True

        non_chat_count = sum(
            1 for recent_action in recent_window
            if recent_action != "chat"
        )
        non_chat_rate = non_chat_count / len(recent_window)

        if action != "chat" and non_chat_rate >= 0.40:
            return True

        return False


    def choose_final_action(
        self,
        conversation: str,
        parsed_action: str,
        conversation_tags: list[str],
        allowed_actions: list[str],
    ) -> str:
        inferred_action = self.actions.infer_action(
            conversation,
            conversation_tags,
        )

        if inferred_action in allowed_actions:
            final_action = inferred_action
        elif parsed_action in allowed_actions:
            final_action = parsed_action
        else:
            final_action = "chat"

        if self.should_cap_action(final_action):
            return "chat"

        return final_action


    def get_previous_event_names(self, current_day: int) -> list[str]:
        return [
            event["name"]
            for event in self.daily_event_history
            if event["day"] < current_day
        ]


    def fix_stale_event_reference(self, conversation: str, current_day: int) -> str:
        if not self.current_daily_event:
            return conversation

        current_event_name = self.current_daily_event.name.lower()
        previous_event_names = self.get_previous_event_names(current_day)

        fixed_conversation = conversation

        for previous_event_name in previous_event_names:
            previous_event_lower = previous_event_name.lower()

            if previous_event_lower == current_event_name:
                continue

            if previous_event_lower in fixed_conversation.lower():
                fixed_conversation = fixed_conversation.replace(
                    " today",
                    " recently",
                )
                fixed_conversation = fixed_conversation.replace(
                    " Today",
                    " Recently",
                )

        return fixed_conversation
        
    def log_activity_event(self, day: int, hour: int, agent: Agent, activity) -> None:
        activity_record = {
            "type": "activity",
            "day": day,
            "hour": hour,
            "agent": agent.name,
            "activity_id": activity.id,
            "activity_name": activity.name,
            "location": activity.location_id,
            "reason": activity.reason,
            "tags": activity.tags,
        }

        self.activity_records.append(activity_record)
        self.logger.log_event(activity_record)
        
    def load_agents_from_state(self, saved_state: dict) -> list[Agent]:
        agents = []
    
        for agent_data in saved_state["agents"]:
            memories = [
                Memory(**memory_data)
                for memory_data in agent_data.get("memory", [])
            ]

            memory_archive = [
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
                memory_archive=memory_archive, 
                memory_summary=agent_data.get("memory_summary", ""),
                occupation=agent_data.get("occupation", "unemployed"),
                recent_topics=agent_data.get("recent_topics", []),
                relationships=agent_data.get("relationships", {}),
                current_activity=agent_data.get("current_activity", "idle"),
                current_activity_reason=agent_data.get("current_activity_reason", ""),
                current_activity_tags=agent_data.get("current_activity_tags", []),
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

        end_day = self.start_day + days - 1 
        for day in range(self.start_day, end_day + 1):
            print(f"\n=== Day {day} ===")
            self.current_daily_event = choose_daily_event() 

            self.daily_event_history.append({
                "day" : day, 
                "id" : self.current_daily_event.id, 
                "name" : self.current_daily_event.name,
            })
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
        self.reporter.summarize(self)
        print("\nSimulation finished.")

    def run_tick(self, day: int, hour: int) -> None:
        location_ids = [location.id for location in self.locations]
    
        for agent in self.agents:
            agent.decay_needs()
    
            activity = self.activity_planner.choose_activity(
                agent=agent,
                location_ids=location_ids,
                current_day=day,
                hour=hour,
                daily_event=self.current_daily_event,
            )
    
            agent.set_activity(activity)
            self.log_activity_event(day, hour, agent, activity)
            print(
                f"{agent.name} chooses activity: {activity.name} "
                f"at {activity.location_id} ({activity.reason})"
            )
    
        self.generate_conversations(day, hour)
        self.maintain_agent_memories()
        self.relationships.decay_all_relationships(probability=0.03)

    def get_relationship_change(self, relationship_label: str) -> int:
        if relationship_label == "close friends":
            return random.choice([-1, 0, 0, 0, 0, 0])
    
        if relationship_label == "friendly":
            return random.choice([-1, 0, 0, 0, 0])
    
        if relationship_label == "neutral":
            return random.choice([-1, 0, 0, 0, 0, 1])
    
        if relationship_label == "tense":
            return random.choice([-1, -1, 0, 0, 0])
    
        if relationship_label == "enemies":
            return random.choice([-1, 0, 0, 0])
    
        return random.choice([-1, 0, 0, 0])

    def calculate_relationship_change(
    self,
    action: str,
    old_relationship_label: str,
    old_relationship_score: int,
    ) -> int:
        action_effect = self.actions.get_relationship_effect(action)
        relationship_drift = self.get_relationship_change(old_relationship_label)
        relationship_change = action_effect + relationship_drift
    
        # Saturation: close relationships are harder to improve.
        if old_relationship_score >= 7 and relationship_change > 0:
            relationship_change = 0
    
        # Very bad relationships are harder to repair casually.
        if old_relationship_score <= -7 and relationship_change > 0 and action == "chat":
            relationship_change = 0
    
        return max(-3, min(3, relationship_change))
        
    def choose_suggested_action(
        self,
        allowed_actions: list[str],
        relationship_label: str,
    ) -> str:
        if not allowed_actions:
            return "chat"

        allowed = set(allowed_actions)

        if relationship_label in ["tense", "enemies"]:
            preferred_weights = {
                "chat": 8,
                "apologize": 3,
                "argue": 2,
                "storm_off": 1,
                "insult": 1,
            }
        elif relationship_label in ["friendly", "close friends"]:
            preferred_weights = {
                "chat": 7,
                "compliment": 3,
                "cooperate": 1,
                "offer_help": 2,
                "ask_for_help": 1,
                "confess_feelings": 1,
            }
        else:
            preferred_weights = {
                "chat": 8,
                "cooperate": 1,
                "offer_help": 2,
                "ask_for_help": 2,
                "compliment": 1,
                "share_rumor": 1,
            }

        weighted_actions = []

        for action, weight in preferred_weights.items():
            if action in allowed:
                weighted_actions.extend([action] * weight)

        if not weighted_actions:
            return "chat"

        return random.choice(weighted_actions)
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
        action_source: str = "",
        action_reason: str = "",
        tags: list[str] | None = None,
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
            "action": action,
            "action_source": action_source,
            "action_reason": action_reason,
            "tags": tags or [],
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
            suggested_action = self.choose_suggested_action(
                allowed_actions,
                old_relationship_label,
            )
            
            context = build_conversation_context(
                speaker=speaker,
                listener=listener,
                location_id=location_id,
                relationship_label=old_relationship_label,
                relationship_score=old_score,
                current_day=day,
                daily_event=self.current_daily_event,
                allowed_actions=allowed_actions,
                suggested_action=suggested_action,
            )            
            
            raw_output = self.llm.generate_conversation(context)

            parsed_output = parse_llm_conversation_output(
                raw_output,
                allowed_actions=allowed_actions,
            )
            
            conversation = parsed_output["dialogue"]
            parsed_action = parsed_output["action"]
            
            if not conversation:
                conversation = speaker.speak_to(listener, old_relationship_label)
                parsed_action = "chat"
            
            conversation = self.fix_stale_event_reference(
                conversation,
                current_day=day,
            )
            
            
            conversation_tags = infer_conversation_tags(conversation)
            conversation_tags.extend(parsed_output.get("tags", []))
            
            action = self.choose_final_action(
                conversation=conversation,
                parsed_action=parsed_action,
                conversation_tags=conversation_tags,
                allowed_actions=allowed_actions,
            )
            
            if self.current_daily_event:
                dialogue_lower = conversation.lower()
                event_name_words = [
                    word
                    for word in self.current_daily_event.name.lower().split()
                    if len(word) >= 4
                ]
            
                mentions_event = any(word in dialogue_lower for word in event_name_words)
            
                if mentions_event or "event" in conversation_tags:
                    conversation_tags.append("event")
                    conversation_tags.append(self.current_daily_event.id)
            
            conversation_tags.append(old_relationship_label)
            conversation_tags.append(action)
            
            conversation_tags = list(dict.fromkeys(conversation_tags))

           

            relationship_change = self.calculate_relationship_change(
                action,
                old_relationship_label,
                old_score,
            )
            
            new_score, relationship_label = self.apply_relationship_change(
                speaker,
                listener,
                relationship_change, 
            )
            

            need_effects = self.actions.get_need_effects(action)
            for need, amount in need_effects.items():
                speaker.satisfy_need(need, amount)
                

            topic_memory = conversation_tags

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

            self.remember_dialogue(conversation)
            self.remember_action(action)

            
            
            
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
                parsed_output.get("action_source", ""),
                parsed_output.get("reason", ""),
                conversation_tags,
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
