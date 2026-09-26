"""Orchestrate bounded, alternating conversation sessions."""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
import json
import random
from types import SimpleNamespace

from src.llm.grounding import GroundingResult, grounded_fallback, plan_grounded_dialogue
from src.llm.generation import (
    ConversationGenerationRequest,
    ConversationGenerationResult,
    generation_request_id,
)
from src.simulation.conversation_session import ConversationSession, ConversationTurn, ResponseOutcomeResolver
from src.simulation.conversation_execution import (
    ConversationRealizationJob,
    ConversationSessionResult,
)
from src.simulation.conversation_scheduler import derive_conversation_seed
from src.simulation.social_snapshot import ConversationTickSnapshot
from src.simulation.social_semantics import classify_commitment_relation


@dataclass
class _ConversationRealizationState:
    plan: object
    engine: object
    session: ConversationSession
    first: object
    second: object
    speaker: object
    listener: object
    transcript: list[dict]


@dataclass
class _PendingTurn:
    state: _ConversationRealizationState
    turn_index: int
    setup: dict
    context: dict
    raw_output: str = ""
    processed: dict | None = None
    generation_error: str = ""
    generation_attempt_count: int = 1
    regenerated_for_repetition: bool = False
    regenerated_for_grounding: bool = False
    regenerated_for_commitment_state: bool = False
    first_grounding_failure: str = ""
    grounded_repair_used: bool = False
    grounded_fallback_used: bool = False
    commitment_state: dict | None = None


class _SingleRequestClientAdapter:
    """Preserve custom single-request client semantics outside batched mode."""

    def __init__(self, client):
        self.client = client

    def generate_conversation_batch(self, requests):
        results = []
        for request in requests:
            try:
                if request.request_kind == "grounding_repair" and callable(
                    getattr(self.client, "repair_grounded_realization", None)
                ):
                    output = self.client.repair_grounded_realization(
                        dict(request.context),
                        request.invalid_output,
                        request.validation_error,
                    )
                else:
                    output = self.client.generate_conversation(dict(request.context))
                results.append(ConversationGenerationResult(
                    request.request_id, output=output,
                ))
            except Exception as error:
                results.append(ConversationGenerationResult(
                    request.request_id,
                    error=f"{type(error).__name__}: {error}",
                ))
        return results


class ConversationRunner:
    def __init__(self, max_turns: int = 4):
        self.max_turns = max(1, int(max_turns))
        self.outcomes = ResponseOutcomeResolver()

    def generate_conversations(self, engine, day: int, hour: int) -> None:
        scheduler = getattr(engine, "conversation_scheduler", None)
        backend = getattr(engine, "conversation_execution_backend", None)
        # Keep small historical test doubles and integrations source-compatible.
        if scheduler is None or backend is None or not hasattr(engine, "agents"):
            return self._generate_conversations_legacy(engine, day, hour)

        snapshot = ConversationTickSnapshot.capture(engine, day, hour)
        plans = scheduler.schedule(snapshot)
        # Characterization tests and downstream integrations historically
        # override this method to force a specific pair. Honor an instance-level
        # override for the first session without making production scheduling
        # dependent on the process-global random module.
        if plans and "choose_conversation_pair" in getattr(engine, "__dict__", {}):
            first_plan = plans[0]
            location_agents = [
                agent for agent in engine.agents
                if str(agent.location_id) == first_plan.location_id
            ]
            preferred = engine.choose_conversation_pair(location_agents)
            preferred_ids = tuple(str(agent.id) for agent in preferred)
            plans[0] = replace(
                first_plan,
                participant_ids=preferred_ids,
                initiating_agent_id=preferred_ids[0],
                session_id=self._session_id(
                    day, hour, first_plan.location_id,
                    preferred[0].name, preferred[1].name,
                ),
            )
        if not plans:
            print("No conversations this tick")
            engine.last_social_tick = self._tick_telemetry(snapshot, plans, [], backend)
            return

        by_id = {str(agent.id): agent for agent in engine.agents}
        states = []
        for plan in plans:
            # A private replica is captured before any commit. Query-like helpers
            # can therefore never mutate the authoritative engine during realization.
            replica = self._make_realization_replica(engine)
            # The LLM is a proposal component, not authoritative state. Sharing
            # it preserves client diagnostics and avoids copying model weights;
            # real clients serialize unsafe model.generate calls internally.
            replica.llm = engine.llm
            replica.conversation_policy.rng = random.Random(plan.request_seed)
            replica_by_id = {str(agent.id): agent for agent in replica.agents}
            first = replica_by_id[plan.participant_ids[0]]
            second = replica_by_id[plan.participant_ids[1]]

            session = ConversationSession(
                session_id=plan.session_id, day=plan.day, hour=plan.hour,
                location=plan.location_id,
                participants=[first.name, second.name],
                initiating_agent=first.name,
                snapshot_id=plan.snapshot_id,
                schedule_index=plan.schedule_index,
                request_seed=plan.request_seed,
                simulation_seed=plan.simulation_seed,
            )
            states.append(_ConversationRealizationState(
                plan, replica, session, first, second, first, second, [],
            ))

        # Barrier: the authoritative engine has not been passed to any worker.
        if backend.name == "batched":
            results, batch_telemetry = self._realize_batched(
                states, engine.llm, backend.batch_size,
            )
        else:
            jobs = []
            for state in states:
                def realize(state=state):
                    self._generate_session(
                        state.engine, state.session, state.first, state.second,
                    )
                    return state.session
                jobs.append(ConversationRealizationJob(state.plan, realize))
            results = backend.realize(jobs)
            batch_telemetry = {}
        ordered = sorted(results, key=lambda item: item.plan.schedule_index)
        for commit_position, result in enumerate(ordered):
            if result.session is None:
                continue
            initiator = by_id[result.plan.participant_ids[0]]
            other = by_id[result.plan.participant_ids[1]]
            result.session.commit_position = commit_position
            self._apply_and_record(engine, result.session, initiator, other)
        engine.last_social_tick = self._tick_telemetry(
            snapshot, plans, ordered, backend, batch_telemetry,
        )

    @staticmethod
    def _make_realization_replica(engine):
        """Copy only conversation-visible machinery, excluding world authorities.

        A shallow shell preserves the engine's compatibility methods; the shell
        is then deeply copied after unrelated and mutation-capable authorities
        have been removed. Materials are retained only as an immutable-looking
        goods catalog used by proposal recognition.
        """
        shell = copy.copy(engine)
        for name in (
            "economy", "crime", "justice", "plan_system", "state", "persistence",
            "activity_system", "simulation_loop", "journal_system", "reporter",
            "logger", "conversation_recorder", "conversation_effects_applier",
            "conversation_execution_backend",
        ):
            if hasattr(shell, name):
                setattr(shell, name, None)
        shell.llm = None
        shell.materials = SimpleNamespace(
            goods=copy.deepcopy(getattr(getattr(engine, "materials", None), "goods", {}))
        )
        replica = copy.deepcopy(shell)
        replica.llm = engine.llm
        return replica

    def _generate_conversations_legacy(self, engine, day: int, hour: int) -> None:
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

    @staticmethod
    def _tick_telemetry(snapshot, plans, results, backend, batch_telemetry=None) -> dict:
        telemetry = {
            "snapshot_id": snapshot.snapshot_id,
            "eligible_agent_count": len(snapshot.participants),
            "scheduled_session_count": len(plans),
            "schedule_order": [plan.session_id for plan in plans],
            "execution_backend": backend.name,
            "commit_order": [
                result.plan.session_id for result in results if result.session is not None
            ],
            "worker_failures": [
                {"session_id": result.plan.session_id, "error": result.error}
                for result in results if result.error
            ],
            "repair_count": sum(
                turn.grounded_repair_used for result in results if result.session
                for turn in result.session.turns
            ),
            "fallback_count": sum(
                turn.grounded_fallback_used for result in results if result.session
                for turn in result.session.turns
            ),
        }
        telemetry.update(batch_telemetry or {})
        return telemetry

    def _realize_batched(self, states, llm, batch_size):
        """Advance private sessions one turn wave at a time."""
        ordered_states = sorted(states, key=lambda state: state.plan.schedule_index)
        active = list(ordered_states)
        failures = {}
        metrics = {
            "active_session_count_by_wave": [],
            "generation_batch_count": 0,
            "batch_sizes": [],
            "repair_batch_count": 0,
            "generation_request_count": 0,
            "successful_generation_requests": 0,
            "failed_generation_requests": 0,
            "generation_wall_clock_seconds": 0.0,
            "generated_token_count": 0,
        }
        while active:
            metrics["active_session_count_by_wave"].append(len(active))
            pending = []
            for state in active:
                try:
                    pending.append(self._prepare_pending_turn(state))
                except Exception as error:
                    failures[state.plan.session_id] = (
                        f"{type(error).__name__}: {error}"
                    )
            pending = [
                item for item in pending
                if item.state.plan.session_id not in failures
            ]
            if not pending:
                break

            primary = [self._generation_request(item, "primary", 0) for item in pending]
            primary_results = self._invoke_generation_batches(
                llm, primary, batch_size, metrics, repair=False,
            )
            grounding_repairs = []
            for item, request in zip(pending, primary):
                result = primary_results[request.request_id]
                self._accept_primary_result(item, result)
                if self._needs_grounding_repair(item):
                    grounding_repairs.append(self._generation_request(
                        item,
                        "grounding_repair" if item.context.get(
                            "grounded_content_plan"
                        ) else "grounding_retry",
                        item.generation_attempt_count - 1,
                        invalid_output=item.raw_output,
                        validation_error=item.first_grounding_failure,
                    ))
            repair_results = self._invoke_generation_batches(
                llm, grounding_repairs, batch_size, metrics, repair=True,
            )
            repair_by_session = {
                request.session_id: repair_results[request.request_id]
                for request in grounding_repairs
            }
            for item in pending:
                result = repair_by_session.get(item.state.session.session_id)
                if result:
                    self._accept_grounding_repair(item, result)

            commitment_repairs = []
            for item in pending:
                item.commitment_state = self._commitment_state_check(
                    item.context, item.processed,
                )
                if self._needs_commitment_repair(item):
                    item.generation_attempt_count += 1
                    item.regenerated_for_commitment_state = True
                    item.context = {
                        **item.context,
                        "commitment_state_correction": item.commitment_state["reason"],
                    }
                    commitment_repairs.append(self._generation_request(
                        item, "commitment_repair",
                        item.generation_attempt_count - 1,
                    ))
            commitment_results = self._invoke_generation_batches(
                llm, commitment_repairs, batch_size, metrics, repair=True,
            )
            commitment_by_session = {
                request.session_id: commitment_results[request.request_id]
                for request in commitment_repairs
            }
            for item in pending:
                result = commitment_by_session.get(item.state.session.session_id)
                if result:
                    self._accept_commitment_repair(item, result)

            echo_repairs = []
            for item in pending:
                if self._needs_anti_echo_repair(item):
                    item.generation_attempt_count += 1
                    item.regenerated_for_repetition = True
                    item.context = {
                        **item.context,
                        "anti_echo_retry": True,
                        "repeated_candidate": item.processed["conversation"],
                    }
                    echo_repairs.append(self._generation_request(
                        item, "anti_echo", item.generation_attempt_count - 1,
                    ))
            echo_results = self._invoke_generation_batches(
                llm, echo_repairs, batch_size, metrics, repair=True,
            )
            echo_by_session = {
                request.session_id: echo_results[request.request_id]
                for request in echo_repairs
            }
            for item in pending:
                result = echo_by_session.get(item.state.session.session_id)
                if result:
                    self._accept_ordinary_regeneration(item, result)

            next_active = []
            for item in pending:
                state = item.state
                try:
                    self._finalize_pending_turn(item)
                except Exception as error:
                    failures[state.plan.session_id] = (
                        f"{type(error).__name__}: {error}"
                    )
                    continue
                if not state.session.termination_reason:
                    if len(state.session.turns) >= self.max_turns:
                        state.session.termination_reason = "max_turns"
                    else:
                        next_active.append(state)
            active = next_active

        results = []
        for state in ordered_states:
            error = failures.get(state.plan.session_id, "")
            results.append(ConversationSessionResult(
                state.plan, None if error else state.session, error,
            ))
        elapsed = metrics["generation_wall_clock_seconds"]
        requests = metrics["generation_request_count"]
        tokens = metrics["generated_token_count"]
        metrics["generation_requests_per_second"] = (
            requests / elapsed if elapsed else 0.0
        )
        metrics["generated_tokens_per_second"] = tokens / elapsed if elapsed else 0.0
        metrics["configured_batch_size"] = batch_size
        runtime_metadata = getattr(llm, "generation_runtime_metadata", None)
        if callable(runtime_metadata):
            metrics.update(runtime_metadata())
        return results, metrics

    def _prepare_pending_turn(self, state):
        turn_index = len(state.session.turns)
        try:
            setup = state.engine.prepare_conversation_context(
                location_id=state.session.location,
                speaker=state.speaker,
                listener=state.listener,
                current_day=state.session.day,
                session_transcript=state.transcript,
            )
        except TypeError:
            setup = state.engine.prepare_conversation_context(
                location_id=state.session.location,
                speaker=state.speaker,
                listener=state.listener,
                current_day=state.session.day,
            )
        context = setup["context"]
        context["session_transcript"] = list(state.transcript)
        context["most_recent_utterance"] = (
            state.transcript[-1]["dialogue"] if state.transcript else ""
        )
        context["conversation_snapshot_id"] = state.session.snapshot_id
        context["conversation_session_id"] = state.session.session_id
        context["conversation_schedule_index"] = state.session.schedule_index
        context["conversation_turn_index"] = turn_index
        if "grounded_content_plan" not in context:
            plan = plan_grounded_dialogue(context)
            context["grounded_content_plan"] = plan.prompt_dict() if plan else None
        return _PendingTurn(state, turn_index, setup, context)

    @staticmethod
    def _invoke_generation_batches(llm, requests, batch_size, metrics, *, repair):
        results = {}
        for offset in range(0, len(requests), batch_size):
            batch = requests[offset:offset + batch_size]
            metrics["generation_batch_count"] += 1
            metrics["batch_sizes"].append(len(batch))
            metrics["generation_request_count"] += len(batch)
            if repair:
                metrics["repair_batch_count"] += 1
            started = __import__("time").perf_counter()
            try:
                rows = llm.generate_conversation_batch(batch)
                by_id = {row.request_id: row for row in rows}
                if len(by_id) != len(rows):
                    raise ValueError("batch client returned duplicate request IDs")
                missing = [row.request_id for row in batch if row.request_id not in by_id]
                extra = set(by_id) - {row.request_id for row in batch}
                if missing or extra:
                    raise ValueError(
                        f"batch result identity mismatch: missing={missing}, extra={sorted(extra)}"
                    )
            except Exception as error:
                message = f"{type(error).__name__}: {error}"
                by_id = {
                    row.request_id: ConversationGenerationResult(
                        row.request_id, error=message,
                    )
                    for row in batch
                }
            metrics["generation_wall_clock_seconds"] += (
                __import__("time").perf_counter() - started
            )
            for request in batch:
                result = by_id[request.request_id]
                results[request.request_id] = result
                metrics["generated_token_count"] += result.generated_token_count
                if result.error:
                    metrics["failed_generation_requests"] += 1
                else:
                    metrics["successful_generation_requests"] += 1
        return results

    @staticmethod
    def _generation_request(
        item, request_kind, generation_attempt, *, invalid_output="",
        validation_error="",
    ):
        session = item.state.session
        seed = derive_conversation_seed(
            session.simulation_seed, session.day, session.hour,
            session.session_id, item.turn_index, generation_attempt,
            schedule_index=session.schedule_index,
            request_kind=request_kind,
        )
        context = {**item.context, "conversation_request_seed": seed}
        item.context = context
        request_id = generation_request_id(
            simulation_seed=session.simulation_seed,
            day=session.day,
            hour=session.hour,
            session_id=session.session_id,
            schedule_index=session.schedule_index,
            turn_index=item.turn_index,
            generation_attempt=generation_attempt,
            request_kind=request_kind,
        )
        return ConversationGenerationRequest(
            request_id=request_id,
            session_id=session.session_id,
            schedule_index=session.schedule_index,
            turn_index=item.turn_index,
            generation_attempt=generation_attempt,
            seed=seed,
            request_kind=request_kind,
            context=context,
            invalid_output=invalid_output,
            validation_error=validation_error,
        )

    def _process_pending_output(self, item, result, *, enforce=None):
        item.raw_output = result.output
        item.generation_error = result.error
        if enforce is None:
            enforce = not getattr(item.state.engine.llm, "is_deterministic_fake", False)
        item.processed = item.state.engine.process_conversation_output(
            raw_output=item.raw_output,
            allowed_actions=item.setup["allowed_actions"],
            speaker=item.state.speaker,
            listener=item.state.listener,
            old_relationship_label=item.setup["old_relationship_label"],
            location_id=item.state.session.location,
            suggested_action=item.setup["suggested_action"],
            current_day=item.state.session.day,
            conversation_context=item.context,
            enforce_information_boundaries=enforce,
        )

    def _accept_primary_result(self, item, result):
        self._process_pending_output(item, result)
        if item.generation_error and item.context.get("grounded_content_plan"):
            self._apply_grounded_fallback(item, advisory_key="generation_error")

    @staticmethod
    def _needs_grounding_repair(item):
        if item.generation_error:
            return False
        if getattr(item.state.engine.llm, "is_deterministic_fake", False):
            return False
        if item.processed["grounding"].valid:
            return False
        item.first_grounding_failure = item.processed["grounding"].reason
        item.generation_attempt_count += 1
        item.regenerated_for_grounding = True
        item.grounded_repair_used = bool(item.context.get("grounded_content_plan"))
        item.context = {
            **item.context,
            "grounding_correction": item.first_grounding_failure,
            "invalid_grounded_output": item.raw_output,
        }
        return True

    def _accept_grounding_repair(self, item, result):
        self._process_pending_output(item, result, enforce=True)
        if item.generation_error or not item.processed["grounding"].valid:
            if item.context.get("grounded_content_plan"):
                self._apply_grounded_fallback(
                    item,
                    advisory_key="repair_error" if item.generation_error else "",
                )
            else:
                item.processed["conversation"] = (
                    item.state.engine.conversation_policy.get_grounded_fallback_dialogue(
                        speaker=item.state.speaker,
                        context=item.context,
                        location_id=item.state.session.location,
                    )
                )
                item.processed["parsed_action"] = "chat"
                item.processed["dialogue_source"] = (
                    "policy_fallback_unsupported_grounding"
                )
                item.processed["grounding"] = GroundingResult(
                    True,
                    valid_refs=item.processed["parsed_output"].get(
                        "grounding_refs", []
                    ),
                    follow_through=item.processed["grounding"].follow_through,
                )

    def _apply_grounded_fallback(self, item, advisory_key=""):
        original_error = item.generation_error
        fallback_output = json.dumps({
            "utterance": grounded_fallback(item.context["grounded_content_plan"])
        })
        item.raw_output = fallback_output
        item.processed = item.state.engine.process_conversation_output(
            raw_output=fallback_output,
            allowed_actions=item.setup["allowed_actions"],
            speaker=item.state.speaker,
            listener=item.state.listener,
            old_relationship_label=item.setup["old_relationship_label"],
            location_id=item.state.session.location,
            suggested_action=item.setup["suggested_action"],
            current_day=item.state.session.day,
            conversation_context=item.context,
            enforce_information_boundaries=True,
        )
        if advisory_key and original_error:
            item.processed.setdefault("grounding_metadata_advisory", {})[
                advisory_key
            ] = original_error
        item.generation_error = ""
        item.grounded_fallback_used = True
        if advisory_key == "repair_error" or (
            not item.processed["grounding"].valid
        ):
            item.processed["parsed_action"] = "chat"
            item.processed["dialogue_source"] = (
                "policy_fallback_unsupported_grounding"
            )
            item.processed["grounding"] = GroundingResult(
                True,
                valid_refs=item.processed["parsed_output"].get("grounding_refs", []),
                follow_through=item.processed["grounding"].follow_through,
            )

    @staticmethod
    def _needs_commitment_repair(item):
        return bool(
            not item.generation_error
            and not item.commitment_state["valid"]
            and not getattr(item.state.engine.llm, "is_deterministic_fake", False)
        )

    def _accept_commitment_repair(self, item, result):
        self._process_pending_output(item, result)
        item.commitment_state = self._commitment_state_check(
            item.context, item.processed,
        )
        if not item.generation_error and not item.commitment_state["valid"]:
            item.processed["conversation"] = "I understand."
            item.processed["parsed_action"] = "chat"
            item.processed["dialogue_source"] = "policy_fallback_commitment_state"
            item.processed["parsed_output"]["commitment_relation"] = {
                "commitment_id": item.commitment_state["commitment_id"],
                "relation": "unrelated",
                "confidence": "none",
            }

    def _needs_anti_echo_repair(self, item):
        return bool(
            item.state.transcript
            and not item.generation_error
            and not getattr(item.state.engine.llm, "is_deterministic_fake", False)
            and self._matches_prior_turn(
                item.processed["conversation"], item.state.transcript,
            )
        )

    def _accept_ordinary_regeneration(self, item, result):
        self._process_pending_output(item, result)

    def _finalize_pending_turn(self, item):
        state = item.state
        engine = state.engine
        session = state.session
        speaker = state.speaker
        listener = state.listener
        setup = item.setup
        context = item.context
        processed = item.processed
        commitment_state = item.commitment_state or self._commitment_state_check(
            context, processed,
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
            conversation=dialogue,
            parsed_action=processed["parsed_action"],
            conversation_tags=tags,
            allowed_actions=setup["allowed_actions"],
            inferred_action=inferred,
        )
        tags = engine.finalize_conversation_tags(
            conversation=dialogue,
            conversation_tags=tags,
            relationship_label=setup["old_relationship_label"],
            action=action,
        )
        response_to = None
        resolution_reason = ""
        if session.turns and session.turns[-1].final_action in self.outcomes.RESPONSIVE_ACTIONS:
            previous = session.turns[-1]
            goods = {
                good_id: definition.name
                for good_id, definition in getattr(engine.materials, "goods", {}).items()
            }
            proposal = (
                engine.commitment_system.recognize_proposal(
                    previous.dialogue, day=session.day, known_goods=goods,
                )
                if getattr(engine, "commitment_system", None) else None
            )
            outcome, resolution_reason = self.outcomes.resolve_with_reason(
                previous.final_action,
                dialogue,
                proposal=proposal,
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
                    "cooperate" if proposal["commitment_type"] == "meet"
                    else "ask_for_help"
                )
                outcome, resolution_reason = self.outcomes.resolve_with_reason(
                    semantic_action,
                    dialogue,
                    proposal=proposal,
                    parsed_action=processed["parsed_action"],
                    social_response=parsed.get("social_response"),
                )
                response_to = previous.turn_index
                previous.response_outcome = outcome
        turn = ConversationTurn(
            turn_index=item.turn_index,
            speaker=speaker.name,
            listener=listener.name,
            dialogue=dialogue,
            suggested_action=setup["suggested_action"],
            parsed_action=processed["parsed_action"],
            inferred_action=inferred,
            inference_reason=inference_reason,
            final_action=action,
            final_action_reason=final_reason,
            action_source=parsed.get("action_source", ""),
            dialogue_source=processed["dialogue_source"],
            generation_attempt_count=item.generation_attempt_count,
            regenerated_for_repetition=item.regenerated_for_repetition,
            regenerated_for_grounding=item.regenerated_for_grounding,
            regenerated_for_commitment_state=item.regenerated_for_commitment_state,
            commitment_state_valid=commitment_state["valid"],
            commitment_state_reason=commitment_state["reason"],
            related_commitment_id=commitment_state["commitment_id"],
            grounding_valid=grounding.valid,
            grounding_reason=(grounding.reason or item.first_grounding_failure),
            grounding_candidate_type=grounding.candidate_type,
            grounding_refs=grounding.valid_refs,
            invalid_grounding_refs=grounding.invalid_refs,
            grounding_metadata_advisory=processed.get(
                "grounding_metadata_advisory", {}
            ),
            grounding_metadata_disagreements=processed.get(
                "grounding_metadata_disagreements", []
            ),
            grounded_repair_used=item.grounded_repair_used,
            grounded_fallback_used=item.grounded_fallback_used,
            generation_error=item.generation_error,
            response_to_turn=response_to,
            response_outcome=None,
            social_response=parsed.get("social_response", {}),
            commitment_relation=parsed.get("commitment_relation", {}),
            follow_through=grounding.follow_through,
            response_resolution_reason=resolution_reason,
            context_evidence=context.get("context_evidence", {}),
            context_snapshot=self._context_snapshot(context),
            diagnostics=self._diagnostics(setup, parsed, tags, item.raw_output),
        )
        turn._speaker_intent = setup.get("speaker_intent")
        turn._listener_intent = setup.get("listener_intent")
        session.turns.append(turn)
        state.transcript.append({
            "turn_index": item.turn_index,
            "speaker": speaker.name,
            "listener": listener.name,
            "dialogue": dialogue,
        })
        reason = self._termination_reason(engine, session, turn)
        if reason:
            session.termination_reason = reason
        else:
            state.speaker, state.listener = listener, speaker

    def _generate_session(self, engine, session, initiator, other) -> None:
        """Realize one session through the shared turn-wave state machine."""
        plan = SimpleNamespace(
            session_id=session.session_id,
            schedule_index=getattr(session, "schedule_index", 0),
        )
        state = _ConversationRealizationState(
            plan, engine, session, initiator, other, initiator, other, [],
        )
        results, _ = self._realize_batched(
            [state], _SingleRequestClientAdapter(engine.llm), 1,
        )
        if results[0].error:
            raise RuntimeError(results[0].error)

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
            grounding_metadata_advisory=turn.grounding_metadata_advisory,
            grounding_metadata_disagreements=turn.grounding_metadata_disagreements,
            grounded_repair_used=turn.grounded_repair_used,
            grounded_fallback_used=turn.grounded_fallback_used,
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
                "grounding_sources", "grounding_packet", "grounded_content_plan")
        return {key: context.get(key) for key in keys}
