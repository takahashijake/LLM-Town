import json
from pathlib import Path
from src.simulation.journal_system import JournalSystem
from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.agents.intent import AgentIntent
from src.agents.memory import Memory
from src.agents.relationships import RelationshipManager
from src.analysis.report import SimulationReporter
from src.behavior.intent_planner import IntentPlanner
from src.behavior.goal_planner import GoalPlanner
from src.behavior.planner import ActivityPlanner
from src.behavior.social_policy import SocialBehaviorPolicy
from src.llm.client import TransformersLLMClient
from src.simulation.simulation_loop import SimulationLoop
from src.simulation.activity_system import ActivitySystem
from src.simulation.conversation_context_preparer import ConversationContextPreparer
from src.simulation.conversation_effects_applier import ConversationEffectsApplier
from src.simulation.conversation_output_processor import ConversationOutputProcessor
from src.simulation.conversation_policy import ConversationPolicy
from src.simulation.conversation_recorder import ConversationRecorder
from src.simulation.conversation_runner import ConversationRunner
from src.simulation.conversation_selector import ConversationSelector
from src.simulation.conversation_tagger import ConversationTagger
from src.simulation.intent_system import IntentSystem
from src.simulation.persistence import SimulationPersistence
from src.simulation.relationship_updater import RelationshipUpdater
from src.simulation.state import SimulationState
from src.simulation.town_arc_system import TownArcSystem
from src.town.daily_event import DailyEvent, choose_daily_event
from src.town.location import Location
from src.town.town_arc import TownArc
from src.utils.logger import TownLogger
from src.systems.reputation import ReputationSystem
from src.systems.economy import EconomySystem
from src.systems.materials import MaterialSystem
from src.systems.crime import CrimeSystem
from src.systems.justice import JusticeSystem

class SimulationEngine:
    def __init__(
        self,
        agents_path: str,
        locations_path: str,
        load_state: bool = False,
        llm_client=None,
        state_path: str | Path = "data/save_state.json",
        logs_dir: str | Path = "logs",
        max_conversation_turns: int = 4,
        economy_path: str | Path = "data/economy.json",
        materials_path: str | Path = "data/materials.json",
        crime_path: str | Path = "data/crime.json",
        justice_path: str | Path = "data/justice.json",
    ):
        self.state_path = Path(state_path)
        self.logs_dir = Path(logs_dir)
        self.economy_path = Path(economy_path)
        if not self.economy_path.is_absolute() and not self.economy_path.is_file():
            sibling_config = Path(agents_path).resolve().parent / "economy.json"
            if sibling_config.is_file():
                self.economy_path = sibling_config
        self.materials_path = Path(materials_path)
        if not self.materials_path.is_absolute() and not self.materials_path.is_file():
            sibling_config = Path(agents_path).resolve().parent / "materials.json"
            if sibling_config.is_file():
                self.materials_path = sibling_config
        self.crime_path = Path(crime_path)
        if not self.crime_path.is_absolute() and not self.crime_path.is_file():
            sibling_config = Path(agents_path).resolve().parent / "crime.json"
            if sibling_config.is_file():
                self.crime_path = sibling_config
        self.justice_path = Path(justice_path)
        if not self.justice_path.is_absolute() and not self.justice_path.is_file():
            sibling_config = Path(agents_path).resolve().parent / "justice.json"
            if sibling_config.is_file():
                self.justice_path = sibling_config
        self.locations = self.load_locations(locations_path)
        self.logger = TownLogger(logs_dir=self.logs_dir)
        self.conversation_recorder = ConversationRecorder(
            logger=self.logger,
        )
        self.max_conversation_turns = max(1, int(max_conversation_turns))
        self.conversation_runner = ConversationRunner(
            max_turns=self.max_conversation_turns
        )
        self.conversation_tagger = ConversationTagger()
        self.relationships = RelationshipManager()
        self.conversation_selector = ConversationSelector(
            relationships=self.relationships,
        )
        self.state = SimulationState(path=self.state_path)
        self.persistence = SimulationPersistence()
        self.economy = None
        self.materials = None
        self.crime = None
        self.justice = None
        self.simulation_loop = SimulationLoop()
        self.journal_system = JournalSystem()
        self.llm = llm_client or TransformersLLMClient()
        self.actions = ActionSystem()
        self.reputation_updates = []
        self.reputation_system = ReputationSystem(
            actions=self.actions,
            update_records=self.reputation_updates,
        )
        self.relationship_updater = RelationshipUpdater(
            relationships=self.relationships,
            actions=self.actions,
        )
        self.activity_planner = ActivityPlanner()
        self.social_policy = SocialBehaviorPolicy()
        self.intent_planner = IntentPlanner() 
        self.goal_planner = GoalPlanner()
        self.agent_intents = {}
        self.intent_history = []
        self.intent_system = IntentSystem(
            intent_planner=self.intent_planner,
            agent_intents=self.agent_intents,
            goal_planner=self.goal_planner,
        )
        self.current_daily_event = None
        self.resume_day_complete = False
        
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
            arc_changes_path=self.logs_dir / "town_arc_changes.jsonl",
        )
        self.conversation_effects_applier = ConversationEffectsApplier(
            actions=self.actions,
            relationship_updater=self.relationship_updater,
            town_arc_system=self.town_arc_system,
            conversation_recorder=self.conversation_recorder,
            conversation_policy=self.conversation_policy,
            reputation_system=self.reputation_system,
        )
        if saved_state:
            self.reputation_updates = list(
                saved_state.get("reputation_updates", [])
            )
            self.reputation_system.update_records = self.reputation_updates
            self.resume_day_complete = bool(
                saved_state.get(
                    "day_complete",
                    False,
                )
            )
        
            self.load_run_continuity_from_state(
                saved_state
            )
        
            self.agents = self.load_agents_from_state(
                saved_state
            )
        
            self.load_relationships_from_state(
                saved_state
            )
        
            self.load_agent_intents_from_state(
                saved_state
            )
        
            self.load_intent_history_from_state(
                saved_state
            )
        
            self.load_relationship_events_from_state(
                saved_state
            )
        
            self.load_town_arcs_from_state(
                saved_state
            )
        
            self.town_arc_system = TownArcSystem(
                town_arcs=self.town_arcs,
                town_arc_change_records=(
                    self.town_arc_change_records
                ),
                arc_changes_path=self.logs_dir / "town_arc_changes.jsonl",
            )
        
            self.sync_agent_relationships_from_manager()
        
            self.start_day = saved_state["current_day"]
            self.start_hour = saved_state["current_hour"]
        else:
            self.agents = self.load_agents(
                agents_path
            )
            self.start_day = 1
            self.start_hour = 0
        self.economy = (
            self.persistence.load_economy_from_state(saved_state)
            if saved_state
            else None
        )
        if self.economy is None:
            self.economy = EconomySystem.from_config(
                self.economy_path,
                self.agents,
            )
        self.materials = (
            self.persistence.load_materials_from_state(
                saved_state,
                economy=self.economy,
            )
            if saved_state
            else None
        )
        if self.materials is None:
            self.materials = MaterialSystem.from_config(
                self.materials_path,
                economy=self.economy,
                agents=self.agents,
            )
        self.crime = (
            self.persistence.load_crime_from_state(
                saved_state,
                materials=self.materials,
                agents=self.agents,
                reputation_system=self.reputation_system,
            )
            if saved_state
            else None
        )
        if self.crime is None:
            self.crime = CrimeSystem.from_config(
                self.crime_path,
                materials=self.materials,
                agents=self.agents,
                reputation_system=self.reputation_system,
            )
        self.justice = (
            self.persistence.load_justice_from_state(
                saved_state, crime=self.crime, materials=self.materials,
                agents=self.agents, reputation_system=self.reputation_system,
            )
            if saved_state else None
        )
        if self.justice is None:
            self.justice = JusticeSystem.from_config(
                self.justice_path, crime=self.crime, materials=self.materials,
                agents=self.agents, reputation_system=self.reputation_system,
            )
        self.activity_system.economy_system = self.economy
        self.activity_system.material_system = self.materials
        self.activity_system.crime_system = self.crime
        self.conversation_context_preparer = ConversationContextPreparer(
            relationships=self.relationships,
            actions=self.actions,
            social_policy=self.social_policy,
            intent_system=self.intent_system,
            conversation_policy=self.conversation_policy,
            relationship_updater=self.relationship_updater,
            town_arc_system=self.town_arc_system,
            reputation_system=self.reputation_system,
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
        rumor_claim: dict | None = None,
        outcome: str = "completed",
        remember: bool = True,
        effect_eligible: bool = True,
        effect_suppression_reason: str = "",
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
            rumor_claim=rumor_claim,
            outcome=outcome,
            remember=remember,
            effect_eligible=effect_eligible,
            effect_suppression_reason=effect_suppression_reason,
        )

        self.recent_dialogues = self.conversation_policy.recent_dialogues
        self.recent_actions = self.conversation_policy.recent_actions

        return result

    def update_intents_after_conversation(
        self,
        day: int,
        location_id: str,
        speaker: Agent,
        listener: Agent,
        action: str,
        relationship_change: int,
        new_score: int,
        conversation_tags: list[str],
    ) -> dict | None:
        self.sync_intent_system_refs()
        self.intent_system._engine_for_goal_check = self
    
        result = self.intent_system.update_intents_after_conversation(
            day=day,
            location_id=location_id,
            speaker=speaker,
            listener=listener,
            action=action,
            relationship_change=relationship_change,
            new_score=new_score,
            conversation_tags=conversation_tags,
        )
    
        self.agent_intents = self.intent_system.agent_intents
        self.intent_history = self.intent_system.intent_history
    
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
        conversation_context: dict | None = None,
        enforce_information_boundaries: bool = False,
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
            conversation_context=conversation_context,
            enforce_information_boundaries=enforce_information_boundaries,
        )
        
    def sync_conversation_context_preparer_refs(self) -> None:
        self.conversation_context_preparer.relationships = self.relationships
        self.conversation_context_preparer.intent_system = self.intent_system
        self.conversation_context_preparer.conversation_policy = self.conversation_policy
        self.conversation_context_preparer.relationship_updater = self.relationship_updater
        self.conversation_context_preparer.town_arc_system = self.town_arc_system
        self.conversation_context_preparer.reputation_system = self.reputation_system

    def sync_conversation_output_processor_refs(self) -> None:
        self.conversation_output_processor.conversation_policy = self.conversation_policy
        
    def sync_activity_system_refs(self) -> None:
        self.activity_system.activity_records = self.activity_records
        self.activity_system.economy_system = getattr(self, "economy", None)
        self.activity_system.material_system = getattr(self, "materials", None)
        self.activity_system.crime_system = getattr(self, "crime", None)
        
    def sync_intent_system_refs(self) -> None:
        self.intent_system.agent_intents = self.agent_intents
        self.intent_system.intent_history = self.intent_history

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
        self.conversation_effects_applier.reputation_system = self.reputation_system
        

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
        session_transcript: list[dict] | None = None,
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
            session_transcript=session_transcript,
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

    def load_intent_history_from_state(self, saved_state: dict) -> None:
        self.intent_history = self.persistence.load_intent_history_from_state(
            saved_state=saved_state,
        )
        self.sync_intent_system_refs()
    
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
        
        
    def sync_agent_relationships_from_manager(self) -> None:
        self.relationship_updater.sync_agent_relationships_from_manager(
            agents=self.agents,
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

    def load_locations(self, path: str) -> list[Location]:
        with open(path, "r") as f:
            data = json.load(f)

        return [Location(**location_data) for location_data in data]
    
    def run(self, days: int, hours: list[int]) -> None:
        self.simulation_loop.run(
            engine=self,
            days=days,
            hours=hours,
        )

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
        self.sync_intent_system_refs()
        self.intent_system._engine_for_goal_check = self
        for agent in self.agents:
            self.intent_system.update_intent_after_activity(
                day=day,
                agent=agent,
                location_id=agent.location_id,
                activity_name=agent.current_activity,
            )
        self.agent_intents = self.intent_system.agent_intents
        self.intent_history = self.intent_system.intent_history
        
    def run_tick(self, day: int, hour: int) -> None:
        self.simulation_loop.run_tick(
            engine=self,
            day=day,
            hour=hour,
        )

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
        inference_reason: str = "",
        base_action_weights: dict | None = None,
        relationship_adjusted_weights: dict | None = None,
        relationship_weight_adjustments: dict | None = None,
        relationship_decision_reasons: list[str] | None = None,
        relationship_snapshot: dict | None = None,
        retrieved_social_memories: list[str] | None = None,
        relationship_updates: dict | None = None,
        intent_adjusted_weights: dict | None = None,
        reputation_adjusted_weights: dict | None = None,
        reputation_weight_adjustments: dict | None = None,
        allowed_actions: list[str] | None = None,
        final_action_reason: str = "",
        raw_response: str = "",
        generation_error: str = "",
        context_evidence: dict | None = None,
        context_snapshot: dict | None = None,
        dialogue_source: str = "llm",
        reputation_updates: list[dict] | None = None,
        rumor_transmission: dict | None = None,
        session_id: str = "",
        turn_index: int = 0,
        response_to_turn: int | None = None,
        response_outcome: str | None = None,
        termination_reason: str = "",
        generation_attempt_count: int = 1,
        regenerated_for_repetition: bool = False,
        regenerated_for_grounding: bool = False,
        grounding_valid: bool = True,
        grounding_reason: str = "",
        grounding_candidate_type: str = "",
        grounding_refs: list[str] | None = None,
        invalid_grounding_refs: list[str] | None = None,
        effect_applied: bool = True,
        effect_suppressed: bool = False,
        effect_suppression_reason: str = "",
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
            inference_reason=inference_reason,
            base_action_weights=base_action_weights,
            relationship_adjusted_weights=relationship_adjusted_weights,
            relationship_weight_adjustments=relationship_weight_adjustments,
            relationship_decision_reasons=relationship_decision_reasons,
            relationship_snapshot=relationship_snapshot,
            retrieved_social_memories=retrieved_social_memories,
            relationship_updates=relationship_updates,
            intent_adjusted_weights=intent_adjusted_weights,
            reputation_adjusted_weights=reputation_adjusted_weights,
            reputation_weight_adjustments=reputation_weight_adjustments,
            allowed_actions=allowed_actions,
            final_action_reason=final_action_reason,
            raw_response=raw_response,
            generation_error=generation_error,
            context_evidence=context_evidence,
            context_snapshot=context_snapshot,
            dialogue_source=dialogue_source,
            reputation_updates=reputation_updates,
            rumor_transmission=rumor_transmission,
            session_id=session_id,
            turn_index=turn_index,
            response_to_turn=response_to_turn,
            response_outcome=response_outcome,
            termination_reason=termination_reason,
            generation_attempt_count=generation_attempt_count,
            regenerated_for_repetition=regenerated_for_repetition,
            regenerated_for_grounding=regenerated_for_grounding,
            grounding_valid=grounding_valid,
            grounding_reason=grounding_reason,
            grounding_candidate_type=grounding_candidate_type,
            grounding_refs=grounding_refs,
            invalid_grounding_refs=invalid_grounding_refs,
            effect_applied=effect_applied,
            effect_suppressed=effect_suppressed,
            effect_suppression_reason=effect_suppression_reason,
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
