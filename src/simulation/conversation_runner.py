"""Orchestrate bounded, alternating conversation sessions."""

from __future__ import annotations

from difflib import SequenceMatcher

from src.llm.grounding import GroundingResult
from src.simulation.conversation_session import ConversationSession, ConversationTurn, ResponseOutcomeResolver
from src.simulation.social_semantics import classify_commitment_relation


class ConversationRunner:
    def __init__(self, max_turns: int = 4):
        self.max_turns = max(1, int(max_turns))
        self.outcomes = ResponseOutcomeResolver()

    def generate_conversations(self, engine, day: int, hour: int) -> None:
        created = 0
        for location_id, agents_here in engine.group_agents_by_location().items():
            if len(agents_here) < 2:
                continue
            created += 1
            initiator, other = engine.choose_conversation_pair(agents_here)
            session = ConversationSession(
                session_id=self._session_id(day, hour, location_id, initiator.name, other.name),
                day=day, hour=hour, location=location_id,
                participants=[initiator.name, other.name], initiating_agent=initiator.name,
            )
            self._generate_session(engine, session, initiator, other)
            self._apply_and_record(engine, session, initiator, other)
        if created == 0:
            print("No conversations this tick")

    def _generate_session(self, engine, session, initiator, other) -> None:
        speaker, listener = initiator, other
        transcript = []
        for turn_index in range(self.max_turns):
            try:
                setup = engine.prepare_conversation_context(
                    location_id=session.location, speaker=speaker, listener=listener,
                    current_day=session.day, session_transcript=transcript,
                )
            except TypeError:  # Compatibility with existing lightweight doubles.
                setup = engine.prepare_conversation_context(
                    location_id=session.location, speaker=speaker, listener=listener,
                    current_day=session.day,
                )
            context = setup["context"]
            context["session_transcript"] = list(transcript)
            context["most_recent_utterance"] = transcript[-1]["dialogue"] if transcript else ""
            raw_output, processed, generation_error = self._generate_and_process(
                engine=engine,
                context=context,
                setup=setup,
                speaker=speaker,
                listener=listener,
                session=session,
            )
            generation_attempt_count = 1
            regenerated_for_repetition = False
            regenerated_for_grounding = False
            regenerated_for_commitment_state = False
            first_grounding_failure = ""
            if (
                not generation_error
                and not getattr(engine.llm, "is_deterministic_fake", False)
                and not processed["grounding"].valid
            ):
                first_grounding_failure = processed["grounding"].reason
                generation_attempt_count += 1
                regenerated_for_grounding = True
                context = {
                    **context,
                    "grounding_correction": first_grounding_failure,
                }
                raw_output, processed, generation_error = self._generate_and_process(
                    engine=engine, context=context, setup=setup, speaker=speaker,
                    listener=listener, session=session,
                )
                if not generation_error and not processed["grounding"].valid:
                    processed["conversation"] = engine.conversation_policy.get_grounded_fallback_dialogue(
                        speaker=speaker, context=context, location_id=session.location,
                    )
                    processed["parsed_action"] = "chat"
                    processed["dialogue_source"] = "policy_fallback_unsupported_grounding"
            commitment_state = self._commitment_state_check(context, processed)
            if (
                not generation_error and not commitment_state["valid"]
                and not getattr(engine.llm, "is_deterministic_fake", False)
            ):
                generation_attempt_count += 1
                regenerated_for_commitment_state = True
                context = {**context,
                           "commitment_state_correction": commitment_state["reason"]}
                raw_output, processed, generation_error = self._generate_and_process(
                    engine=engine, context=context, setup=setup, speaker=speaker,
                    listener=listener, session=session,
                )
                commitment_state = self._commitment_state_check(context, processed)
                if not generation_error and not commitment_state["valid"]:
                    processed["conversation"] = "I understand."
                    processed["parsed_action"] = "chat"
                    processed["dialogue_source"] = "policy_fallback_commitment_state"
                    processed["parsed_output"]["commitment_relation"] = {
                        "commitment_id": commitment_state["commitment_id"],
                        "relation": "unrelated", "confidence": "none",
                    }
            if (
                transcript
                and not generation_error
                and not getattr(engine.llm, "is_deterministic_fake", False)
                and self._matches_prior_turn(processed["conversation"], transcript)
            ):
                generation_attempt_count += 1
                regenerated_for_repetition = True
                context = {
                    **context,
                    "anti_echo_retry": True,
                    "repeated_candidate": processed["conversation"],
                }
                raw_output, processed, generation_error = self._generate_and_process(
                    engine=engine,
                    context=context,
                    setup=setup,
                    speaker=speaker,
                    listener=listener,
                    session=session,
                )
            parsed = processed["parsed_output"]
            grounding = processed.get("grounding", GroundingResult(True))
            dialogue = processed["conversation"]
            tags = engine.get_initial_conversation_tags(
                conversation=dialogue, parsed_tags=parsed.get("tags", []),
            )
            infer = getattr(engine.actions, "infer_action_with_reason", None)
            if infer:
                inferred, inference_reason = infer(dialogue, tags)
            else:
                inferred = engine.actions.infer_action(dialogue, tags)
                inference_reason = "not_available"
            action, final_reason = engine.choose_final_action_with_reason(
                conversation=dialogue, parsed_action=processed["parsed_action"],
                conversation_tags=tags, allowed_actions=setup["allowed_actions"],
                inferred_action=inferred,
            )
            tags = engine.finalize_conversation_tags(
                conversation=dialogue, conversation_tags=tags,
                relationship_label=setup["old_relationship_label"], action=action,
            )
            response_to = None
            outcome = None
            resolution_reason = ""
            if session.turns and session.turns[-1].final_action in self.outcomes.RESPONSIVE_ACTIONS:
                previous = session.turns[-1]
                goods = {good_id: definition.name for good_id, definition in getattr(engine.materials, "goods", {}).items()}
                proposal = engine.commitment_system.recognize_proposal(previous.dialogue, day=session.day, known_goods=goods) if getattr(engine, "commitment_system", None) else None
                outcome, resolution_reason = self.outcomes.resolve_with_reason(
                    previous.final_action, dialogue, proposal=proposal,
                    parsed_action=processed["parsed_action"],
                    social_response=parsed.get("social_response"),
                )
                response_to = previous.turn_index
                previous.response_outcome = outcome
            elif session.turns and getattr(engine, "commitment_system", None):
                previous = session.turns[-1]
                goods = {
                    good_id: definition.name
                    for good_id, definition in getattr(engine.materials, "goods", {}).items()
                }
                proposal = engine.commitment_system.recognize_proposal(
                    previous.dialogue, day=session.day, known_goods=goods,
                )
                if proposal:
                    semantic_action = (
                        "cooperate" if proposal["commitment_type"] == "meet" else "ask_for_help"
                    )
                    outcome, resolution_reason = self.outcomes.resolve_with_reason(
                        semantic_action, dialogue, proposal=proposal,
                        parsed_action=processed["parsed_action"],
                        social_response=parsed.get("social_response"),
                    )
                    response_to = previous.turn_index
                    previous.response_outcome = outcome
            turn = ConversationTurn(
                turn_index=turn_index, speaker=speaker.name, listener=listener.name,
                dialogue=dialogue, suggested_action=setup["suggested_action"],
                parsed_action=processed["parsed_action"], inferred_action=inferred,
                inference_reason=inference_reason, final_action=action,
                final_action_reason=final_reason,
                action_source=parsed.get("action_source", ""),
                dialogue_source=processed["dialogue_source"],
                generation_attempt_count=generation_attempt_count,
                regenerated_for_repetition=regenerated_for_repetition,
                regenerated_for_grounding=regenerated_for_grounding,
                regenerated_for_commitment_state=regenerated_for_commitment_state,
                commitment_state_valid=commitment_state["valid"],
                commitment_state_reason=commitment_state["reason"],
                related_commitment_id=commitment_state["commitment_id"],
                grounding_valid=grounding.valid,
                grounding_reason=(grounding.reason or first_grounding_failure),
                grounding_candidate_type=grounding.candidate_type,
                grounding_refs=grounding.valid_refs,
                invalid_grounding_refs=grounding.invalid_refs,
                generation_error=generation_error, response_to_turn=response_to,
                response_outcome=None,
                social_response=parsed.get("social_response", {}),
                commitment_relation=parsed.get("commitment_relation", {}),
                response_resolution_reason=resolution_reason,
                context_evidence=context.get("context_evidence", {}),
                context_snapshot=self._context_snapshot(context),
                diagnostics=self._diagnostics(setup, parsed, tags, raw_output),
            )
            turn._speaker_intent = setup.get("speaker_intent")
            turn._listener_intent = setup.get("listener_intent")
            session.turns.append(turn)
            transcript.append({"turn_index": turn_index, "speaker": speaker.name,
                               "listener": listener.name, "dialogue": dialogue})
            reason = self._termination_reason(engine, session, turn)
            if reason:
                session.termination_reason = reason
                break
            speaker, listener = listener, speaker
        if not session.termination_reason:
            session.termination_reason = "max_turns"

    def _apply_and_record(self, engine, session, initiator, other) -> None:
        agents = {initiator.name: initiator, other.name: other}
        commitment_system = getattr(engine, "commitment_system", None)
        if commitment_system:
            goods = {
                good_id: definition.name
                for good_id, definition in getattr(engine.materials, "goods", {}).items()
            }
            for response in session.turns:
                if response.response_to_turn is None:
                    continue
                proposal = session.turns[response.response_to_turn]
                repair_parent = self._repair_parent_for_turn(
                    commitment_system, agents[proposal.speaker].id,
                    agents[response.speaker].id, proposal.dialogue, session.day,
                )
                commitment_system.process_response(
                    proposer_id=agents[proposal.speaker].id,
                    counterpart_id=agents[response.speaker].id,
                    proposal_text=proposal.dialogue,
                    response_text=response.dialogue,
                    outcome=proposal.response_outcome or "unresolved",
                    day=session.day,
                    tick=session.hour,
                    session_id=session.session_id,
                    proposal_turn=proposal.turn_index,
                    response_turn=response.turn_index,
                    known_goods=goods,
                    repair_of_commitment_id=repair_parent,
                )
            for turn in session.turns:
                speaker_id = agents[turn.speaker].id
                listener_id = agents[turn.listener].id
                records = commitment_system.relevant_context_records(
                    speaker_id, listener_id, session.day, limit=10,
                )
                annotated_id = turn.commitment_relation.get("commitment_id", "")
                for record in records:
                    if annotated_id and record["commitment_id"] != annotated_id:
                        continue
                    commitment_system.cancel_from_dialogue(
                        record["commitment_id"], speaker_id=speaker_id,
                        counterpart_id=listener_id, dialogue=turn.dialogue,
                        day=session.day, tick=session.hour, session_id=session.session_id,
                        turn_index=turn.turn_index,
                    )
        seen_actions = set()
        total_change = 0
        all_tags = []
        for turn in session.turns:
            d = turn.diagnostics
            outcome = turn.response_outcome or (
                "unresolved" if turn.final_action in self.outcomes.RESPONSIVE_ACTIONS else "completed"
            )
            if turn.final_action in self.outcomes.RESPONSIVE_ACTIONS and turn.response_outcome is None:
                turn.response_outcome = outcome
            suppression_reason = ""
            if turn.final_action in seen_actions:
                suppression_reason = "duplicate_action_in_session"
            else:
                cap = getattr(engine, "should_cap_action", None)
                if cap and cap(turn.final_action):
                    suppression_reason = "action_rate_cap"
            seen_actions.add(turn.final_action)
            effects = engine.apply_conversation_effects(
                day=session.day, hour=session.hour, location_id=session.location,
                speaker=agents[turn.speaker], listener=agents[turn.listener],
                action=turn.final_action, conversation=turn.dialogue,
                conversation_tags=d["tags"],
                old_relationship_label=d["old_relationship_label"],
                old_score=(engine.relationships.get_score(turn.speaker, turn.listener)
                           if hasattr(engine, "relationships") else d["old_score"]),
                rumor_claim=d.get("rumor_claim"), outcome=outcome, remember=False,
                effect_eligible=not suppression_reason,
                effect_suppression_reason=suppression_reason,
            )
            turn.effect_applied = effects.get("effect_applied", not suppression_reason)
            turn.effect_suppressed = effects.get("effect_suppressed", bool(suppression_reason))
            turn.effect_suppression_reason = effects.get(
                "effect_suppression_reason", suppression_reason
            )
            if turn.effect_applied:
                total_change += effects["relationship_change"]
                if not (
                    turn.final_action in self.outcomes.RESPONSIVE_ACTIONS
                    and outcome not in {"accepted", "answered", "acknowledged"}
                ):
                    engine.update_intents_after_conversation(
                        day=session.day, location_id=session.location,
                        speaker=agents[turn.speaker], listener=agents[turn.listener],
                        action=turn.final_action,
                        relationship_change=effects["relationship_change"],
                        new_score=effects["new_score"], conversation_tags=d["tags"],
                    )
            all_tags.extend(d["tags"])
            self._log_turn(engine, session, turn, agents, effects)
            engine.print_conversation_event(
                session.day, session.hour, session.location, turn.dialogue,
                effects["relationship_label"], effects["new_score"],
                effects["relationship_change"], turn.final_action,
            )
        recorder = getattr(engine, "conversation_recorder", None)
        if recorder and hasattr(recorder, "remember_session_for_agents"):
            recorder.remember_session_for_agents(
                day=session.day, hour=session.hour, location_id=session.location,
                participants=[initiator, other], turns=[turn.to_dict() for turn in session.turns],
                relationship_change=total_change, tags=list(dict.fromkeys(all_tags)),
                session_id=session.session_id,
            )
            log_session = getattr(recorder.logger, "log_conversation_session", None)
            if log_session:
                log_session(session.to_dict())

    @staticmethod
    def _log_turn(engine, session, turn, agents, effects) -> None:
        d = turn.diagnostics
        engine.log_conversation_event(
            session.day, session.hour, session.location,
            agents[turn.speaker], agents[turn.listener], turn.dialogue,
            effects["relationship_change"], effects["new_score"],
            effects["relationship_label"], turn.final_action,
            turn.action_source, d["action_reason"], d["tags"],
            speaker_intent=getattr(turn, "_speaker_intent", None),
            listener_intent=getattr(turn, "_listener_intent", None),
            suggested_action=turn.suggested_action, parsed_action=turn.parsed_action,
            inferred_action=turn.inferred_action, inference_reason=turn.inference_reason,
            base_action_weights=d["base_action_weights"],
            relationship_adjusted_weights=d["relationship_adjusted_weights"],
            relationship_weight_adjustments=d["relationship_weight_adjustments"],
            relationship_decision_reasons=d["relationship_decision_reasons"],
            relationship_snapshot=d["relationship_snapshot"],
            retrieved_social_memories=d["social_memories"],
            relationship_updates=effects.get("relationship_updates", {}),
            intent_adjusted_weights=d["intent_adjusted_weights"],
            reputation_adjusted_weights=d["reputation_adjusted_weights"],
            reputation_weight_adjustments=d["reputation_weight_adjustments"],
            allowed_actions=d["allowed_actions"], final_action_reason=turn.final_action_reason,
            raw_response=d["raw_response"], generation_error=turn.generation_error,
            context_evidence=turn.context_evidence, context_snapshot=turn.context_snapshot,
            dialogue_source=turn.dialogue_source,
            reputation_updates=effects.get("reputation_updates", []),
            rumor_transmission=effects.get("rumor_transmission"),
            session_id=session.session_id, turn_index=turn.turn_index,
            response_to_turn=turn.response_to_turn,
            response_outcome=turn.response_outcome,
            termination_reason=session.termination_reason,
            generation_attempt_count=turn.generation_attempt_count,
            regenerated_for_repetition=turn.regenerated_for_repetition,
            regenerated_for_grounding=turn.regenerated_for_grounding,
            regenerated_for_commitment_state=turn.regenerated_for_commitment_state,
            commitment_state_valid=turn.commitment_state_valid,
            commitment_state_reason=turn.commitment_state_reason,
            related_commitment_id=turn.related_commitment_id,
            grounding_valid=turn.grounding_valid,
            grounding_reason=turn.grounding_reason,
            grounding_candidate_type=turn.grounding_candidate_type,
            grounding_refs=turn.grounding_refs,
            invalid_grounding_refs=turn.invalid_grounding_refs,
            effect_applied=turn.effect_applied,
            effect_suppressed=turn.effect_suppressed,
            effect_suppression_reason=turn.effect_suppression_reason,
        )

    @staticmethod
    def _generate_and_process(engine, context, setup, speaker, listener, session):
        generation_error = ""
        try:
            raw_output = engine.llm.generate_conversation(context)
        except Exception as error:
            raw_output = ""
            generation_error = f"{type(error).__name__}: {error}"
        processed = engine.process_conversation_output(
            raw_output=raw_output, allowed_actions=setup["allowed_actions"],
            speaker=speaker, listener=listener,
            old_relationship_label=setup["old_relationship_label"],
            location_id=session.location, suggested_action=setup["suggested_action"],
            current_day=session.day, conversation_context=context,
            enforce_information_boundaries=not getattr(
                engine.llm, "is_deterministic_fake", False
            ),
        )
        return raw_output, processed, generation_error

    @staticmethod
    def _matches_prior_turn(dialogue: str, transcript: list[dict]) -> bool:
        candidate = " ".join(dialogue.lower().split())
        if not candidate:
            return False
        for turn in transcript:
            prior = " ".join(str(turn.get("dialogue", "")).lower().split())
            if candidate == prior:
                return True
            if min(len(candidate), len(prior)) >= 20 and (
                SequenceMatcher(None, candidate, prior).ratio() >= 0.90
            ):
                return True
        return False

    @staticmethod
    def _commitment_state_check(context: dict, processed: dict) -> dict:
        records = context.get("commitment_records", [])
        if not records:
            return {"valid": True, "reason": "no_supplied_commitment_claim",
                    "commitment_id": ""}
        annotation = processed.get("parsed_output", {}).get("commitment_relation", {})
        annotated_id = annotation.get("commitment_id", "")
        candidates = [row for row in records if not annotated_id
                      or row.get("commitment_id") == annotated_id]
        for row in candidates:
            commitment = {**row, "id": row["commitment_id"]}
            result = classify_commitment_relation(
                commitment, processed.get("conversation", ""), annotation,
                processed.get("parsed_output", {}).get("grounding_refs", []),
            )
            if result["classification"] == "contradiction":
                return {"valid": False, "reason": result["reason"],
                        "commitment_id": result["commitment_id"]}
        return {"valid": True, "reason": "consistent_with_authoritative_state",
                "commitment_id": annotated_id or (candidates[0]["commitment_id"] if candidates else "")}

    @staticmethod
    def _repair_parent_for_turn(system, proposal_speaker_id: str,
                                response_speaker_id: str, dialogue: str,
                                day: int) -> str | None:
        text = " ".join(dialogue.lower().split())
        if not any(marker in text for marker in ("sorry", "missed", "failed", "couldn't", "didn't")):
            return None
        if not any(marker in text for marker in ("instead", "again", "make it up", "tomorrow")):
            return None
        options = system.repair_opportunities(
            proposal_speaker_id, response_speaker_id, day=day,
        )
        return options[0]["commitment_id"] if options else None

    @staticmethod
    def _diagnostics(setup, parsed, tags, raw_output):
        return {
            "tags": tags, "raw_response": raw_output,
            "action_reason": parsed.get("reason", ""), "old_score": setup["old_score"],
            "old_relationship_label": setup["old_relationship_label"],
            "allowed_actions": setup["allowed_actions"],
            "base_action_weights": setup.get("base_action_weights", {}),
            "relationship_adjusted_weights": setup.get("relationship_adjusted_weights", {}),
            "relationship_weight_adjustments": setup.get("relationship_weight_adjustments", {}),
            "relationship_decision_reasons": setup.get("relationship_decision_reasons", []),
            "relationship_snapshot": setup.get("relationship_snapshot", {}),
            "social_memories": setup.get("social_memories", []),
            "intent_adjusted_weights": setup.get("intent_adjusted_weights", {}),
            "reputation_adjusted_weights": setup.get("reputation_adjusted_weights", {}),
            "reputation_weight_adjustments": setup.get("reputation_weight_adjustments", {}),
            "rumor_claim": setup.get("rumor_claim"),
        }

    @staticmethod
    def _termination_reason(engine, session, turn) -> str:
        if turn.generation_error:
            return "generation_failure"
        if turn.final_action == "storm_off":
            return "storm_off"
        text = " ".join(turn.dialogue.lower().split())
        if any(marker in text for marker in ("goodbye", "see you later", "nothing more to add")):
            return "conversation_closed"
        prior = [" ".join(item.dialogue.lower().split()) for item in session.turns[:-1]]
        if any(SequenceMatcher(None, text, old).ratio() >= 0.9 for old in prior):
            return "repetition"
        if turn.dialogue_source == "policy_fallback_repetition":
            return "repetition"
        policy_hook = getattr(engine, "should_terminate_conversation", None)
        if policy_hook and policy_hook(session):
            return "policy_termination"
        return ""

    @staticmethod
    def _session_id(day, hour, location, first, second) -> str:
        return f"d{day}-h{hour:02d}-{'-'.join(str(location).lower().split())}-{first.lower()}-{second.lower()}"

    @staticmethod
    def _context_snapshot(context):
        keys = ("occupation", "speaker_activity", "speaker_activity_display", "speaker_activity_reason",
                "relationship_history", "relationship_snapshot", "social_memories",
                "reputation_context", "reputation_rumor_text", "relevant_memories",
                "recent_journals", "goals", "active_goal", "speaker_intent", "daily_event",
                "daily_event_relevant", "town_arcs", "recent_topics", "recent_utterances",
                "focus_options", "session_transcript", "most_recent_utterance",
                "grounding_sources")
        return {key: context.get(key) for key in keys}
