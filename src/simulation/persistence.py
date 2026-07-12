from src.agents.agent import Agent
from src.agents.memory import Memory
from src.agents.relationship_event import RelationshipEvent
from src.agents.relationships import RelationshipManager
from src.agents.intent import AgentIntent
from src.town.daily_event import DailyEvent
from src.town.town_arc import TownArc
from src.agents.journal_entry import JournalEntry

class SimulationPersistence:
    def load_agent_intents_from_state(
        self,
        saved_state: dict,
    ) -> dict[str, AgentIntent]:
        return {
            agent_name: AgentIntent(**intent_data)
            for agent_name, intent_data in saved_state.get("agent_intents", {}).items()
        }

    def load_relationship_events_from_state(
        self,
        saved_state: dict,
    ) -> list[RelationshipEvent]:
        return [
            RelationshipEvent(**event_data)
            for event_data in saved_state.get("relationship_events", [])
        ]

    def load_daily_event_from_state(
        self,
        saved_state: dict,
    ) -> DailyEvent | None:
        event_data = saved_state.get("current_daily_event")

        if not event_data:
            return None

        return DailyEvent(**event_data)

    def load_run_continuity_from_state(
        self,
        saved_state: dict,
    ) -> dict:
        return {
            "current_daily_event": self.load_daily_event_from_state(saved_state),
            "daily_event_history": saved_state.get("daily_event_history", []),
            "recent_dialogues": saved_state.get("recent_dialogues", []),
            "recent_actions": saved_state.get("recent_actions", []),
            "activity_records": saved_state.get("activity_records", []),
        }

    def load_intent_history_from_state(
        self,
        saved_state: dict,
    ) -> list[AgentIntent]:
        return [
            AgentIntent(**intent_data)
            for intent_data in saved_state.get("intent_history", [])
        ]
    
    def load_town_arcs_from_state(
        self,
        saved_state: dict,
    ) -> list[TownArc]:
        return [
            TownArc.from_dict(arc_data)
            for arc_data in saved_state.get("town_arcs", [])
        ]

    def load_agents_from_state(
        self,
        saved_state: dict,
    ) -> list[Agent]:
        agents = []

        for agent_data in saved_state["agents"]:
            memories = [
                Memory(**memory_data)
                for memory_data in agent_data.get("memory", [])
            ]

            memory_archive = [
                Memory(**memory_data)
                for memory_data in agent_data.get("memory_archive", [])
            ]
            daily_journals = [
                JournalEntry(**journal_data)
                for journal_data in agent_data.get(
                    "daily_journals",
                    [],
                )
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
                daily_journals=daily_journals,
                occupation=agent_data.get("occupation", "unemployed"),
                recent_topics=agent_data.get("recent_topics", []),
                relationships=agent_data.get("relationships", {}),
                current_activity=agent_data.get("current_activity", "idle"),
                current_activity_reason=agent_data.get("current_activity_reason", ""),
                current_activity_tags=agent_data.get("current_activity_tags", []),
            )

            agents.append(agent)

        return agents

    def load_relationships_from_state(
        self,
        saved_state: dict,
        relationships: RelationshipManager,
    ) -> None:
        relationship_scores = saved_state.get("relationship_scores", {})

        for pair_key, score in relationship_scores.items():
            agent_a, agent_b = pair_key.split("|")
            relationships.scores[(agent_a, agent_b)] = score
            