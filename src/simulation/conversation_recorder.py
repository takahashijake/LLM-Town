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

    def remember_session_for_agents(
        self,
        *,
        day: int,
        hour: int,
        location_id: str,
        participants: list[Agent],
        turns: list[dict],
        relationship_change: int,
        tags: list[str],
        session_id: str,
    ) -> list[Memory]:
        """Store one coherent memory per participant, not one per utterance."""
        transcript = " ".join(
            f"{turn['speaker']}: {turn['dialogue']}" for turn in turns
        )
        unique_lines = list(dict.fromkeys(turn["dialogue"] for turn in turns))
        # A repetition-terminated session containing one duplicated line is
        # coherently represented by that line and remains load-compatible.
        description = (
            unique_lines[0]
            if len(unique_lines) == 1
            else f"Conversation {session_id}: {transcript}"
        )
        memories = []
        names = [agent.name for agent in participants]
        for owner in participants:
            owner.remember_topics(tags)
            ordered = [owner.name, *[name for name in names if name != owner.name]]
            memory = Memory(
                day=day,
                hour=hour,
                type="conversation",
                description=description,
                participants=ordered,
                location=location_id,
                importance=2,
                sentiment=relationship_change,
                tags=list(dict.fromkeys(["conversation", *tags, session_id])),
            )
            owner.remember(memory)
            memories.append(memory)
        return memories

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
        effect_applied: bool = True,
        effect_suppressed: bool = False,
        effect_suppression_reason: str = "",
    ) -> None:
        intent_relationship_applies = bool(
            speaker_intent
            and getattr(speaker_intent, "relationship_influenced", False)
            and speaker_intent.target_agent in (None, listener.name)
        )
        conversation_record = {
            "session_id": session_id,
            "turn_index": turn_index,
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
            "inference_reason": inference_reason,
            "base_action_weights": base_action_weights or {},
            "relationship_adjusted_weights": relationship_adjusted_weights or {},
            "relationship_weight_adjustments": relationship_weight_adjustments or {},
            "relationship_influenced": bool(relationship_weight_adjustments) or bool(
                intent_relationship_applies
            ),
            "relationship_decision_reasons": relationship_decision_reasons or (
                [getattr(speaker_intent, "relationship_reason", "")]
                if intent_relationship_applies else []
            ),
            "relationship_snapshot": relationship_snapshot or {},
            "retrieved_social_memories": retrieved_social_memories or [],
            "relationship_updates": relationship_updates or {},
            "intent_adjusted_weights": intent_adjusted_weights or {},
            "reputation_adjusted_weights": reputation_adjusted_weights or {},
            "reputation_weight_adjustments": reputation_weight_adjustments or {},
            "reputation_influenced": bool(reputation_weight_adjustments),
            "tags": tags or [],
            "allowed_actions": allowed_actions or [],
            "final_action_reason": final_action_reason,
            "speaker_intent_type": speaker_intent.intent_type if speaker_intent else "",
            "speaker_intent_target_agent": speaker_intent.target_agent if speaker_intent else "",
            "speaker_intent_target_location": speaker_intent.target_location if speaker_intent else "",
            "speaker_intent_description": speaker_intent.description if speaker_intent else "",
            "speaker_intent_id": speaker_intent.id if speaker_intent else "",
            "speaker_intent_parent_goal_id": (
                speaker_intent.parent_goal_id if speaker_intent else ""
            ),
            "speaker_intent_strategy": speaker_intent.strategy if speaker_intent else "",
            "listener_intent_type": listener_intent.intent_type if listener_intent else "",
            "raw_response": raw_response,
            "generation_error": generation_error,
            "context_evidence": context_evidence or {},
            "context": context_snapshot or {},
            "dialogue_source": dialogue_source,
            "reputation_updates": reputation_updates or [],
            "rumor_transmission": rumor_transmission,
            "response_to_turn": response_to_turn,
            "response_outcome": response_outcome,
            "termination_reason": termination_reason,
            "generation_attempt_count": generation_attempt_count,
            "regenerated_for_repetition": regenerated_for_repetition,
            "regenerated_for_grounding": regenerated_for_grounding,
            "regenerated_for_commitment_state": regenerated_for_commitment_state,
            "commitment_state_valid": commitment_state_valid,
            "commitment_state_reason": commitment_state_reason,
            "related_commitment_id": related_commitment_id,
            "grounding_valid": grounding_valid,
            "grounding_reason": grounding_reason,
            "grounding_candidate_type": grounding_candidate_type,
            "grounding_refs": grounding_refs or [],
            "invalid_grounding_refs": invalid_grounding_refs or [],
            "effect_applied": effect_applied,
            "effect_suppressed": effect_suppressed,
            "effect_suppression_reason": effect_suppression_reason,
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
