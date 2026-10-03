import json
from copy import deepcopy
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
from src.llm.context import _prune_context_to_budget
from src.simulation.simulation_loop import SimulationLoop
from src.simulation.activity_system import ActivitySystem
from src.simulation.conversation_context_preparer import ConversationContextPreparer
from src.simulation.conversation_effects_applier import ConversationEffectsApplier
from src.simulation.conversation_output_processor import ConversationOutputProcessor
from src.simulation.conversation_policy import ConversationPolicy
from src.simulation.conversation_recorder import ConversationRecorder
from src.simulation.conversation_runner import ConversationRunner
from src.simulation.conversation_scheduler import ConversationScheduler
from src.simulation.conversation_execution import (
    BatchedConversationExecutionBackend,
    ConcurrentConversationExecutionBackend,
    SerialConversationExecutionBackend,
)
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
from src.systems.economy import EconomySystem, Employment
from src.systems.materials import (
    MaterialSystem, ProductionRecipe, PurchaseActivityRule, Seller,
)
from src.systems.crime import CrimeSystem
from src.systems.justice import JusticeSystem
from src.systems.commitments import CommitmentSystem
from src.systems.plans import PlanSystem
from src.systems.outcome_memory import KnowledgeRecipient, OutcomeMemorySystem
from src.systems.town_growth import MigrationRecord, TownGrowthSystem
from src.systems.location_growth import (
    LocationActivationRecord,
    LocationGrowthSystem,
)
from src.systems.event_ecology import EventEcologySystem
from src.systems.institution_growth import InstitutionGrowthSystem
from src.systems.commerce_growth import CommerceGrowthSystem

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
        conversation_execution: str = "serial",
        conversation_workers: int = 4,
        conversation_batch_size: int = 4,
        simulation_seed: int = 0,
        town_growth_path: str | Path = "data/town_growth.json",
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
        self.town_growth_path = Path(town_growth_path)
        self.simulation_seed = int(simulation_seed)
        if (
            not self.town_growth_path.is_absolute()
            and not self.town_growth_path.is_file()
        ):
            sibling_config = Path(agents_path).resolve().parent / "town_growth.json"
            if sibling_config.is_file():
                self.town_growth_path = sibling_config
        self.locations = self.load_locations(locations_path)
        self.logger = TownLogger(logs_dir=self.logs_dir)
        self.conversation_recorder = ConversationRecorder(
            logger=self.logger,
        )
        self.max_conversation_turns = max(1, int(max_conversation_turns))
        self.conversation_runner = ConversationRunner(
            max_turns=self.max_conversation_turns
        )
        self.conversation_scheduler = ConversationScheduler(seed=simulation_seed)
        if conversation_execution == "serial":
            self.conversation_execution_backend = SerialConversationExecutionBackend()
        elif conversation_execution == "concurrent":
            self.conversation_execution_backend = ConcurrentConversationExecutionBackend(
                max_workers=conversation_workers,
            )
        elif conversation_execution == "batched":
            if llm_client is not None and not callable(
                getattr(llm_client, "generate_conversation_batch", None)
            ):
                raise TypeError(
                    "batched conversation execution requires an LLM client with "
                    "generate_conversation_batch(requests)"
                )
            self.conversation_execution_backend = BatchedConversationExecutionBackend(
                batch_size=conversation_batch_size,
            )
        else:
            raise ValueError(
                "conversation_execution must be 'serial', 'concurrent', or 'batched'"
            )
        self.last_social_tick = {}
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
        self.grounded_dialogue_capability_tier = getattr(
            self.llm, "grounded_dialogue_capability_tier", "unverified"
        )
        self.actions = ActionSystem()
        self.reputation_updates = []
        self.reputation_system = ReputationSystem(
            actions=self.actions,
            update_records=self.reputation_updates,
        )
        self.commitment_grounding_enabled = True
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
        self.outcome_memory = OutcomeMemorySystem(self.agents)
        self.crime.outcome_memory = self.outcome_memory
        self.justice.outcome_memory = self.outcome_memory
        self.commitment_system = CommitmentSystem.from_dict(
            saved_state.get("commitments") if saved_state else None,
            relationships=self.relationships,
            reputation_system=self.reputation_system,
            agents=self.agents,
            materials=self.materials,
            location_ids=[location.id for location in self.locations],
            outcome_memory=self.outcome_memory,
        )
        self.plan_system = PlanSystem.from_dict(
            saved_state.get("plans") if saved_state else None,
            commitment_system=self.commitment_system,
            agents=self.agents,
            outcome_memory=self.outcome_memory,
            materials=self.materials,
        )
        self.commitment_system.plan_system = self.plan_system
        self.town_growth = TownGrowthSystem.from_config(
            self.town_growth_path,
            self.agents,
            saved_state.get("town_growth") if saved_state else None,
        )
        self.location_growth = LocationGrowthSystem.from_config(
            self.town_growth_path,
            self.locations,
            saved_state.get("location_growth") if saved_state else None,
        )
        self.locations.extend(self.location_growth.activated_locations())
        self.event_ecology = EventEcologySystem.from_config(
            self.town_growth_path,
            simulation_seed=self.simulation_seed,
            state=saved_state.get("event_ecology") if saved_state else None,
        )
        self.institution_growth = InstitutionGrowthSystem.from_config(
            self.town_growth_path,
            saved_state.get("institution_growth") if saved_state else None,
        )
        self.commerce_growth = CommerceGrowthSystem.from_config(
            self.town_growth_path,
            saved_state.get("commerce_growth") if saved_state else None,
        )
        self.activity_planner.set_location_affinities([
            location for location in self.locations
            if location.id not in self.location_growth.base_location_ids
        ])
        self.outcome_memory.bind_authorities(
            commitments=self.commitment_system, plans=self.plan_system,
            crime=self.crime, justice=self.justice, materials=self.materials,
            town_growth=self.town_growth, location_growth=self.location_growth,
            institution_growth=self.institution_growth,
            commerce_growth=self.commerce_growth,
        )
        self.validate_population_authorities()
        self.validate_location_authorities()
        self.validate_event_authorities()
        self.validate_institution_authorities()
        self.validate_commerce_authorities()
        self.activity_planner.set_commerce_authority(self.materials)
        self.activity_system.economy_system = self.economy
        self.activity_system.material_system = self.materials
        self.activity_system.crime_system = self.crime
        self.activity_system.commitment_system = self.commitment_system
        self.activity_system.plan_system = self.plan_system
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
        evidence_key: str | None = None,
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
            evidence_key=evidence_key,
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
        self.activity_system.commitment_system = getattr(self, "commitment_system", None)
        self.activity_system.plan_system = getattr(self, "plan_system", None)
        if getattr(self, "materials", None) is not None:
            self.activity_planner.set_commerce_authority(self.materials)
        
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

        economy = getattr(self, "economy", None)
        if economy is not None:
            employment = economy.employment_for_agent(speaker.id)
            speaker.authoritative_employment_title = (
                employment.title
                if employment and employment.active
                and current_day >= employment.start_day else ""
            )

        result = self.conversation_context_preparer.prepare_conversation_context(
            location_id=location_id,
            speaker=speaker,
            listener=listener,
            current_day=current_day,
            current_daily_event=self.current_daily_event,
            agent_intents=self.agent_intents,
            relationship_events=self.relationship_events,
            session_transcript=session_transcript,
        )
        requests = getattr(self, "goal_delegation_requests", None)
        if requests is None and getattr(self, "plan_system", None) is not None:
            requests = self.plan_system.delegation_requests()
        prior_speakers = {
            row.get("speaker") for row in (session_transcript or [])
        }
        delegation = next((item for item in (requests or [])
                           if item["owner_id"] == speaker.id
                           and item["helper_id"] == listener.id
                           and speaker.name not in prior_speakers
                           and "ask_for_help" in result["allowed_actions"]), None)
        if delegation:
            provenance_keys = (
                "owner_id", "source_goal_id", "plan_id", "revision", "strategy",
                "helper_id", "task_code", "target_location", "request_id",
            )
            result["goal_delegation_provenance"] = {
                key: delegation[key] for key in provenance_keys
            }
            # Only fixed human-readable semantics enter the model-visible context.
            result["context"]["bounded_goal_request"] = {
                "task": delegation["task"],
                "location": delegation["target_location"],
                "utterance": (
                    f"Could you help me with research at the "
                    f"{delegation['target_location'].replace('_', ' ')} tomorrow?"
                ),
            }
        result["context"]["active_commitments"] = (
            self.commitment_system.relevant_context(speaker.id, listener.id, current_day)
            if self.commitment_grounding_enabled else []
        )
        result["context"]["commitment_records"] = (
            self.commitment_system.relevant_context_records(speaker.id, listener.id, current_day)
            if self.commitment_grounding_enabled else []
        )
        for record in result["context"]["commitment_records"]:
            record.update(self.plan_system.context_for_commitment(record["commitment_id"]))
            if record["status"] == "accepted" and record.get("repair_of_commitment_id"):
                record["lifecycle_state"] = "repair_successor_active"
            elif record["status"] == "accepted":
                record["lifecycle_state"] = record.get("plan_stage", "pending")
            else:
                record["lifecycle_state"] = record["status"]
        result["context"]["repair_opportunities"] = (
            self.commitment_system.repair_opportunities(
                speaker.id, listener.id, day=current_day,
            ) if self.commitment_grounding_enabled else []
        )
        _prune_context_to_budget(result["context"])
        return result
        
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

    def preflight_resident_registration(self, record: MigrationRecord) -> Agent:
        """Validate every authority before exposing a proposed resident."""
        if record.status != "proposed":
            raise ValueError("migration is not pending activation")
        self.validate_population_authorities()
        template = self.town_growth.template(record.template_id)
        if record.arrival_location_id not in {item.id for item in self.locations}:
            raise ValueError("arrival location is unavailable")
        if any(item.id == record.agent_id for item in self.agents):
            raise ValueError("resident id is already registered")
        if any(item.name == template.name for item in self.agents):
            raise ValueError("resident name is already registered")
        account_id = f"account:agent:{record.agent_id}"
        inventory_id = f"inventory:agent:{record.agent_id}"
        if not self.economy.can_register_agent_account(record.agent_id, account_id):
            raise ValueError("resident account cannot be registered")
        if not self.materials.can_register_agent_inventory(
            record.agent_id,
            account_id,
            inventory_id,
            allow_pending_account=True,
        ):
            raise ValueError("resident inventory cannot be registered")
        source = self.economy.get_account(
            self.town_growth.policy.settlement_source_account_id
        )
        if source.balance < self.town_growth.policy.settlement_grant:
            raise ValueError("settlement source has insufficient funds")
        settlement_event_key = f"migration-settlement:{record.id}"
        if settlement_event_key in self.economy.applied_event_keys:
            raise ValueError("settlement event was already applied")
        resident = Agent(
            id=record.agent_id,
            name=template.name,
            personality=template.personality,
            occupation="unemployed",
            location_id=record.arrival_location_id,
            goals=list(template.goals),
            needs=dict(template.initial_needs),
        )
        checks = (
            self.commitment_system.can_register_agent(resident),
            self.plan_system.can_register_agent(resident),
            self.crime.can_register_agent(resident),
            self.justice.can_register_agent(resident),
            self.outcome_memory.can_register_agent(resident),
        )
        if not all(checks):
            raise ValueError("resident is incompatible with a cached authority")
        return resident

    def validate_population_authorities(self) -> None:
        """Fail closed when population, migration, money, or goods disagree."""
        agent_ids = [agent.id for agent in self.agents]
        agent_names = [agent.name for agent in self.agents]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("resident ids must be unique")
        if len(agent_names) != len(set(agent_names)):
            raise ValueError("resident names must be unique")
        registered_ids = set(agent_ids)
        account_owner_ids = [
            account.owner_id for account in self.economy.accounts.values()
            if account.owner_type == "agent"
        ]
        inventory_owner_ids = [
            inventory.owner_id for inventory in self.materials.inventories.values()
            if inventory.owner_type == "agent"
        ]
        if (
            set(account_owner_ids) != registered_ids
            or len(account_owner_ids) != len(agent_ids)
        ):
            raise ValueError("resident account registry does not match population")
        if (
            set(inventory_owner_ids) != registered_ids
            or len(inventory_owner_ids) != len(agent_ids)
        ):
            raise ValueError("resident inventory registry does not match population")
        for agent in self.agents:
            account = self.economy.account_for_agent(agent.id)
            inventory = self.materials.inventory_for_agent(agent.id)
            if (
                account.id != f"account:agent:{agent.id}"
                or inventory.id != f"inventory:agent:{agent.id}"
                or inventory.account_id != account.id
            ):
                raise ValueError("resident inventory and account linkage disagree")

        agents_by_id = {agent.id: agent for agent in self.agents}
        cached_agents = (
            self.crime.agents,
            self.justice.agents,
            self.outcome_memory.agents,
        )
        if any(
            set(registry) != registered_ids
            or any(registry[agent_id] is not agents_by_id[agent_id]
                   for agent_id in registered_ids)
            for registry in cached_agents
        ):
            raise ValueError("id-indexed resident registry does not match population")
        for registry in (self.plan_system.agents, self.commitment_system.agents):
            if (
                {agent.id for agent in registry} != registered_ids
                or len(registry) != len(agent_ids)
                or any(agents_by_id[agent.id] is not agent for agent in registry)
            ):
                raise ValueError("resident list registry does not match population")
        transactions_by_id = {
            transaction.id: transaction for transaction in self.economy.ledger
        }
        for record in self.town_growth.migration_records:
            if record.status != "activated":
                if record.agent_id in agents_by_id:
                    raise ValueError("inactive migration cannot expose a resident")
                continue
            resident = agents_by_id.get(record.agent_id)
            if resident is None:
                raise ValueError("activated migration resident is missing")
            template = self.town_growth.template(record.template_id)
            employment = self.economy.employment_for_agent(record.agent_id)
            institution_employment_valid = employment is None or any(
                formation.status == "activated"
                and formation.employee_agent_id == record.agent_id
                and formation.employment_id == employment.id
                and employment.institution_id == formation.institution_id
                and employment.formation_id == formation.id
                for formation in getattr(
                    getattr(self, "institution_growth", None),
                    "formation_records", (),
                )
            )
            if (
                resident.name != template.name
                or resident.occupation != "unemployed"
                or not institution_employment_valid
                or record.agent_id in self.justice.investigator_agent_ids
                or any(
                    record.agent_id in rule.eligible_actor_ids
                    for rule in self.crime.theft_activity_rules.values()
                )
            ):
                raise ValueError("activated migration resident identity disagrees")
            transaction = transactions_by_id.get(record.settlement_transaction_id)
            account = self.economy.account_for_agent(record.agent_id)
            if transaction is None or (
                transaction.event_key != f"migration-settlement:{record.id}"
                or transaction.transaction_type != "migration_settlement"
                or transaction.source_account_id
                != self.town_growth.policy.settlement_source_account_id
                or transaction.destination_account_id != account.id
                or transaction.amount != self.town_growth.policy.settlement_grant
                or dict(transaction.metadata).get("migration_id") != record.id
                or dict(transaction.metadata).get("agent_id") != record.agent_id
            ):
                raise ValueError("activated migration settlement proof is invalid")

    def _restore_population_authorities(
        self,
        *,
        agents: list[Agent],
        economy_state: dict,
        materials_state: dict,
        crime_state: dict,
        justice_state: dict,
        commitments_state: dict,
        plans_state: dict,
        growth_state: dict,
    ) -> None:
        """Restore the small authority set used by one activation transaction."""
        self.agents = agents
        self.economy = EconomySystem.from_dict(economy_state)
        self.materials = MaterialSystem.from_dict(
            materials_state, economy=self.economy
        )
        self.crime = CrimeSystem.from_dict(
            crime_state, materials=self.materials, agents=self.agents,
            reputation_system=self.reputation_system,
        )
        self.justice = JusticeSystem.from_dict(
            justice_state, crime=self.crime, materials=self.materials,
            agents=self.agents, reputation_system=self.reputation_system,
        )
        self.outcome_memory = OutcomeMemorySystem(self.agents)
        self.commitment_system = CommitmentSystem.from_dict(
            commitments_state,
            relationships=self.relationships,
            reputation_system=self.reputation_system,
            agents=self.agents,
            materials=self.materials,
            location_ids=[location.id for location in self.locations],
            outcome_memory=self.outcome_memory,
        )
        self.plan_system = PlanSystem.from_dict(
            plans_state,
            commitment_system=self.commitment_system,
            agents=self.agents,
            outcome_memory=self.outcome_memory,
            materials=self.materials,
        )
        self.commitment_system.plan_system = self.plan_system
        self.town_growth = TownGrowthSystem.from_config(
            self.town_growth_path, self.agents, growth_state
        )
        self.outcome_memory.bind_authorities(
            commitments=self.commitment_system,
            plans=self.plan_system,
            crime=self.crime,
            justice=self.justice,
            materials=self.materials,
            town_growth=self.town_growth,
            location_growth=self.location_growth,
            institution_growth=self.institution_growth,
            commerce_growth=self.commerce_growth,
        )
        self.crime.outcome_memory = self.outcome_memory
        self.justice.outcome_memory = self.outcome_memory
        self.sync_activity_system_refs()

    def activate_pending_migration(self, day: int) -> MigrationRecord | None:
        """Atomically register and fund the one pending resident proposal."""
        record = self.town_growth.pending_migration()
        if record is None:
            return None
        try:
            resident = self.preflight_resident_registration(record)
        except (KeyError, TypeError, ValueError) as error:
            self.town_growth.reject(record.id, str(error))
            return None

        snapshot = deepcopy({
            "agents": self.agents,
            "economy_state": self.economy.to_dict(),
            "materials_state": self.materials.to_dict(),
            "crime_state": self.crime.to_dict(),
            "justice_state": self.justice.to_dict(),
            "commitments_state": self.commitment_system.to_dict(),
            "plans_state": self.plan_system.to_dict(),
            "growth_state": self.town_growth.to_dict(),
        })
        try:
            account = self.economy.register_agent_account(resident.id)
            self.materials.register_agent_inventory(resident.id, account.id)
            self.agents.append(resident)
            self.commitment_system.register_agent(resident)
            self.plan_system.register_agent(resident)
            self.crime.register_agent(resident)
            self.justice.register_agent(resident)
            self.outcome_memory.register_agent(resident)
            transfer = self.economy.transfer(
                self.town_growth.policy.settlement_source_account_id,
                account.id,
                self.town_growth.policy.settlement_grant,
                day=day,
                hour=None,
                transaction_type="migration_settlement",
                reason=f"Settlement grant for {record.id}",
                event_key=f"migration-settlement:{record.id}",
                metadata={"migration_id": record.id, "agent_id": resident.id},
            )
            activated = self.town_growth.activate(
                record.id,
                day=day,
                settlement_transaction_id=transfer.id,
            )
            recipients = [KnowledgeRecipient(
                owner_id=item.id,
                knowledge_basis=(
                    "participant" if item.id == resident.id else "public_event"
                ),
                description=(
                    f"I arrived in town at {record.arrival_location_id}."
                    if item.id == resident.id
                    else f"{resident.name} arrived in town at "
                    f"{record.arrival_location_id}."
                ),
                counterpart_ids=(resident.id,) if item.id != resident.id else (),
                sentiment=1,
                importance=5 if item.id == resident.id else 4,
                location=record.arrival_location_id,
            ) for item in self.agents]
            self.outcome_memory.project(
                source_system="town_growth",
                source_id=record.id,
                event_type="resident_arrival",
                day=day,
                hour=None,
                recipients=recipients,
            )
            self.sync_agent_relationships_from_manager()
            self.validate_population_authorities()
            return activated
        except Exception as error:
            self._restore_population_authorities(**snapshot)
            restored = self.town_growth.pending_migration()
            if restored is not None:
                self.town_growth.reject(
                    restored.id, f"activation_failed:{error}"
                )
            return None

    def review_town_growth(self, day: int):
        """Run the bounded review and orchestrate at most one activation."""
        review = self.town_growth.review(
            day=day,
            agents=self.agents,
            locations=self.locations,
            activity_records=self.activity_records,
            economy=self.economy,
        )
        if review.status == "proposed":
            self.activate_pending_migration(day)
            return next(
                (
                    current for current in self.town_growth.review_history
                    if current.event_key == review.event_key
                ),
                review,
            )
        return review

    def validate_location_authorities(self) -> None:
        """Fail closed when the live registry and activation evidence disagree."""
        checks = self.location_growth.validate(self.locations, self.agents)
        if not all(checks.values()):
            failed = sorted(name for name, passed in checks.items() if not passed)
            raise ValueError(f"location authority invariants failed: {failed}")
        memory_checks = self.outcome_memory.validate()
        if not all(memory_checks.values()):
            raise ValueError("location outcome-memory provenance is invalid")
        dynamic_ids = {
            record.location_id for record in self.location_growth.activation_records
            if record.status == "activated"
        }
        for location in self.locations:
            if location.id not in dynamic_ids:
                continue
            template = next(
                item for item in self.location_growth.templates.values()
                if item.location_id == location.id
            )
            if (
                location.name != template.name
                or location.description != template.description
                or tuple(location.affinities or ()) != template.affinities
            ):
                raise ValueError("active location contradicts its finite template")

    def validate_event_authorities(self) -> None:
        """Fail closed when dynamic event authority lacks exact provenance."""
        checks = self.event_ecology.validate(
            locations=self.locations,
            location_growth=self.location_growth,
            activity_records=self.activity_records,
        )
        if not all(checks.values()):
            failed = sorted(name for name, passed in checks.items() if not passed)
            raise ValueError(f"event ecology invariants failed: {failed}")
        if self.current_daily_event is not None:
            current_day = int(
                self.current_daily_event.day
                if self.current_daily_event.day is not None
                else self.start_day
            )
            self.event_ecology.validate_occurrence(
                self.current_daily_event,
                current_day=current_day,
                locations=self.locations,
                location_growth=self.location_growth,
                activity_records=self.activity_records,
                require_current_day=self.current_daily_event.source_kind != "legacy",
            )

    def preflight_location_activation(
        self, record: LocationActivationRecord
    ) -> Location:
        if record.status != "proposed":
            raise ValueError("location activation is not pending")
        self.validate_location_authorities()
        template = self.location_growth.template(record.template_id)
        if record.location_id != template.location_id:
            raise ValueError("location proposal contradicts its template")
        if record.template_id in self.location_growth.consumed_template_ids:
            raise ValueError("location template was already consumed")
        if len(self.locations) >= self.location_growth.policy.location_capacity:
            raise ValueError("location capacity reached")
        if any(item.id == template.location_id for item in self.locations):
            raise ValueError("location id is already active")
        if any(item.name == template.name for item in self.locations):
            raise ValueError("location name is already active")
        review = next(
            (item for item in self.location_growth.review_history
             if item.activation_id == record.id), None
        )
        if review is None or review.status != "proposed" or review.event_key != record.event_key:
            raise ValueError("location proposal lacks authoritative review")
        if len(self.agents) < self.location_growth.policy.minimum_resident_population:
            raise ValueError("location proposal no longer has sufficient population")
        if not self.location_growth.activity_gate_passes(
            record.review_day, self.agents, self.activity_records
        ):
            raise ValueError("location proposal lacks authoritative sustained activity")
        return Location(
            template.location_id, template.name, template.description,
            list(template.affinities),
        )

    def activate_pending_location(self, day: int) -> LocationActivationRecord | None:
        """Atomically expose one preflighted configured public location."""
        record = self.location_growth.pending_activation()
        if record is None:
            return None
        try:
            location = self.preflight_location_activation(record)
        except (KeyError, TypeError, ValueError) as error:
            self.location_growth.reject(record.id, str(error))
            return None
        locations_before = list(self.locations)
        growth_before = self.location_growth.to_dict()
        base_ids_before = set(self.location_growth.base_location_ids)
        memories_before = [
            (deepcopy(agent.memory), deepcopy(agent.memory_archive))
            for agent in self.agents
        ]
        try:
            self.locations.append(location)
            activated = self.location_growth.activate(record.id, day=day)
            self.activity_planner.set_location_affinities([
                item for item in self.locations
                if item.id not in self.location_growth.base_location_ids
            ])
            self.outcome_memory.bind_authorities(
                commitments=self.commitment_system, plans=self.plan_system,
                crime=self.crime, justice=self.justice, materials=self.materials,
                town_growth=self.town_growth, location_growth=self.location_growth,
                institution_growth=self.institution_growth,
                commerce_growth=self.commerce_growth,
            )
            self.outcome_memory.project(
                source_system="location_growth", source_id=activated.id,
                event_type="location_opened", day=day, hour=None,
                recipients=[KnowledgeRecipient(
                    owner_id=agent.id, knowledge_basis="public_event",
                    description=f"The {location.name} opened as a public town place.",
                    sentiment=1, importance=4, location=location.id,
                ) for agent in self.agents],
            )
            self.validate_location_authorities()
            return activated
        except Exception as error:
            self.locations = locations_before
            for agent, (memory, archive) in zip(self.agents, memories_before):
                agent.memory = memory
                agent.memory_archive = archive
            self.location_growth = LocationGrowthSystem.from_config(
                self.town_growth_path,
                [item for item in self.locations if item.id in base_ids_before],
                growth_before,
            )
            self.activity_planner.set_location_affinities([
                item for item in self.locations
                if item.id not in self.location_growth.base_location_ids
            ])
            self.outcome_memory.bind_authorities(
                commitments=self.commitment_system, plans=self.plan_system,
                crime=self.crime, justice=self.justice, materials=self.materials,
                town_growth=self.town_growth, location_growth=self.location_growth,
                institution_growth=self.institution_growth,
                commerce_growth=self.commerce_growth,
            )
            restored = self.location_growth.pending_activation()
            if restored is not None:
                self.location_growth.reject(restored.id, f"activation_failed:{error}")
            return None

    def review_location_growth(self, day: int):
        review = self.location_growth.review(
            day=day, agents=self.agents, locations=self.locations,
            activity_records=self.activity_records,
        )
        if review.status == "proposed":
            self.activate_pending_location(day)
            return next(
                (item for item in self.location_growth.review_history
                 if item.event_key == review.event_key), review
            )
        return review

    def validate_institution_authorities(self) -> None:
        """Cross-check every activated institution against live authorities."""
        for template in self.institution_growth.templates.values():
            if template.location_template_id not in self.location_growth.templates:
                raise ValueError("institution template has unknown location binding")
            for event_template_id in template.relevant_dynamic_event_template_ids:
                event_template = self.event_ecology.templates.get(event_template_id)
                if (event_template is None
                        or event_template.location_template_id
                        != template.location_template_id):
                    raise ValueError("institution template has invalid event authority")
        checks = self.institution_growth.validate(
            agents=self.agents, locations=self.locations,
            location_growth=self.location_growth,
            event_ecology=self.event_ecology, economy=self.economy,
        )
        if not all(checks.values()):
            failed = sorted(name for name, passed in checks.items() if not passed)
            raise ValueError(f"institution authority invariants failed: {failed}")
        if not self.economy.conservation_holds():
            raise ValueError("institution economy does not conserve currency")
        if not self.economy.ledger_reconstructs_balances():
            raise ValueError("institution economy ledger does not reconstruct")
        memory_checks = self.outcome_memory.validate()
        if not all(memory_checks.values()):
            raise ValueError("institution outcome-memory provenance is invalid")

    def preflight_institution_formation(self, record):
        """Recompute a pending proposal's authority before any mutation."""
        if record.status != "proposed":
            raise ValueError("institution formation is not pending")
        template = self.institution_growth.template(record.template_id)
        review = next((item for item in self.institution_growth.review_history
                       if item.event_key == record.event_key), None)
        if (review is None or review.status != "proposed"
                or review.formation_id != record.id
                or review.candidate_agent_id != record.employee_agent_id
                or record.review_day != review.day):
            raise ValueError("institution proposal lacks its exact review")
        if template.id in self.institution_growth.consumed_template_ids:
            raise ValueError("institution template was already consumed")
        if any(item.status == "activated" and (
            item.institution_id == record.institution_id
            or item.institution_key == record.institution_key
            or item.name == record.name
        ) for item in self.institution_growth.formation_records):
            raise ValueError("institution identity is already active")
        binding = self.location_growth.templates.get(template.location_template_id)
        activation = next((item for item in self.location_growth.activation_records
                           if item.id == record.location_activation_id
                           and item.status == "activated"), None)
        if (binding is None or activation is None
                or binding.location_id != record.location_id
                or activation.template_id != template.location_template_id
                or activation.location_id != record.location_id
                or record.location_id not in {item.id for item in self.locations}):
            raise ValueError("institution location authority is invalid")
        candidate = next((item for item in self.agents
                          if item.id == record.employee_agent_id), None)
        if candidate is None or self.economy.employment_for_agent(candidate.id):
            raise ValueError("institution employee is absent or already employed")
        self.economy.account_for_agent(candidate.id)
        if not self.economy.can_register_employer_account(
            record.institution_id, record.employer_account_id
        ):
            raise ValueError("institution employer account conflicts")
        source = self.economy.get_account(
            template.startup_funding_source_account_id
        )
        if source.balance < template.startup_grant:
            raise ValueError("institution startup funds are insufficient")
        if f"institution-startup:{record.id}" in self.economy.applied_event_keys:
            raise ValueError("institution startup transfer was already applied")
        first_day = record.review_day - self.institution_growth.policy.recent_activity_window_days
        recent = [item for item in self.activity_records
                  if item.get("type") == "activity"
                  and item.get("location") == record.location_id
                  and first_day <= item.get("day", -1) <= record.review_day]
        if (len({item.get("agent_id") for item in recent
                 if item.get("agent_id") in {agent.id for agent in self.agents}})
                < self.institution_growth.policy.minimum_distinct_residents
                or len({item.get("day") for item in recent})
                < self.institution_growth.policy.minimum_activity_days):
            raise ValueError("institution sustained activity is no longer valid")
        allowed_events = set(template.relevant_dynamic_event_template_ids)
        occurrence_ids = {
            item.occurrence_id for item in self.event_ecology.occurrence_history
            if item.location_id == record.location_id
            and item.template_id in allowed_events
            and item.day < record.review_day
        }
        if (len(occurrence_ids)
                < self.institution_growth.policy.minimum_dynamic_event_occurrences):
            raise ValueError("institution dynamic event history is insufficient")
        candidate_first_day = (
            record.review_day
            - self.institution_growth.policy.candidate_activity_window_days
        )
        candidate_evidence = [item for item in self.activity_records
                              if item.get("type") == "activity"
                              and item.get("agent_id") == candidate.id
                              and item.get("location") == record.location_id
                              and candidate_first_day
                              <= item.get("day", -1) <= record.review_day]
        if len(candidate_evidence) < self.institution_growth.policy.minimum_candidate_activities:
            raise ValueError("institution employee evidence is stale")
        return template, candidate

    def activate_pending_institution(self, day: int):
        """Atomically register an institution, its one job, and startup grant."""
        record = self.institution_growth.pending_formation()
        if record is None:
            return None
        try:
            template, candidate = self.preflight_institution_formation(record)
        except (KeyError, TypeError, ValueError) as error:
            self.institution_growth.reject(record.id, str(error))
            return None
        economy_before = deepcopy(self.economy.to_dict())
        growth_before = deepcopy(self.institution_growth.to_dict())
        memories_before = [
            (deepcopy(agent.memory), deepcopy(agent.memory_archive))
            for agent in self.agents
        ]
        try:
            account = self.economy.register_employer_account(
                record.institution_id, record.employer_account_id
            )
            role = template.role
            employment = Employment(
                id=record.employment_id, agent_id=candidate.id,
                title=role.title, employer_account_id=account.id,
                wage=role.wage,
                qualifying_activity_ids=(role.work_activity_id,),
                start_day=day + 1,
                activity_locations=((role.work_activity_id, record.location_id),),
                activity_names=((role.work_activity_id, role.work_activity_name),),
                institution_id=record.institution_id, formation_id=record.id,
                role_template_id=role.role_template_id,
            )
            self.economy.register_employment(employment)
            startup = self.economy.transfer(
                template.startup_funding_source_account_id, account.id,
                template.startup_grant, day=day, hour=None,
                transaction_type="institution_startup",
                reason=f"Startup grant for {record.name}",
                event_key=f"institution-startup:{record.id}",
                metadata={
                    "formation_id": record.id,
                    "institution_id": record.institution_id,
                    "template_id": template.id,
                },
            )
            activated = self.institution_growth.activate(
                record.id, day=day, startup_transaction_id=startup.id
            )
            self.outcome_memory.bind_authorities(
                commitments=self.commitment_system, plans=self.plan_system,
                crime=self.crime, justice=self.justice, materials=self.materials,
                town_growth=self.town_growth, location_growth=self.location_growth,
                institution_growth=self.institution_growth,
                commerce_growth=self.commerce_growth,
            )
            self.outcome_memory.project(
                source_system="institution_growth", source_id=activated.id,
                event_type="institution_established", day=day, hour=None,
                recipients=[KnowledgeRecipient(
                    owner_id=agent.id, knowledge_basis="public_event",
                    description=f"{activated.name} was established.",
                    sentiment=1, importance=4, location=activated.location_id,
                ) for agent in self.agents],
            )
            self.outcome_memory.project(
                source_system="institution_growth", source_id=activated.id,
                event_type="employment_started", day=day, hour=None,
                recipients=[KnowledgeRecipient(
                    owner_id=candidate.id, knowledge_basis="participant",
                    description=f"You began working as the {role.title}.",
                    sentiment=1, importance=5, location=activated.location_id,
                )],
            )
            self.validate_institution_authorities()
            return activated
        except Exception as error:
            self.economy = EconomySystem.from_dict(economy_before)
            self.materials.economy = self.economy
            self.institution_growth = InstitutionGrowthSystem.from_config(
                self.town_growth_path, growth_before
            )
            for agent, (memory, archive) in zip(self.agents, memories_before):
                agent.memory = memory
                agent.memory_archive = archive
            self.sync_activity_system_refs()
            self.outcome_memory.bind_authorities(
                commitments=self.commitment_system, plans=self.plan_system,
                crime=self.crime, justice=self.justice, materials=self.materials,
                town_growth=self.town_growth, location_growth=self.location_growth,
                institution_growth=self.institution_growth,
                commerce_growth=self.commerce_growth,
            )
            restored = self.institution_growth.pending_formation()
            if restored is not None:
                self.institution_growth.reject(
                    restored.id, f"activation_failed:{error}"
                )
            return None

    def review_institution_growth(self, day: int):
        review = self.institution_growth.review(
            day=day, agents=self.agents, locations=self.locations,
            location_growth=self.location_growth,
            event_ecology=self.event_ecology,
            activity_records=self.activity_records, economy=self.economy,
        )
        if review.status == "proposed":
            self.activate_pending_institution(day)
            return next((item for item in self.institution_growth.review_history
                         if item.event_key == review.event_key), review)
        return review

    def _commerce_material_contract(self, record, template):
        seller = Seller(
            id=record.seller_id, inventory_id=record.inventory_id,
            account_id=record.institution_account_id,
            location_id=record.location_id,
            operator_employment_id=record.operator_employment_id,
            institution_id=record.institution_id,
            commerce_activation_id=record.id,
        )
        purchase_rule = PurchaseActivityRule(
            activity_id=record.purchase_activity_id,
            seller_id=record.seller_id, good_id=template.output_good_id,
            quantity=1, commerce_activation_id=record.id,
        )
        recipe = ProductionRecipe(
            id=record.recipe_id,
            inputs=((template.input_good_id, template.input_quantity),),
            outputs=((template.output_good_id, template.output_quantity),),
            output_inventory_id=record.inventory_id,
            activity_id=template.production_activity_id,
            required_location_id=record.location_id,
            eligible_actor_ids=(record.operator_agent_id,),
            eligible_employment_ids=(record.operator_employment_id,),
            target_stock_good_id=template.output_good_id,
            target_stock_quantity=template.target_stock_quantity,
            commerce_activation_id=record.id,
            procurement_seller_id=record.upstream_seller_id,
            procurement_quantity=template.input_quantity,
        )
        return seller, purchase_rule, recipe

    def preflight_commerce_activation(self, record):
        """Recompute readiness and validate every prospective material mutation."""
        if record.status != "proposed":
            raise ValueError("commerce activation is not pending")
        template = self.commerce_growth.template(record.template_id)
        review = next((item for item in self.commerce_growth.review_history
                       if item.event_key == record.event_key), None)
        if (review is None or review.status != "proposed"
                or review.activation_id != record.id
                or review.template_id != record.template_id
                or review.day != record.review_day):
            raise ValueError("commerce proposal lacks its exact review")
        reason, formation = self.commerce_growth.readiness_reason(
            template, day=record.review_day, agents=self.agents,
            locations=self.locations, institution_growth=self.institution_growth,
            location_growth=self.location_growth, economy=self.economy,
            materials=self.materials, activity_records=self.activity_records,
        )
        if reason != "eligible" or formation is None:
            raise ValueError(f"commerce readiness no longer holds:{reason}")
        expected = (
            formation.id, formation.institution_id, formation.location_id,
            formation.location_activation_id, formation.employee_agent_id,
            formation.employment_id, formation.employer_account_id,
            template.purchase_activity_id, template.upstream_seller_id,
        )
        actual = (
            record.institution_formation_id, record.institution_id,
            record.location_id, record.location_activation_id,
            record.operator_agent_id, record.operator_employment_id,
            record.institution_account_id, record.purchase_activity_id,
            record.upstream_seller_id,
        )
        if actual != expected:
            raise ValueError("commerce proposal contradicts live institution authority")
        preview = MaterialSystem.from_dict(
            deepcopy(self.materials.to_dict()), economy=self.economy,
        )
        preview.register_institution_inventory(
            inventory_id=record.inventory_id, institution_id=record.institution_id,
            account_id=record.institution_account_id,
            commerce_activation_id=record.id,
        )
        seller, purchase_rule, recipe = self._commerce_material_contract(record, template)
        preview.register_seller(seller, location_ids={item.id for item in self.locations})
        preview.register_purchase_activity_rule(purchase_rule)
        preview.register_production_recipe(recipe)
        return template, seller, purchase_rule, recipe

    def activate_pending_commerce(self, day: int):
        """Atomically register an empty inventory, seller, route, and recipe."""
        record = self.commerce_growth.pending_activation()
        if record is None:
            return None
        try:
            template, seller, purchase_rule, recipe = (
                self.preflight_commerce_activation(record)
            )
        except (KeyError, TypeError, ValueError) as error:
            self.commerce_growth.reject(record.id, str(error))
            return None
        materials_before = deepcopy(self.materials.to_dict())
        growth_before = deepcopy(self.commerce_growth.to_dict())
        memories_before = [
            (deepcopy(agent.memory), deepcopy(agent.memory_archive))
            for agent in self.agents
        ]
        try:
            self.materials.register_institution_inventory(
                inventory_id=record.inventory_id,
                institution_id=record.institution_id,
                account_id=record.institution_account_id,
                commerce_activation_id=record.id,
            )
            self.materials.register_seller(
                seller, location_ids={item.id for item in self.locations},
            )
            self.materials.register_purchase_activity_rule(purchase_rule)
            self.materials.register_production_recipe(recipe)
            activated = self.commerce_growth.activate(record.id, day=day)
            formation_name = next(
                item.name for item in self.institution_growth.formation_records
                if item.id == activated.institution_formation_id
            )
            self.activity_planner.set_commerce_authority(self.materials)
            self.outcome_memory.bind_authorities(
                commitments=self.commitment_system, plans=self.plan_system,
                crime=self.crime, justice=self.justice, materials=self.materials,
                town_growth=self.town_growth, location_growth=self.location_growth,
                institution_growth=self.institution_growth,
                commerce_growth=self.commerce_growth,
            )
            self.outcome_memory.project(
                source_system="commerce_growth", source_id=activated.id,
                event_type="institution_commerce_opened", day=day, hour=None,
                recipients=[KnowledgeRecipient(
                    owner_id=agent.id, knowledge_basis="public_event",
                    description=(
                        f"{formation_name} began operating a garden food stand."
                    ),
                    sentiment=1, importance=4, location=activated.location_id,
                ) for agent in self.agents],
            )
            self.outcome_memory.project(
                source_system="commerce_growth", source_id=activated.id,
                event_type="commerce_operator_authorized", day=day, hour=None,
                recipients=[KnowledgeRecipient(
                    owner_id=activated.operator_agent_id,
                    knowledge_basis="participant",
                    description="You began producing and selling garden meals there.",
                    sentiment=1, importance=5, location=activated.location_id,
                )],
            )
            self.validate_commerce_authorities()
            return activated
        except Exception as error:
            self.materials = MaterialSystem.from_dict(
                materials_before, economy=self.economy,
            )
            self.crime.materials = self.materials
            self.justice.materials = self.materials
            self.commitment_system.materials = self.materials
            self.plan_system.materials = self.materials
            self.commerce_growth = CommerceGrowthSystem.from_config(
                self.town_growth_path, growth_before,
            )
            for agent, (memory, archive) in zip(self.agents, memories_before):
                agent.memory = memory
                agent.memory_archive = archive
            self.sync_activity_system_refs()
            self.outcome_memory.bind_authorities(
                commitments=self.commitment_system, plans=self.plan_system,
                crime=self.crime, justice=self.justice, materials=self.materials,
                town_growth=self.town_growth, location_growth=self.location_growth,
                institution_growth=self.institution_growth,
                commerce_growth=self.commerce_growth,
            )
            restored = self.commerce_growth.pending_activation()
            if restored is not None:
                self.commerce_growth.reject(
                    restored.id, f"activation_failed:{error}",
                )
            return None

    def review_commerce_growth(self, day: int):
        review = self.commerce_growth.review(
            day=day, agents=self.agents, locations=self.locations,
            institution_growth=self.institution_growth,
            location_growth=self.location_growth, economy=self.economy,
            materials=self.materials, activity_records=self.activity_records,
        )
        if review.status == "proposed":
            self.activate_pending_commerce(day)
            return next((item for item in self.commerce_growth.review_history
                         if item.event_key == review.event_key), review)
        return review

    def validate_commerce_authorities(self) -> None:
        """Reject orphan or contradictory dynamic material authority."""
        self.commerce_growth._validate_state()
        configured_goods = json.loads(
            self.materials_path.read_text(encoding="utf-8")
        ).get("goods", [])
        live_goods = [{
            "id": item.id, "name": item.name, "category": item.category,
            "unit_price": item.unit_price, "consumable": item.consumable,
            **({"need_effect": item.need_effect}
               if item.need_effect is not None else {}),
            **({"need_effect_amount": item.need_effect_amount}
               if item.need_effect_amount else {}),
        } for item in self.materials.goods.values()]
        normalized_configured = [{
            **item,
            **({"consumable": False} if "consumable" not in item else {}),
        } for item in configured_goods]
        if live_goods != normalized_configured:
            raise ValueError("runtime goods contradict checked-in material definitions")
        for template in self.commerce_growth.templates.values():
            institution = self.institution_growth.templates.get(
                template.institution_template_id
            )
            location = self.location_growth.templates.get(template.location_template_id)
            upstream = self.materials.sellers.get(template.upstream_seller_id)
            if (institution is None or location is None
                    or institution.location_template_id != template.location_template_id
                    or upstream is None or upstream.commerce_activation_id is not None
                    or template.input_good_id not in self.materials.goods
                    or template.output_good_id not in self.materials.goods
                    or template.production_activity_id
                    != institution.role.work_activity_id):
                raise ValueError("commerce template references invalid finite authority")
        active = [item for item in self.commerce_growth.activation_records
                  if item.status == "activated"]
        active_ids = {item.id for item in active}
        dynamic_inventories = {item.commerce_activation_id: item
                               for item in self.materials.inventories.values()
                               if item.commerce_activation_id is not None}
        dynamic_sellers = {item.commerce_activation_id: item
                           for item in self.materials.sellers.values()
                           if item.commerce_activation_id is not None}
        dynamic_rules = {item.commerce_activation_id: item
                         for item in self.materials.purchase_activity_rules.values()
                         if item.commerce_activation_id is not None}
        dynamic_recipes = {item.commerce_activation_id: item
                           for item in self.materials.production_recipes.values()
                           if item.commerce_activation_id is not None}
        registries = (dynamic_inventories, dynamic_sellers, dynamic_rules, dynamic_recipes)
        dynamic_counts = (
            sum(item.commerce_activation_id is not None
                for item in self.materials.inventories.values()),
            sum(item.commerce_activation_id is not None
                for item in self.materials.sellers.values()),
            sum(item.commerce_activation_id is not None
                for item in self.materials.purchase_activity_rules.values()),
            sum(item.commerce_activation_id is not None
                for item in self.materials.production_recipes.values()),
        )
        if any(set(registry) != active_ids or len(registry) != len(active)
               for registry in registries):
            raise ValueError("orphan or missing dynamic commerce material authority")
        if any(count != len(active) for count in dynamic_counts):
            raise ValueError("duplicate dynamic commerce material authority")
        for record in active:
            template = self.commerce_growth.template(record.template_id)
            formation = next((item for item in self.institution_growth.formation_records
                              if item.id == record.institution_formation_id
                              and item.status == "activated"), None)
            inventory = dynamic_inventories[record.id]
            seller = dynamic_sellers[record.id]
            rule = dynamic_rules[record.id]
            recipe = dynamic_recipes[record.id]
            expected_seller, expected_rule, expected_recipe = (
                self._commerce_material_contract(record, template)
            )
            if (formation is None
                    or formation.institution_id != record.institution_id
                    or formation.location_id != record.location_id
                    or formation.employment_id != record.operator_employment_id
                    or formation.employee_agent_id != record.operator_agent_id
                    or formation.employer_account_id != record.institution_account_id
                    or inventory.id != record.inventory_id
                    or inventory.owner_type != "institution"
                    or inventory.owner_id != record.institution_id
                    or inventory.account_id != record.institution_account_id
                    or self.materials.initial_quantities.get(record.inventory_id) != {}
                    or seller != expected_seller or rule != expected_rule
                    or recipe != expected_recipe):
                raise ValueError("dynamic commerce authority contradicts activation")
            if any(item.day < record.activation_day for item in self.materials.exchanges
                   if item.seller_id == record.seller_id
                   or item.buyer_inventory_id == record.inventory_id):
                raise ValueError("commerce exchange predates activation")
            if any(item.day < record.activation_day for item in self.materials.production_records
                   if item.recipe_id == record.recipe_id):
                raise ValueError("commerce production predates activation")
        if not (
            self.materials.material_history_reconstructs_inventories()
            and self.materials.exchanges_reconcile_with_ledger()
            and self.materials.provenance_reconciles()
            and self.materials.production_records_are_valid()
            and self.economy.conservation_holds()
            and self.economy.ledger_reconstructs_balances()
        ):
            raise ValueError("commerce economic or material reconstruction failed")
        memory_checks = self.outcome_memory.validate()
        if not all(memory_checks.values()):
            raise ValueError("commerce outcome-memory provenance is invalid")

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
            activity_record = next((
                record for record in reversed(self.activity_records)
                if record.get("type") == "activity"
                and record.get("day") == day
                and record.get("hour") == hour
                and (
                    record.get("agent_id") == agent.id
                    or (
                        record.get("agent_id") is None
                        and record.get("agent") == agent.name
                    )
                )
            ), None)
            self.intent_system.update_intent_after_activity(
                day=day,
                agent=agent,
                activity_record=activity_record,
            )
        delegation_outcomes = self.plan_system.consume_delegation_outcomes(
            day=day, tick=hour,
        )
        self.intent_system.observe_delegation_outcomes(
            day=day, outcomes=delegation_outcomes,
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
        regenerated_for_commitment_state: bool = False,
        commitment_state_valid: bool = True,
        commitment_state_reason: str = "",
        related_commitment_id: str = "",
        grounding_valid: bool = True,
        grounding_reason: str = "",
        grounding_candidate_type: str = "",
        grounding_refs: list[str] | None = None,
        invalid_grounding_refs: list[str] | None = None,
        grounding_metadata_advisory: dict | None = None,
        grounding_metadata_disagreements: list[str] | None = None,
        grounded_repair_used: bool = False,
        grounded_fallback_used: bool = False,
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
            regenerated_for_commitment_state=regenerated_for_commitment_state,
            commitment_state_valid=commitment_state_valid,
            commitment_state_reason=commitment_state_reason,
            related_commitment_id=related_commitment_id,
            grounding_valid=grounding_valid,
            grounding_reason=grounding_reason,
            grounding_candidate_type=grounding_candidate_type,
            grounding_refs=grounding_refs,
            invalid_grounding_refs=invalid_grounding_refs,
            grounding_metadata_advisory=grounding_metadata_advisory,
            grounding_metadata_disagreements=grounding_metadata_disagreements,
            grounded_repair_used=grounded_repair_used,
            grounded_fallback_used=grounded_fallback_used,
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
