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
        conversation_context: dict | None = None,
        enforce_information_boundaries: bool = False,
    ) -> dict:
        parsed_output = parse_llm_conversation_output(
            raw_output,
            allowed_actions=allowed_actions,
        )

        conversation = parsed_output["dialogue"]
        parsed_action = parsed_output["action"]
        dialogue_source = "llm"

        if not conversation:
            conversation = speaker.speak_to(listener, old_relationship_label)
            parsed_action = "chat"
            dialogue_source = "agent_fallback_empty"

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
            if enforce_information_boundaries:
                conversation = self.conversation_policy.get_grounded_fallback_dialogue(
                    speaker=speaker,
                    context=conversation_context or {},
                    location_id=location_id,
                )
            else:
                conversation = speaker.speak_to(listener, old_relationship_label)
            parsed_action = "chat"
            dialogue_source = "agent_fallback_narration"

        if (
            enforce_information_boundaries
            and self._uses_unsourced_hearsay(conversation, conversation_context or {})
        ):
            conversation = self.conversation_policy.get_grounded_fallback_dialogue(
                speaker=speaker,
                context=conversation_context or {},
                location_id=location_id,
            )
            parsed_action = "chat"
            parsed_output["tags"] = []
            dialogue_source = "policy_fallback_unsourced_hearsay"

        if self.conversation_policy.is_repeated_dialogue(conversation) or (
            enforce_information_boundaries
            and self.conversation_policy.is_near_repeated_dialogue(conversation)
        ):
            fallback_action = (
                "chat"
                if dialogue_source == "policy_fallback_unsourced_hearsay"
                or (
                    enforce_information_boundaries
                    and suggested_action == "share_rumor"
                    and not self._context_has_uncertain_source(
                        conversation_context or {}
                    )
                )
                else suggested_action
            )
            conversation = self.conversation_policy.get_non_repeated_fallback_dialogue(
                speaker=speaker,
                listener=listener,
                relationship_label=old_relationship_label,
                location_id=location_id,
                suggested_action=fallback_action,
                avoid_near_repetition=enforce_information_boundaries,
            )
            parsed_action = "chat"
            dialogue_source = "policy_fallback_repetition"

        conversation = clean_dialogue_text(conversation)

        return {
            "parsed_output": parsed_output,
            "conversation": conversation,
            "parsed_action": parsed_action,
            "dialogue_source": dialogue_source,
        }

    @staticmethod
    def _uses_unsourced_hearsay(conversation: str, context: dict) -> bool:
        text = conversation.lower()
        hearsay_markers = (
            "i heard", "have you heard", "did you hear", "someone said", "people are saying",
            "rumor", "rumour", "gossip", "word is", "spotted a suspicious",
        )
        if not any(marker in text for marker in hearsay_markers):
            return False

        return not ConversationOutputProcessor._context_has_uncertain_source(context)

    @staticmethod
    def _context_has_uncertain_source(context: dict) -> bool:
        sources = [
            *context.get("relevant_memories", []),
            *context.get("relationship_history", []),
            *context.get("recent_journals", []),
        ]
        uncertain_markers = (
            "rumor", "rumour", "gossip", "uncertain", "not sure",
            "someone said", "people are saying", "suspicious",
        )
        return any(
            marker in str(source).lower()
            for source in sources
            for marker in uncertain_markers
        )
