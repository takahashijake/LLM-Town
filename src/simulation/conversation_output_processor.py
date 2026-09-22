import re

from src.agents.agent import Agent
from src.llm.parser import parse_llm_conversation_output
from src.simulation.conversation_policy import ConversationPolicy
from src.simulation.dialogue_utils import (
    clean_dialogue_text,
    fix_stale_event_reference,
    is_narration,
)
from src.town.daily_event import DailyEvent
from src.systems.reputation import ReputationSystem
from src.llm.grounding import GroundingValidator


class ConversationOutputProcessor:
    def __init__(
        self,
        conversation_policy: ConversationPolicy,
    ):
        self.conversation_policy = conversation_policy
        self.grounding = GroundingValidator()

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

        if conversation.strip().lower() in {
            "spoken line",
            "short line of dialogue",
            "dialogue",
        }:
            conversation = ""

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
                if suggested_action in allowed_actions and suggested_action != "share_rumor":
                    conversation = (
                        self.conversation_policy.get_non_repeated_fallback_dialogue(
                            speaker=speaker,
                            listener=listener,
                            relationship_label=old_relationship_label,
                            location_id=location_id,
                            suggested_action=suggested_action,
                            avoid_near_repetition=True,
                        )
                    )
                else:
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

        reputation_rumor = (conversation_context or {}).get("reputation_rumor")
        if (
            enforce_information_boundaries
            and parsed_action == "share_rumor"
            and reputation_rumor
            and not self._matches_reputation_claim(conversation, reputation_rumor)
        ):
            conversation = ReputationSystem.format_rumor_dialogue(
                reputation_rumor
            )
            dialogue_source = "policy_fallback_structured_reputation_rumor"

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

        grounding = self.grounding.validate(
            conversation,
            parsed_output.get("grounding_refs", []),
            conversation_context or {},
            follow_through=parsed_output.get("follow_through"),
        )
        # Structured metadata is advisory. Invalid fields are removed before
        # downstream systems see them; ordinary dialogue remains available for
        # the established safe path and may still be regenerated by the runner.
        parsed_output["follow_through"] = grounding.follow_through

        return {
            "parsed_output": parsed_output,
            "conversation": conversation,
            "parsed_action": parsed_action,
            "dialogue_source": dialogue_source,
            "grounding": grounding,
        }

    @staticmethod
    def _uses_unsourced_hearsay(conversation: str, context: dict) -> bool:
        text = conversation.lower()
        hearsay_markers = (
            "i heard", "i overheard", "been hearing", "have you heard", "did you hear", "someone said", "people are saying",
            "rumor", "rumour", "gossip", "word is", "spotted a suspicious",
        )
        if not any(marker in text for marker in hearsay_markers):
            return False
        structured_claim = context.get("reputation_rumor")
        if structured_claim:
            return not ConversationOutputProcessor._matches_reputation_claim(
                conversation,
                structured_claim,
            )
        return not ConversationOutputProcessor._matches_uncertain_text_source(
            conversation,
            context,
        )

    @staticmethod
    def _matches_uncertain_text_source(conversation: str, context: dict) -> bool:
        uncertain_markers = (
            "rumor", "rumour", "gossip", "uncertain", "not sure",
            "someone said", "people are saying", "suspicious", "i heard",
            "might be hiding", "might be unreliable",
        )
        sources = [
            *context.get("relevant_memories", []),
            *context.get("relationship_history", []),
            *context.get("recent_journals", []),
        ]
        uncertain_sources = [
            str(source).lower()
            for source in sources
            if any(marker in str(source).lower() for marker in uncertain_markers)
        ]
        if not uncertain_sources:
            return False
        ignored = {
            "about", "heard", "rumor", "rumour", "gossip", "someone",
            "people", "saying", "might", "could", "should", "would",
            "their", "there", "these", "those", "something", "today",
        }
        claim_tokens = {
            token for token in re.findall(r"[a-z][a-z'-]{3,}", conversation.lower())
            if token not in ignored
        }
        return any(
            claim_tokens & set(re.findall(r"[a-z][a-z'-]{3,}", source))
            for source in uncertain_sources
        )

    @staticmethod
    def _context_has_uncertain_source(context: dict) -> bool:
        if context.get("reputation_rumor"):
            return True
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

    @staticmethod
    def _matches_reputation_claim(conversation: str, claim: dict) -> bool:
        text = conversation.lower()
        subject = str(claim.get("subject_agent", "")).lower()
        dimension = claim.get("dimension")
        positive = float(claim.get("value", 0.0)) > 0
        descriptors = {
            "trustworthiness": (
                ("trustworthy", "reliable", "keeps their word"),
                ("untrustworthy", "unreliable", "cannot trust"),
            ),
            "helpfulness": (
                ("helpful", "helped", "helps"),
                ("unhelpful", "wouldn't help", "would not help"),
            ),
            "cooperativeness": (
                ("cooperative", "worked together", "cooperated"),
                ("uncooperative", "wouldn't cooperate", "would not cooperate"),
            ),
            "hostility": (
                ("hostile", "aggressive", "angry"),
                ("non-hostile", "calm", "peaceful"),
            ),
        }
        directions = descriptors.get(dimension)
        if not subject or not directions:
            return False
        expected = directions[0 if positive else 1]
        return subject in text and any(word in text for word in expected)
