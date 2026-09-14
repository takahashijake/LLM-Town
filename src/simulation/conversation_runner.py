class ConversationRunner:
    def generate_conversations(
        self,
        engine,
        day: int,
        hour: int,
    ) -> None:
        agents_by_location = engine.group_agents_by_location()
        conversations_created = 0

        for location_id, agents_here in agents_by_location.items():
            if len(agents_here) < 2:
                continue

            conversations_created = conversations_created + 1
            speaker, listener = engine.choose_conversation_pair(agents_here)

            conversation_setup = engine.prepare_conversation_context(
                location_id=location_id,
                speaker=speaker,
                listener=listener,
                current_day=day,
            )

            old_score = conversation_setup["old_score"]
            old_relationship_label = conversation_setup["old_relationship_label"]
            allowed_actions = conversation_setup["allowed_actions"]
            speaker_intent = conversation_setup["speaker_intent"]
            listener_intent = conversation_setup["listener_intent"]
            base_action_weights = conversation_setup["base_action_weights"]
            intent_adjusted_weights = conversation_setup["intent_adjusted_weights"]
            reputation_adjusted_weights = conversation_setup.get(
                "reputation_adjusted_weights", intent_adjusted_weights
            )
            reputation_weight_adjustments = conversation_setup.get(
                "reputation_weight_adjustments", {}
            )
            rumor_claim = conversation_setup.get("rumor_claim")
            suggested_action = conversation_setup["suggested_action"]
            context = conversation_setup["context"]

            generation_error = ""
            try:
                raw_output = engine.llm.generate_conversation(context)
            except Exception as error:  # A single model failure must not end a long run.
                raw_output = ""
                generation_error = f"{type(error).__name__}: {error}"

            processed_output = engine.process_conversation_output(
                raw_output=raw_output,
                allowed_actions=allowed_actions,
                speaker=speaker,
                listener=listener,
                old_relationship_label=old_relationship_label,
                location_id=location_id,
                suggested_action=suggested_action,
                current_day=day,
                conversation_context=context,
                enforce_information_boundaries=not getattr(
                    engine.llm, "is_deterministic_fake", False
                ),
            )

            parsed_output = processed_output["parsed_output"]
            conversation = processed_output["conversation"]
            parsed_action = processed_output["parsed_action"]
            dialogue_source = processed_output["dialogue_source"]

            conversation_tags = engine.get_initial_conversation_tags(
                conversation=conversation,
                parsed_tags=parsed_output.get("tags", []),
            )

            inferred_action = engine.actions.infer_action(
                conversation,
                conversation_tags,
            )

            action, final_action_reason = engine.choose_final_action_with_reason(
                conversation=conversation,
                parsed_action=parsed_action,
                conversation_tags=conversation_tags,
                allowed_actions=allowed_actions,
                inferred_action=inferred_action,
            )

            conversation_tags = engine.finalize_conversation_tags(
                conversation=conversation,
                conversation_tags=conversation_tags,
                relationship_label=old_relationship_label,
                action=action,
            )

            effects_result = engine.apply_conversation_effects(
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
                rumor_claim=rumor_claim,
            )

            relationship_change = effects_result["relationship_change"]
            new_score = effects_result["new_score"]
            relationship_label = effects_result["relationship_label"]

            intent_update = engine.update_intents_after_conversation(
                day=day,
                location_id=location_id,
                speaker=speaker,
                listener=listener,
                action=action,
                relationship_change=relationship_change,
                new_score=new_score,
                conversation_tags=conversation_tags,
            )
            
            if intent_update:
                print(
                    "Intent update: "
                    f"{intent_update['agent']} {intent_update['intent_type']} "
                    f"{intent_update['status']} "
                    f"({intent_update['progress']}/{intent_update['progress_goal']})"
                )
    
            engine.log_conversation_event(
                day,
                hour,
                location_id,
                speaker,
                listener,
                conversation,
                relationship_change,
                new_score,
                relationship_label,
                action,
                parsed_output.get("action_source", ""),
                parsed_output.get("reason", ""),
                conversation_tags,
                speaker_intent=speaker_intent,
                listener_intent=listener_intent,
                suggested_action=suggested_action,
                parsed_action=parsed_action,
                inferred_action=inferred_action,
                base_action_weights=base_action_weights,
                intent_adjusted_weights=intent_adjusted_weights,
                reputation_adjusted_weights=reputation_adjusted_weights,
                reputation_weight_adjustments=reputation_weight_adjustments,
                allowed_actions=allowed_actions,
                final_action_reason=final_action_reason,
                raw_response=raw_output,
                generation_error=generation_error,
                context_evidence=context.get("context_evidence", {}),
                context_snapshot={
                    "occupation": context.get("occupation"),
                    "activity": context.get("speaker_activity"),
                    "activity_display": context.get("speaker_activity_display"),
                    "activity_reason": context.get("speaker_activity_reason"),
                    "relationship_history": context.get("relationship_history", []),
                    "reputation": context.get("reputation_context", []),
                    "reputation_rumor": context.get("reputation_rumor_text", ""),
                    "memories": context.get("relevant_memories", []),
                    "journals": context.get("recent_journals", []),
                    "goals": context.get("goals", []),
                    "active_goal": context.get("active_goal"),
                    "speaker_intent": context.get("speaker_intent"),
                    "daily_event": context.get("daily_event"),
                    "daily_event_relevant": context.get("daily_event_relevant", False),
                    "town_arcs": context.get("town_arcs", []),
                    "recent_topics": context.get("recent_topics", []),
                    "recent_utterances": context.get("recent_utterances", []),
                    "focus_options": context.get("focus_options", []),
                },
                dialogue_source=dialogue_source,
                reputation_updates=effects_result.get("reputation_updates", []),
                rumor_transmission=effects_result.get("rumor_transmission"),
            )

            engine.print_conversation_event(
                day,
                hour,
                location_id,
                conversation,
                relationship_label,
                new_score,
                relationship_change,
                action,
            )

        if conversations_created == 0:
            print("No conversations this tick")
