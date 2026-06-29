import json
import random
from pathlib import Path

from src.simulation.conversation_runner import ConversationRunner
from src.simulation.conversation_effects_applier import ConversationEffectsApplier
from src.simulation.conversation_output_processor import ConversationOutputProcessor
from src.simulation.conversation_context_preparer import ConversationContextPreparer
from src.simulation.conversation_selector import ConversationSelector 
from src.simulation.conversation_tagger import ConversationTagger
from src.simulation.conversation_recorder import ConversationRecorder
from src.simulation.activity_system import ActivitySystem
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
from src.llm.parser import clean_conversation_output, parse_llm_conversation_output
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
        self.conversation_recorder = ConversationRecorder(
            logger=self.logger,
        )
        self.conversation_runner = ConversationRunner()
        self.conversation_tagger = ConversationTagger()
        self.relationships = RelationshipManager()
        self.conversation_selector = ConversationSelector(
            relationships=self.relationships,
        )
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
        self.activity_system = ActivitySystem(
            activity_planner=self.activity_planner,
            logger=self.logger,
            activity_records=self.activity_records,
        )
        self.recent_dialogues = [] 
        self.recent_actions = []
        self.conversation_policy = ConversationPolicy(
            actions=self.actions,
            recent_dialogues=self.recent_dialogues,
            recent_actions=self.recent_actions,
        )
        self.conversation_output_processor = ConversationOutputProcessor(
            conversation_policy=self.conversation_policy,
        )
        self.daily_event_history = []
        self.relationship_events = []
        self.town_arcs = []
        self.town_arc_change_records = []
        self.town_arc_system = TownArcSystem(
            town_arcs=self.town_arcs,
            town_arc_change_records=self.town_arc_change_records,
        )
        self.conversation_effects_applier = ConversationEffectsApplier(
            actions=self.actions,
            relationship_updater=self.relationship_updater,
            town_arc_system=self.town_arc_system,
            conversation_recorder=self.conversation_recorder,
            conversation_policy=self.conversation_policy,
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
        self.conversation_context_preparer = ConversationContextPreparer(
            relationships=self.relationships,
            actions=self.actions,
            social_policy=self.social_policy,
            intent_system=self.intent_system,
            conversation_policy=self.conversation_policy,
            relationship_updater=self.relationship_updater,
            town_arc_system=self.town_arc_system,
        )

    def apply_conversation_effects(
        self,
        day: int,
        hour: int,
        location_id: str,
        speaker: Agent,
        listener: Agent,
        action: str,
        conversation: str,
        conversation_tags: list[str],
        old_relationship_label: str,
        old_score: int,
    ) -> dict:
        self.sync_town_arc_system_refs()
        self.sync_conversation_policy_refs()
        self.sync_conversation_effects_applier_refs()

        result = self.conversation_effects_applier.apply_conversation_effects(
            day=day,
            hour=hour,
            location_id=location_id,
            speaker=speaker,
            listener=listener,
            action=action,
            conversation=conversation,
            conversation_tags=conversation_tags,
            old_relationship_label=old_relationship_label,
            old_score=old_score,
            relationship_events=self.relationship_events,
        )

        self.recent_dialogues = self.conversation_policy.recent_dialogues
        self.recent_actions = self.conversation_policy.recent_actions

        return result
        
    def process_conversation_output(
        self,
        raw_output: str,
        allowed_actions: list[str],
        speaker: Agent,
        listener: Agent,
        old_relationship_label: str,
        location_id: str,
        suggested_action: str,
        current_day: int,
    ) -> dict:
        self.sync_conversation_policy_refs()
        self.sync_conversation_output_processor_refs()

        return self.conversation_output_processor.process_llm_output(
            raw_output=raw_output,
            allowed_actions=allowed_actions,
            speaker=speaker,
            listener=listener,
            old_relationship_label=old_relationship_label,
            location_id=location_id,
            suggested_action=suggested_action,
            current_day=current_day,
            current_daily_event=self.current_daily_event,
            daily_event_history=self.daily_event_history,
        )
        
    def sync_conversation_context_preparer_refs(self) -> None:
        self.conversation_context_preparer.relationships = self.relationships
        self.conversation_context_preparer.intent_system = self.intent_system
        self.conversation_context_preparer.conversation_policy = self.conversation_policy
        self.conversation_context_preparer.relationship_updater = self.relationship_updater
        self.conversation_context_preparer.town_arc_system = self.town_arc_system

    def sync_conversation_output_processor_refs(self) -> None:
        self.conversation_output_processor.conversation_policy = self.conversation_policy
        
    def sync_activity_system_refs(self) -> None:
        self.activity_system.activity_records = self.activity_records
        
    def sync_intent_system_refs(self) -> None:
        self.intent_system.agent_intents = self.agent_intents

    def sync_conversation_policy_refs(self) -> None:
        self.conversation_policy.recent_dialogues = self.recent_dialogues
        self.conversation_policy.recent_actions = self.recent_actions
        
    def get_activity_need_effects(self, activity) -> dict[str, int]:
        return self.activity_system.get_activity_need_effects(activity)
        
    def sync_town_arc_system_refs(self) -> None:
        self.town_arc_system.town_arcs = self.town_arcs
        self.town_arc_system.town_arc_change_records = self.town_arc_change_records

    def sync_conversation_effects_applier_refs(self) -> None:
        self.conversation_effects_applier.actions = self.actions
        self.conversation_effects_applier.relationship_updater = self.relationship_updater
        self.conversation_effects_applier.town_arc_system = self.town_arc_system
        self.conversation_effects_applier.conversation_recorder = self.conversation_recorder
        self.conversation_effects_applier.conversation_policy = self.conversation_policy
        

    def get_initial_conversation_tags(
        self,
        conversation: str,
        parsed_tags: list[str] | None = None,
    ) -> list[str]:
        return self.conversation_tagger.get_initial_conversation_tags(
            conversation=conversation,
            parsed_tags=parsed_tags,
        )

    def prepare_conversation_context(
        self,
        location_id: str,
        speaker: Agent,
        listener: Agent,
        current_day: int,
    ) -> dict:
        self.sync_intent_system_refs()
        self.sync_town_arc_system_refs()
        self.sync_conversation_policy_refs()
        self.sync_conversation_context_preparer_refs()

        return self.conversation_context_preparer.prepare_conversation_context(
            location_id=location_id,
            speaker=speaker,
            listener=listener,
            current_day=current_day,
            current_daily_event=self.current_daily_event,
            agent_intents=self.agent_intents,
            relationship_events=self.relationship_events,
        )
        
    def finalize_conversation_tags(
        self,
        conversation: str,
        conversation_tags: list[str],
        relationship_label: str,
        action: str,
    ) -> list[str]:
        return self.conversation_tagger.finalize_conversation_tags(
            conversation=conversation,
            conversation_tags=conversation_tags,
            current_daily_event=self.current_daily_event,
            relationship_label=relationship_label,
            action=action,
        )

    
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
        self.sync_activity_system_refs()
        self.sync_conversation_policy_refs()
        self.sync_conversation_output_processor_refs()
    
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
        self.sync_activity_system_refs()
        self.activity_system.log_activity_event(
            day=day,
            hour=hour,
            agent=agent,
            activity=activity,
        )
        self.activity_records = self.activity_system.activity_records
        
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

    def run_agent_activities(self, day: int, hour: int) -> None:
        self.sync_activity_system_refs()
        location_ids = [location.id for location in self.locations]

        self.activity_system.run_agent_activities(
            agents=self.agents,
            location_ids=location_ids,
            day=day,
            hour=hour,
            current_daily_event=self.current_daily_event,
            agent_intents=self.agent_intents,
        )

        self.activity_records = self.activity_system.activity_records
        
    def run_tick(self, day: int, hour: int) -> None:
        self.run_agent_activities(day, hour)
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
    
        
    def group_agents_by_location(self) -> dict[str, list[Agent]]:
        return self.conversation_selector.group_agents_by_location(
            agents=self.agents,
        )

    def choose_conversation_pair(self, agents_here: list[Agent]) -> tuple[Agent, Agent]:
        return self.conversation_selector.choose_conversation_pair(
            agents_here=agents_here,
            intent_bonus_fn=self.get_intent_listener_weight_bonus,
        )

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
        
    def remember_conversation_for_agents(
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
        return self.conversation_recorder.remember_conversation_for_agents(
            day=day,
            hour=hour,
            location_id=location_id,
            speaker=speaker,
            listener=listener,
            conversation=conversation,
            relationship_change=relationship_change,
            tags=tags,
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
        return self.conversation_recorder.create_conversation_memory(
            day=day,
            hour=hour,
            location_id=location_id,
            speaker=speaker,
            listener=listener,
            conversation=conversation,
            relationship_change=relationship_change,
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
        self.conversation_recorder.log_conversation_event(
            day=day,
            hour=hour,
            location_id=location_id,
            speaker=speaker,
            listener=listener,
            conversation=conversation,
            relationship_change=relationship_change,
            new_score=new_score,
            relationship_label=relationship_label,
            action=action,
            action_source=action_source,
            action_reason=action_reason,
            tags=tags,
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
        self.conversation_recorder.print_conversation_event(
            day=day,
            hour=hour,
            location_id=location_id,
            conversation=conversation,
            relationship_label=relationship_label,
            new_score=new_score,
            relationship_change=relationship_change,
            action=action,
        )
        
    def generate_conversations(self, day: int, hour: int) -> None:
        self.conversation_runner.generate_conversations(
            engine=self,
            day=day,
            hour=hour,
        )
        

    def print_relationships(self):
        print("\n=== Final Relationships ===")

        for agent in self.agents:
            print(f"\n{agent.name}:")
            for other_name, score in agent.relationships.items():
                label = self.relationships.describe_relationship(agent.name, other_name)
                print(f"  {other_name}: {label} ({score:+d})")
