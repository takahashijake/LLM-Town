import json
import random
from pathlib import Path

from src.simulation.conversation_policy import ConversationPolicy
from src.simulation.intent_system import IntentSystem 
from src.simulation.persistence import SimulationPersistence
from src.simulation.town_arc_system import TownArcSystem
from src.simulation.relationship_updater import RelationshipUpdater
from src.town.town_arc import TownArc
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
from src.town.daily_event import choose_daily_event, DailyEvent
from src.actions.action_system import ActionSystem 
from src.analysis.report import SimulationReporter
from src.agents.relationship_event import RelationshipEvent 
from src.behavior.social_policy import SocialBehaviorPolicy 
from src.agents.intent import AgentIntent 
from src.behavior.intent_planner import IntentPlanner 
from src.simulation.dialogue_utils import ( 
    clean_dialogue_text,
    fix_stale_event_reference,
    get_previous_event_keywords,
    has_rumor_marker,
    is_narration,
)

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
        self.persistence = SimulationPersistence()
        self.llm = llm_client or TransformersLLMClient()
        self.actions = ActionSystem()
        self.relationship_updater = RelationshipUpdater(
            relationships=self.relationships,
            actions=self.actions,
        )
        self.activity_planner = ActivityPlanner()
        self.social_policy = SocialBehaviorPolicy()
        self.intent_planner = IntentPlanner() 
        self.agent_intents = {}
        self.intent_system = IntentSystem(
            intent_planner=self.intent_planner,
            agent_intents=self.agent_intents,
        )
        self.current_daily_event = None
        saved_state = self.state.load() if load_state else None
        self.reporter = SimulationReporter()
        self.activity_records = []
        self.recent_dialogues = [] 
        self.recent_actions = []
        self.conversation_policy = ConversationPolicy(
            actions=self.actions,
            recent_dialogues=self.recent_dialogues,
            recent_actions=self.recent_actions,
        )
        self.daily_event_history = []
        self.relationship_events = []
        self.town_arcs = []
        self.town_arc_change_records = []
        self.town_arc_system = TownArcSystem(
            town_arcs = self.town_arcs, 
            town_arc_change_records=self.town_arc_change_records,
        )
        if saved_state:
            self.load_run_continuity_from_state(saved_state)
            self.agents = self.load_agents_from_state(saved_state)
            self.load_relationships_from_state(saved_state)
            self.load_agent_intents_from_state(saved_state)
            self.load_relationship_events_from_state(saved_state)
            self.load_town_arcs_from_state(saved_state)
            self.town_arc_system = TownArcSystem(
                town_arcs=self.town_arcs,
                town_arc_change_records=self.town_arc_change_records,
            )
            self.sync_agent_relationships_from_manager()
            self.start_day = saved_state["current_day"]
            self.start_hour = saved_state["current_hour"]
        else:
            self.agents = self.load_agents(agents_path)
            self.start_day = 1
            self.start_hour = 0

    def sync_intent_system_refs(self) -> None:
        self.intent_system.agent_intents = self.agent_intents

    def sync_conversation_policy_refs(self) -> None:
        self.conversation_policy.recent_dialogues = self.recent_dialogues
        self.conversation_policy.recent_actions = self.recent_actions
        
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
            "journalism": {"knowledge": 2},
            "accounting": {"knowledge": 2},
        }
    
        effects = {}
    
        for tag in activity.tags:
            for need, amount in effects_by_tag.get(tag, {}).items():
                effects[need] = effects.get(need, 0) + amount
    
        return effects
    def sync_town_arc_system_refs(self) -> None:
        self.town_arc_system.town_arcs = self.town_arcs
        self.town_arc_system.town_arc_change_records = self.town_arc_change_records
        
    def get_intent_listener_weight_bonus(
        self,
        speaker: Agent,
        listener: Agent,
    ) -> int:
        self.sync_intent_system_refs()
        return self.intent_system.get_intent_listener_weight_bonus(
            speaker=speaker,
            listener=listener,
        )
        
    def load_agent_intents_from_state(self, saved_state: dict) -> None:
        self.agent_intents = self.persistence.load_agent_intents_from_state(
            saved_state=saved_state,
        )
        self.sync_intent_system_refs()

    def apply_conversation_to_town_arcs(
        self,
        day: int,
        location_id: str,
        speaker: Agent,
        listener: Agent,
        action: str,
        conversation_tags: list[str],
    ) -> None:
        self.sync_town_arc_system_refs()
        self.town_arc_system.apply_conversation_to_town_arcs(
            day=day,
            location_id=location_id,
            speaker=speaker,
            listener=listener,
            action=action,
            conversation_tags=conversation_tags,
        )
        
    def update_agent_intents(self, current_day: int) -> None:
        self.sync_intent_system_refs()
        self.intent_system.update_agent_intents(
            agents=self.agents,
            current_day=current_day,
            engine=self,
        )


    def get_agent_intent_text(self, agent_name: str) -> str:
        self.sync_intent_system_refs()
        return self.intent_system.get_agent_intent_text(
            agent_name=agent_name,
        )
    
    
    def load_relationship_events_from_state(self, saved_state: dict) -> None:
        self.relationship_events = self.persistence.load_relationship_events_from_state(
            saved_state=saved_state,
        )
        
    def load_daily_event_from_state(self, saved_state: dict) -> DailyEvent | None:
        return self.persistence.load_daily_event_from_state(
            saved_state=saved_state,
        )


    def load_run_continuity_from_state(self, saved_state: dict) -> None:
        continuity = self.persistence.load_run_continuity_from_state(
            saved_state=saved_state,
        )

        self.current_daily_event = continuity["current_daily_event"]
        self.daily_event_history = continuity["daily_event_history"]
        self.recent_dialogues = continuity["recent_dialogues"]
        self.recent_actions = continuity["recent_actions"]
        self.activity_records = continuity["activity_records"]
        self.sync_conversation_policy_refs()
    
    def load_town_arcs_from_state(self, saved_state: dict) -> None:
        self.town_arcs = self.persistence.load_town_arcs_from_state(
            saved_state=saved_state,
        )
        


    def get_active_town_arcs(self): 
        self.sync_town_arc_system_refs()
        return self.town_arc_system.get_active_town_arcs()

    def create_town_arc_from_daily_event(self, day: int, daily_event) -> TownArc | None:
        self.sync_town_arc_system_refs()
        return self.town_arc_system.create_town_arc_from_daily_event(
            day=day,
            daily_event=daily_event,
        )


    def should_create_town_arc(self, day: int) -> bool:
        self.sync_town_arc_system_refs()
        return self.town_arc_system.should_create_town_arc(day=day)


    def update_town_arcs(self, day: int) -> None:
        self.sync_town_arc_system_refs()

        self.town_arc_system.update_town_arcs(
            day=day,
            current_daily_event=self.current_daily_event,
            agents=self.agents,
        )


    def create_town_arc_memory(self, day: int, arc: TownArc) -> Memory:
        self.sync_town_arc_system_refs()
        return self.town_arc_system.create_town_arc_memory(
            day=day,
            arc=arc,
        )


   

    def remember_town_arc_for_all_agents(self, day, arc, reason):
        self.sync_town_arc_system_refs()
        self.town_arc_system.remember_town_arc_for_all_agents(
            day=day,
            arc=arc,
            reason=reason,
            agents=self.agents,
        )
    
    def get_relevant_town_arcs_for_context(self, location_id: str):
        self.sync_town_arc_system_refs()
        return self.town_arc_system.get_relevant_town_arcs_for_context(
            location_id=location_id,
        )
        
    def should_record_relationship_event(
        self,
        action: str,
        relationship_change: int,
    ) -> bool:
        return self.relationship_updater.should_record_relationship_event(
            action=action,
            relationship_change=relationship_change,
        )

    
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
        return self.relationship_updater.create_relationship_event(
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
            tags=tags,
        )


    def record_relationship_event(
        self,
        relationship_event: RelationshipEvent,
    ) -> None:
        self.relationship_updater.record_relationship_event(
            relationship_events=self.relationship_events,
            relationship_event=relationship_event,
        )


    def get_recent_relationship_events(
        self,
        agent_a: str,
        agent_b: str,
        limit: int = 3,
    ) -> list[RelationshipEvent]:
        return self.relationship_updater.get_recent_relationship_events(
            relationship_events=self.relationship_events,
            agent_a=agent_a,
            agent_b=agent_b,
            limit=limit,
        )
    
    
    def format_relationship_history_for_prompt(
        self,
        agent_a: str,
        agent_b: str,
        limit: int = 3,
    ) -> list[str]:
        return self.relationship_updater.format_relationship_history_for_prompt(
            relationship_events=self.relationship_events,
            agent_a=agent_a,
            agent_b=agent_b,
            limit=limit,
        )
        
    def sync_agent_relationships_from_manager(self) -> None:
        self.relationship_updater.sync_agent_relationships_from_manager(
            agents=self.agents,
        )
            
    def is_narration(self, conversation: str, speaker: Agent, listener: Agent) -> bool:
        return is_narration(
            conversation=conversation,
            speaker_name=speaker.name,
            listener_name=listener.name,
        )
        
    def maintain_agent_memories(self) -> None:
        for agent in self.agents:
            agent.prune_memory(active_memory_limit=200)
            agent.summarize_archived_memories(max_archive_size=500)
            
    def remember_dialogue(self, conversation: str, limit: int = 50) -> None:
        self.sync_conversation_policy_refs()
        self.conversation_policy.remember_dialogue(
            conversation=conversation,
            limit=limit,
        )
        self.recent_dialogues = self.conversation_policy.recent_dialogues


    def is_repeated_dialogue(self, conversation: str) -> bool:
        self.sync_conversation_policy_refs()
        return self.conversation_policy.is_repeated_dialogue(
            conversation=conversation,
        )

    def clean_dialogue_text(self, conversation: str) -> str:
        return clean_dialogue_text(conversation)
    
    def get_non_repeated_fallback_dialogue(
        self,
        speaker: Agent,
        listener: Agent,
        relationship_label: str,
        location_id: str | None = None,
        suggested_action: str = "chat",
    ) -> str:
        self.sync_conversation_policy_refs()
        return self.conversation_policy.get_non_repeated_fallback_dialogue(
            speaker=speaker,
            listener=listener,
            relationship_label=relationship_label,
            location_id=location_id,
            suggested_action=suggested_action,
        )
        
    def remember_action(self, action: str, limit: int = 50) -> None:
        self.sync_conversation_policy_refs()
        self.conversation_policy.remember_action(
            action=action,
            limit=limit,
        )
        self.recent_actions = self.conversation_policy.recent_actions


    def should_cap_action(self, action: str) -> bool:
        self.sync_conversation_policy_refs()
        return self.conversation_policy.should_cap_action(
            action=action,
        )

    def has_rumor_marker(self, conversation: str) -> bool: 
        return has_rumor_marker(conversation)
        
    def choose_final_action_with_reason(
        self,
        conversation: str,
        parsed_action: str,
        conversation_tags: list[str],
        allowed_actions: list[str],
        inferred_action: str | None = None,
    ) -> tuple[str, str]:
        self.sync_conversation_policy_refs()
        return self.conversation_policy.choose_final_action_with_reason(
            conversation=conversation,
            parsed_action=parsed_action,
            conversation_tags=conversation_tags,
            allowed_actions=allowed_actions,
            inferred_action=inferred_action,
        )


    def choose_final_action(
        self,
        conversation: str,
        parsed_action: str,
        conversation_tags: list[str],
        allowed_actions: list[str],
        inferred_action: str | None = None,
    ) -> str:
        self.sync_conversation_policy_refs()
        return self.conversation_policy.choose_final_action(
            conversation=conversation,
            parsed_action=parsed_action,
            conversation_tags=conversation_tags,
            allowed_actions=allowed_actions,
            inferred_action=inferred_action,
        )


    def get_previous_event_names(self, current_day: int) -> list[str]:
        return [
            event["name"]
            for event in self.daily_event_history
            if event["day"] < current_day
        ]


    def get_previous_event_keywords(self, current_day: int) -> list[str]:
        return get_previous_event_keywords(
            daily_event_history=self.daily_event_history,
            current_day=current_day,
        )


    def fix_stale_event_reference(self, conversation: str, current_day: int) -> str:
        return fix_stale_event_reference(
            conversation=conversation,
            current_day=current_day,
            current_daily_event=self.current_daily_event,
            daily_event_history=self.daily_event_history,
        )
        
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
        return self.persistence.load_agents_from_state(
            saved_state=saved_state,
        )


    def load_relationships_from_state(self, saved_state: dict) -> None:
        self.persistence.load_relationships_from_state(
            saved_state=saved_state,
            relationships=self.relationships,
        )
        
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
            if day == self.start_day and self.start_hour:
                active_hours = [
                    hour
                    for hour in hours
                    if hour > self.start_hour
                ]
            else:
                active_hours = hours
        
            if not active_hours:
                continue
        
            print(f"\n=== Day {day} ===")

            is_resuming_saved_day = (
                day == self.start_day
                and self.start_hour > 0
                and self.current_daily_event is not None
            )
            
            if not is_resuming_saved_day:
                self.current_daily_event = choose_daily_event()
            
                self.daily_event_history.append({
                    "day": day,
                    "id": self.current_daily_event.id,
                    "name": self.current_daily_event.name,
                })
            
                self.update_town_arcs(day)
            
                event_memory = self.create_daily_event_memory(day, self.current_daily_event)
                for agent in self.agents:
                    agent.remember(event_memory)
            
                self.update_agent_intents(day)
        
            print(
                f"Daily Event: {self.current_daily_event.name} - "
                f"{self.current_daily_event.description}"
            )
        
            for hour in active_hours:
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
        return self.relationship_updater.get_relationship_change(
            relationship_label=relationship_label,
        )

    def calculate_relationship_change(
        self,
        action: str,
        old_relationship_label: str,
        old_relationship_score: int,
    ) -> int:
        return self.relationship_updater.calculate_relationship_change(
            action=action,
            old_relationship_label=old_relationship_label,
            old_relationship_score=old_relationship_score,
            relationship_drift=self.get_relationship_change(old_relationship_label),
        )
        
    def adjust_action_weights_for_town_arcs(
        self,
        weights: dict[str, int],
        location_id: str,
        conversation_tags: list[str] | None = None,
    ) -> dict[str, int]:
        self.sync_town_arc_system_refs()
        return self.town_arc_system.adjust_action_weights_for_town_arcs(
            weights=weights,
            location_id=location_id,
            conversation_tags=conversation_tags,
        )
    
    def adjust_action_weights_for_intent(
        self,
        weights: dict[str, int],
        intent: AgentIntent | None,
        listener_name: str,
    ) -> dict[str, int]:
        self.sync_intent_system_refs()
        return self.intent_system.adjust_action_weights_for_intent(
            weights=weights,
            intent=intent,
            listener_name=listener_name,
        )
    

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
        return self.relationship_updater.apply_relationship_change(
            speaker=speaker,
            listener=listener,
            relationship_change=relationship_change,
        )

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
        return self.conversation_policy.choose_weighted_action(
            weights=weights,
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
        speaker_intent: AgentIntent | None = None,
        listener_intent: AgentIntent | None = None,
        suggested_action: str = "",
        parsed_action: str = "",
        inferred_action: str = "",
        base_action_weights: dict | None = None,
        intent_adjusted_weights: dict | None = None,
        allowed_actions: list[str] | None = None,
        final_action_reason: str = "",
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
            "suggested_action": suggested_action,
            "parsed_action": parsed_action,
            "inferred_action": inferred_action,
            "base_action_weights": base_action_weights or {},
            "intent_adjusted_weights": intent_adjusted_weights or {},
            "tags": tags or [],
            "allowed_actions" : allowed_actions or [], 
            "final_action_reason": final_action_reason,
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
            
            arc_adjusted_weights = self.adjust_action_weights_for_town_arcs(
                weights=intent_adjusted_weights,
                location_id=location_id,
                conversation_tags=[],
            )
            
            suggested_action = self.choose_weighted_action(arc_adjusted_weights)

            relationship_history = self.format_relationship_history_for_prompt(
                speaker.name,
                listener.name,
                limit=3,
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
                relationship_history=relationship_history,
                speaker_intent=speaker_intent.to_dict() if speaker_intent else None,
                listener_intent=listener_intent.to_dict() if listener_intent else None,
                town_arcs=self.get_relevant_town_arcs_for_context(location_id),
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

            if self.is_repeated_dialogue(conversation):
                conversation = self.get_non_repeated_fallback_dialogue(
                    speaker=speaker,
                    listener=listener,
                    relationship_label=old_relationship_label,
                    location_id=location_id,
                    suggested_action=suggested_action,
                )
                parsed_action = "chat"
            
            conversation = self.clean_dialogue_text(conversation)
            
            conversation_tags = infer_conversation_tags(conversation)
            conversation_tags.extend(parsed_output.get("tags", []))
            
            inferred_action = self.actions.infer_action(
                conversation,
                conversation_tags,
            )

            action, final_action_reason = self.choose_final_action_with_reason(
                conversation=conversation,
                parsed_action=parsed_action,
                conversation_tags=conversation_tags,
                allowed_actions=allowed_actions,
                inferred_action=inferred_action,
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

            self.apply_conversation_to_town_arcs(
                day=day,
                location_id=location_id,
                speaker=speaker,
                listener=listener,
                action=action,
                conversation_tags=conversation_tags,
            )
            

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
                suggested_action=suggested_action,
                parsed_action=parsed_action,
                inferred_action=inferred_action,
                base_action_weights=base_action_weights,
                intent_adjusted_weights=intent_adjusted_weights,
                allowed_actions=allowed_actions,
                final_action_reason=final_action_reason,
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
