from src.agents.agent import Agent
from src.agents.intent import AgentIntent
from src.agents.memory import Memory
from src.utils.logger import TownLogger


class ConversationRecorder:
    def __init__(self, logger: TownLogger):
        self.logger = logger

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
        speaker.remember_topics(tags)
        listener.remember_topics(tags)

        memory = self.create_conversation_memory(
            day=day,
            hour=hour,
            location_id=location_id,
            speaker=speaker,
            listener=listener,
            conversation=conversation,
            relationship_change=relationship_change,
            tags=tags,
        )

        speaker.remember(memory)
        listener.remember(memory)

        return memory

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
            "allowed_actions": allowed_actions or [],
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