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
from src.agents.relationship_event import RelationshipEvent 
from src.behavior.social_policy import SocialBehaviorPolicy 
from src.agents.intent import AgentIntent 
from src.behavior.intent_planner import IntentPlanner 


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
        self.social_policy = SocialBehaviorPolicy()
        self.intent_planner = IntentPlanner() 
        self.agent_intents = {}
        self.current_daily_event = None
        saved_state = self.state.load() if load_state else None
        self.reporter = SimulationReporter()
        self.activity_records = []
        self.recent_dialogues = [] 
        self.recent_actions = []
        self.daily_event_history = []
        self.relationship_events = []
        if saved_state:
            self.agents = self.load_agents_from_state(saved_state)
            self.load_relationships_from_state(saved_state)
            self.load_agent_intents_from_state(saved_state)
            self.load_relationship_events_from_state(saved_state)
            self.sync_agent_relationships_from_manager()
            self.start_day = saved_state["current_day"]
            self.start_hour = saved_state["current_hour"]
        else:
            self.agents = self.load_agents(agents_path)
            self.start_day = 1
            self.start_hour = 0

    def get_activity_need_effects(self, activity) -> dict[str, int]:
        effects_by_tag = {
            "wealth": {"wealth": 3},
            "business": {"wealth": 2},
            "market": {"wealth": 1},
            "social": {"social": 2},
            "relationship": {"social": 2},
            "community": {"social": 1},
            "volunteer": {"social": 1},
            "knowledge": {"knowledge": 2},
            "learning": {"knowledge": 2},
            "jousrnalism": {"knowledge": 2},
            "accounting": {"knowledge": 2},
        }
    
        effects = {}
    
        for tag in activity.tags:
            for need, amount in effects_by_tag.get(tag, {}).items():
                effects[need] = effects.get(need, 0) + amount
    
        return effects
    
    def get_intent_listener_weight_bonus(
    self,
    speaker: Agent,
    listener: Agent,
    ) -> int:
        intent = self.agent_intents.get(speaker.name)
    
        if not intent:
            return 0
    
        if intent.target_agent != listener.name:
            return 0
    
        if intent.intent_type == "repair_relationship":
            return 5
    
        if intent.intent_type == "build_friendship":
            return 4
    
        return 2
    
    def load_agent_intents_from_state(self, saved_state: dict) -> None:
        self.agent_intents = {
            agent_name: AgentIntent(**intent_data)
            for agent_name, intent_data in saved_state.get("agent_intents", {}).items()
        }


    def update_agent_intents(self, current_day: int) -> None:
        for agent in self.agents:
            current_intent = self.agent_intents.get(agent.name)
    
            if current_intent and not current_intent.is_expired(current_day):
                continue
    
            new_intent = self.intent_planner.create_intent_for_agent(
                agent=agent,
                engine=self,
                current_day=current_day,
            )
    
            if new_intent:
                self.agent_intents[agent.name] = new_intent


    def get_agent_intent_text(self, agent_name: str) -> str:
        intent = self.agent_intents.get(agent_name)
    
        if not intent:
            return "No active intent."
    
        return intent.description
    
    def load_relationship_events_from_state(self, saved_state: dict) -> None:
        self.relationship_events = [
            RelationshipEvent(**event_data)
            for event_data in saved_state.get("relationship_events", [])
        ]
    def should_record_relationship_event(
    self,
    action: str,
    relationship_change: int,
    ) -> bool:
        return action != "chat" or relationship_change != 0

    
    def create_relationship_event(
        self,
        day: int,
        hour: int,
        location_id: str,
        speaker: Agent,
        listener: Agent,
        action: str,
        relationship_change: int,
        new_score: int,
        relationship_label: str,
        conversation: str,
        tags: list[str],
    ) -> RelationshipEvent:
        if relationship_change > 0:
            direction = "improved"
        elif relationship_change < 0:
            direction = "worsened"
        else:
            direction = "stayed the same"
    
        description = (
            f"{speaker.name} used action '{action}' with {listener.name}. "
            f"Their relationship {direction} by {relationship_change:+d}; "
            f"score is now {new_score:+d} ({relationship_label})."
        )
    
        return RelationshipEvent(
            day=day,
            hour=hour,
            agent_a=speaker.name,
            agent_b=listener.name,
            action=action,
            relationship_change=relationship_change,
            relationship_score=new_score,
            relationship_label=relationship_label,
            description=description,
            location=location_id,
            tags=tags,
            conversation=conversation,
        )


    def record_relationship_event(
        self,
        relationship_event: RelationshipEvent,
    ) -> None:
        self.relationship_events.append(relationship_event)


    def get_recent_relationship_events(
        self,
        agent_a: str,
        agent_b: str,
        limit: int = 3,
    ) -> list[RelationshipEvent]:
        matching_events = [
            event
            for event in self.relationship_events
            if event.involves_pair(agent_a, agent_b)
        ]
    
        matching_events.sort(
            key=lambda event: (
                event.day,
                event.hour,
            ),
            reverse=True,
        )
    
        return matching_events[:limit]
    
    
    def format_relationship_history_for_prompt(
        self,
        agent_a: str,
        agent_b: str,
        limit: int = 3,
    ) -> list[str]:
        events = self.get_recent_relationship_events(
            agent_a,
            agent_b,
            limit=limit,
        )
    
        return [
            (
                f"Day {event.day}, {event.hour}:00: "
                f"{event.description} "
                f"Conversation: \"{event.conversation}\""
            )
            for event in events
        ]
        
    def sync_agent_relationships_from_manager(self) -> None:
        agents_by_name = {
            agent.name: agent
            for agent in self.agents
        }

        for (agent_a, agent_b), score in self.relationships.scores.items():
            if agent_a not in agents_by_name or agent_b not in agents_by_name:
                continue

            agents_by_name[agent_a].update_relationship(agent_b, score)
            agents_by_name[agent_b].update_relationship(agent_a, score)
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

        if action != "chat" and non_chat_rate >= 0.50:
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
    
        if parsed_action == "share_rumor" and inferred_action == "chat":
            final_action = "chat"
        elif inferred_action != "chat" and inferred_action in allowed_actions:
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


    def get_previous_event_keywords(self, current_day: int) -> list[str]:
        keywords = []

        for event in self.daily_event_history:
            if event["day"] >= current_day:
                continue

            name = event["name"].lower()
            keywords.append(name)

            for word in name.split():
                if len(word) >= 5:
                    keywords.append(word)

        return list(dict.fromkeys(keywords))


    def fix_stale_event_reference(self, conversation: str, current_day: int) -> str:
        if not self.current_daily_event:
            return conversation

        current_event_name = self.current_daily_event.name.lower()
        current_event_words = {
            word
            for word in current_event_name.split()
            if len(word) >= 5
        }

        previous_keywords = self.get_previous_event_keywords(current_day)
        fixed_conversation = conversation
        fixed_lower = fixed_conversation.lower()

        mentions_today = (
            "today" in fixed_lower
            or "tonight" in fixed_lower
            or "this morning" in fixed_lower
            or "this afternoon" in fixed_lower
            or "this evening" in fixed_lower
        )

        if not mentions_today:
            return fixed_conversation

        for keyword in previous_keywords:
            if keyword in current_event_words:
                continue

            if keyword in fixed_lower and keyword not in current_event_name:
                fixed_conversation = fixed_conversation.replace(" today", " recently")
                fixed_conversation = fixed_conversation.replace(" Today", " Recently")
                fixed_conversation = fixed_conversation.replace(" tonight", " recently")
                fixed_conversation = fixed_conversation.replace(" Tonight", " Recently")
                fixed_conversation = fixed_conversation.replace(" this morning", " recently")
                fixed_conversation = fixed_conversation.replace(" this afternoon", " recently")
                fixed_conversation = fixed_conversation.replace(" this evening", " recently")
                return fixed_conversation

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

            self.update_agent_intents(day)
                
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
                current_intent=self.agent_intents.get(agent.name),
            )
    
            agent.set_activity(activity)
            self.log_activity_event(day, hour, agent, activity)

            activity_need_effects = self.get_activity_need_effects(activity)

            for need, amount in activity_need_effects.items():
                agent.satisfy_need(need, amount)
                
            print(
                f"{agent.name} chooses activity: {activity.name} "
                f"at {activity.location_id} ({activity.reason})"
            )
    
        self.generate_conversations(day, hour)
        self.maintain_agent_memories()
        self.relationships.decay_all_relationships(probability=0.03)
        self.sync_agent_relationships_from_manager() 
        

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

    def adjust_action_weights_for_intent(
    self,
    weights: dict[str, int],
    intent: AgentIntent | None,
    listener_name: str,
    ) -> dict[str, int]:
        adjusted = dict(weights)
    
        if not intent:
            return adjusted
    
        target_matches = (
            intent.target_agent is None
            or intent.target_agent == listener_name
        )
    
        if not target_matches:
            return adjusted
    
        if intent.intent_type == "repair_relationship":
            if "apologize" in adjusted:
                adjusted["apologize"] += 4
            if "offer_help" in adjusted:
                adjusted["offer_help"] += 2
            if "chat" in adjusted:
                adjusted["chat"] += 1
            if "argue" in adjusted:
                adjusted["argue"] = max(1, adjusted["argue"] - 2)
    
        elif intent.intent_type == "build_friendship":
            if "compliment" in adjusted:
                adjusted["compliment"] += 2
            if "offer_help" in adjusted:
                adjusted["offer_help"] += 2
            if "cooperate" in adjusted:
                adjusted["cooperate"] += 2
    
        elif intent.intent_type == "investigate":
            if "ask_for_help" in adjusted:
                adjusted["ask_for_help"] += 3
            if "share_rumor" in adjusted:
                adjusted["share_rumor"] += 1
            if "chat" in adjusted:
                adjusted["chat"] += 1
    
        elif intent.intent_type == "socialize":
            if "chat" in adjusted:
                adjusted["chat"] += 2
            if "compliment" in adjusted:
                adjusted["compliment"] += 1
    
        elif intent.intent_type == "seek_work":
            if "ask_for_help" in adjusted:
                adjusted["ask_for_help"] += 1
            if "cooperate" in adjusted:
                adjusted["cooperate"] += 1
            if "chat" in adjusted:
                adjusted["chat"] += 2
            
        return adjusted
    

    def get_suggested_action_weights(
        self,
        allowed_actions: list[str],
        relationship_label: str,
        recent_relationship_events=None,
    ) -> dict[str, int]:
        return self.social_policy.get_action_weights(
            allowed_actions=allowed_actions,
            relationship_label=relationship_label,
            recent_events=recent_relationship_events,
        )


    def choose_suggested_action(
    self,
    allowed_actions: list[str],
    relationship_label: str,
    recent_relationship_events=None,
    ) -> str:
        if not allowed_actions:
            return "chat"
    
        weights = self.get_suggested_action_weights(
            allowed_actions=allowed_actions,
            relationship_label=relationship_label,
            recent_relationship_events=recent_relationship_events,
        )
    
        return self.choose_weighted_action(weights)
        
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
            + self.get_intent_listener_weight_bonus(speaker, listener)
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

    def choose_weighted_action(self, weights: dict[str, int]) -> str:
        weighted_actions = []
    
        for action, weight in weights.items():
            weighted_actions.extend([action] * weight)
    
        if not weighted_actions:
            return "chat"
    
        return random.choice(weighted_actions)
        
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
        speaker_intent: AgentIntent | None = None,
        listener_intent: AgentIntent | None = None,
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
            "speaker_intent_type": speaker_intent.intent_type if speaker_intent else "",
            "speaker_intent_target_agent": speaker_intent.target_agent if speaker_intent else "",
            "speaker_intent_target_location": speaker_intent.target_location if speaker_intent else "",
            "speaker_intent_description": speaker_intent.description if speaker_intent else "",
            "listener_intent_type": listener_intent.intent_type if listener_intent else "",
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

            recent_relationship_events = self.get_recent_relationship_events(
                speaker.name,
                listener.name,
                limit=5,
            )
            
            speaker_intent = self.agent_intents.get(speaker.name)
            listener_intent = self.agent_intents.get(listener.name)
            
            base_action_weights = self.get_suggested_action_weights(
                allowed_actions=allowed_actions,
                relationship_label=old_relationship_label,
                recent_relationship_events=recent_relationship_events,
            )
            
            intent_adjusted_weights = self.adjust_action_weights_for_intent(
                weights=base_action_weights,
                intent=speaker_intent,
                listener_name=listener.name,
            )
            
            suggested_action = self.choose_weighted_action(intent_adjusted_weights)

            relationship_history = self.format_relationship_history_for_prompt(
                speaker.name,
                listener.name,
                limit=3,
            )

            speaker_intent = self.agent_intents.get(speaker.name) 
            listener_intent = self.agent_intents.get(listener.name)
            
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
                relationship_history=relationship_history,
                speaker_intent=speaker_intent.to_dict() if speaker_intent else None,
                listener_intent=listener_intent.to_dict() if listener_intent else None,
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

            if self.is_narration(conversation, speaker, listener): 
                conversation = speaker.speak_to(listener, old_relationship_label) 
                parsed_action = "chat"
            
            
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
            
            action_tags = {
                "chat",
                "compliment",
                "apologize",
                "offer_help",
                "ask_for_help",
                "argue",
                "insult",
                "storm_off",
                "confess_feelings",
                "share_rumor",
                "cooperate",
            }
            
            conversation_tags = [
                tag
                for tag in conversation_tags
                if tag not in action_tags
            ]
            
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

            if self.should_record_relationship_event(action, relationship_change):
                relationship_event = self.create_relationship_event(
                    day=day,
                    hour=hour,
                    location_id=location_id,
                    speaker=speaker,
                    listener=listener,
                    action=action,
                    relationship_change=relationship_change,
                    new_score=new_score,
                    relationship_label=relationship_label,
                    conversation=conversation,
                    tags=conversation_tags,
                )
                self.record_relationship_event(relationship_event)
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
                speaker_intent=speaker_intent,
                listener_intent=listener_intent,
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
