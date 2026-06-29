from src.agents.agent import Agent
from src.llm.parser import parse_llm_conversation_output
from src.simulation.conversation_policy import ConversationPolicy
from src.simulation.dialogue_utils import (
    clean_dialogue_text,
    fix_stale_event_reference,
    is_narration,
)
from src.town.daily_event import DailyEvent


class ConversationOutputProcessor:
    def __init__(
        self,
        conversation_policy: ConversationPolicy,
    ):
        self.conversation_policy = conversation_policy

    def process_llm_output(
        self,
        raw_output: str,
        allowed_actions: list[str],
        speaker: Agent,
        listener: Agent,
        old_relationship_label: str,
        location_id: str,
        suggested_action: str,
        current_day: int,
        current_daily_event: DailyEvent | None,
        daily_event_history: list[dict],
    ) -> dict:
        parsed_output = parse_llm_conversation_output(
            raw_output,
            allowed_actions=allowed_actions,
        )

        conversation = parsed_output["dialogue"]
        parsed_action = parsed_output["action"]

        if not conversation:
            conversation = speaker.speak_to(listener, old_relationship_label)
            parsed_action = "chat"

        conversation = fix_stale_event_reference(
            conversation,
            current_day=current_day,
            current_daily_event=current_daily_event,
            daily_event_history=daily_event_history,
        )

        if is_narration(
            conversation,
            speaker.name,
            listener.name,
        ):
            conversation = speaker.speak_to(listener, old_relationship_label)
            parsed_action = "chat"

        if self.conversation_policy.is_repeated_dialogue(conversation):
            conversation = self.conversation_policy.get_non_repeated_fallback_dialogue(
                speaker=speaker,
                listener=listener,
                relationship_label=old_relationship_label,
                location_id=location_id,
                suggested_action=suggested_action,
            )
            parsed_action = "chat"

        conversation = clean_dialogue_text(conversation)

        return {
            "parsed_output": parsed_output,
            "conversation": conversation,
            "parsed_action": parsed_action,
        }
        