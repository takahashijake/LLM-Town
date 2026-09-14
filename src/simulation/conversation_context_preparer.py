from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.agents.relationships import RelationshipManager
from src.behavior.social_policy import SocialBehaviorPolicy
from src.llm.context import build_conversation_context
from src.simulation.conversation_policy import ConversationPolicy
from src.simulation.intent_system import IntentSystem
from src.simulation.relationship_updater import RelationshipUpdater
from src.simulation.town_arc_system import TownArcSystem
from src.town.daily_event import DailyEvent


class ConversationContextPreparer:
    def __init__(
        self,
        relationships: RelationshipManager,
        actions: ActionSystem,
        social_policy: SocialBehaviorPolicy,
        intent_system: IntentSystem,
        conversation_policy: ConversationPolicy,
        relationship_updater: RelationshipUpdater,
        town_arc_system: TownArcSystem,
    ):
        self.relationships = relationships
        self.actions = actions
        self.social_policy = social_policy
        self.intent_system = intent_system
        self.conversation_policy = conversation_policy
        self.relationship_updater = relationship_updater
        self.town_arc_system = town_arc_system

    def prepare_conversation_context(
        self,
        location_id: str,
        speaker: Agent,
        listener: Agent,
        current_day: int,
        current_daily_event: DailyEvent | None,
        agent_intents: dict,
        relationship_events: list,
    ) -> dict:
        old_score = self.relationships.get_score(
            speaker.name,
            listener.name,
        )

        old_relationship_label = self.relationships.describe_relationship(
            speaker.name,
            listener.name,
        )

        allowed_actions = self.actions.get_allowed_actions_for_relationship(
            old_score,
        )

        recent_relationship_events = self.relationship_updater.get_recent_relationship_events(
            relationship_events=relationship_events,
            agent_a=speaker.name,
            agent_b=listener.name,
            limit=5,
        )

        speaker_intent = agent_intents.get(speaker.name)
        listener_intent = agent_intents.get(listener.name)

        base_action_weights = self.social_policy.get_action_weights(
            allowed_actions=allowed_actions,
            relationship_label=old_relationship_label,
            recent_events=recent_relationship_events,
        )

        intent_adjusted_weights = self.intent_system.adjust_action_weights_for_intent(
            weights=base_action_weights,
            intent=speaker_intent,
            listener_name=listener.name,
        )

        arc_adjusted_weights = self.town_arc_system.adjust_action_weights_for_town_arcs(
            weights=intent_adjusted_weights,
            location_id=location_id,
            conversation_tags=[],
        )

        suggested_action = self.conversation_policy.choose_weighted_action(
            arc_adjusted_weights,
        )

        relationship_history = self.relationship_updater.format_relationship_history_for_prompt(
            relationship_events=relationship_events,
            agent_a=speaker.name,
            agent_b=listener.name,
            limit=3,
        )

        context = build_conversation_context(
            speaker=speaker,
            listener=listener,
            location_id=location_id,
            relationship_label=old_relationship_label,
            relationship_score=old_score,
            current_day=current_day,
            daily_event=current_daily_event,
            allowed_actions=allowed_actions,
            suggested_action=suggested_action,
            relationship_history=relationship_history,
            speaker_intent=speaker_intent.to_dict() if speaker_intent else None,
            town_arcs=self.town_arc_system.get_relevant_town_arcs_for_context(
                location_id,
            ),
        )

        return {
            "old_score": old_score,
            "old_relationship_label": old_relationship_label,
            "allowed_actions": allowed_actions,
            "recent_relationship_events": recent_relationship_events,
            "speaker_intent": speaker_intent,
            "listener_intent": listener_intent,
            "base_action_weights": base_action_weights,
            "intent_adjusted_weights": intent_adjusted_weights,
            "arc_adjusted_weights": arc_adjusted_weights,
            "suggested_action": suggested_action,
            "relationship_history": relationship_history,
            "context": context,
        }
