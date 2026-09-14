from src.agents.agent import Agent
from src.agents.intent import AgentIntent
from src.behavior.intent_planner import IntentPlanner


class IntentSystem:
    def __init__(
        self,
        intent_planner: IntentPlanner,
        agent_intents: dict[str, AgentIntent],
        intent_history: list[AgentIntent] | None = None,
        goal_planner=None,
    ):
        self.intent_planner = intent_planner
        self.agent_intents = agent_intents
        self.intent_history = intent_history if intent_history is not None else []
        self.goal_planner = goal_planner

    def archive_intent(self, intent: AgentIntent) -> None:
        already_archived = any(
            archived.id == intent.id
            for archived in self.intent_history
        )

        if not already_archived:
            self.intent_history.append(intent)

    def get_intent_listener_weight_bonus(
        self,
        speaker: Agent,
        listener: Agent,
    ) -> int:
        intent = self.agent_intents.get(speaker.name)

        if not intent or intent.status != "active":
            return 0

        if intent.target_agent != listener.name:
            return 0

        if intent.intent_type == "repair_relationship":
            return 5

        if intent.intent_type == "build_friendship":
            return 4

        return 2

    def update_agent_intents(
        self,
        agents: list[Agent],
        current_day: int,
        engine,
    ) -> None:
        self._engine_for_goal_check = engine
        intent_type_counts = {}
        agents_by_name = {agent.name: agent for agent in agents}

        for agent_name, intent in list(self.agent_intents.items()):
            if intent.status == "active" and intent.is_expired(current_day):
                intent.mark_failed(
                    day=current_day,
                    reason="Intent expired before reaching enough progress.",
                    status="expired",
                )
                intent.expiration_reason = (
                    "no_opportunity" if intent.opportunity_count == 0
                    else "despite_opportunity"
                )
                self.archive_intent(intent)
                owner = agents_by_name.get(agent_name)
                goal = owner.get_goal(intent.parent_goal_id) if owner else None
                if goal:
                    goal.current_intent_id = None
                    goal.evidence.append({
                        "type": "intent_terminal", "day": current_day,
                        "intent_id": intent.id, "status": intent.status,
                        "expiration_reason": intent.expiration_reason,
                    })
                self.agent_intents.pop(agent_name, None)
                continue

            if intent.is_active(current_day):
                intent_type_counts[intent.intent_type] = (
                    intent_type_counts.get(intent.intent_type, 0) + 1
                )

        for agent in agents:
            if self.goal_planner:
                self.goal_planner.ensure_goals(agent, engine, current_day)
            current_intent = self.agent_intents.get(agent.name)

            if current_intent and current_intent.is_active(current_day):
                goal = agent.get_goal(current_intent.parent_goal_id)
                if goal:
                    complete, reason = self.goal_planner.goal_is_complete(
                        goal, agent, engine
                    )
                    if complete:
                        goal.mark_achieved(current_day, reason)
                        current_intent.mark_succeeded(current_day, "Parent goal achieved.")
                        self.archive_intent(current_intent)
                        self.agent_intents.pop(agent.name, None)
                        current_intent = None
                    else:
                        replacement, trigger = self.goal_planner.should_adapt(
                            goal, current_intent, agent, engine, current_day
                        )
                        if replacement:
                            old_strategy = current_intent.strategy
                            current_intent.mark_superseded(
                                current_day,
                                f"Replaced by {replacement.name} after {trigger} change.",
                                trigger=trigger,
                            )
                            self.archive_intent(current_intent)
                            goal.current_intent_id = None
                            goal.adaptation_count += 1
                            goal.current_strategy = replacement.name
                            goal.current_strategy_target = replacement.target_agent
                            goal.evidence.append({
                                "type": "strategy_adaptation", "day": current_day,
                                "trigger": trigger, "old_strategy": old_strategy,
                                "new_strategy": replacement.name,
                                "preserved_progress": goal.progress,
                                "old_target_agent": current_intent.target_agent,
                                "new_target_agent": replacement.target_agent,
                                "relationship_reason": replacement.relationship_reason,
                                "relationship_snapshot": replacement.relationship_snapshot,
                                "relevant_social_memories": list(
                                    replacement.relevant_social_memories
                                ),
                                "prior_counterpart_memories": [
                                    memory.summary for memory in agent.get_social_memories(
                                        current_intent.target_agent, limit=3
                                    )
                                ] if current_intent.target_agent else [],
                            })
                            self.agent_intents.pop(agent.name, None)
                            current_intent = None
                        elif trigger == "hard_constraint":
                            current_intent.mark_blocked(
                                current_day, "No feasible strategy remains."
                            )
                            self.archive_intent(current_intent)
                            goal.current_intent_id = None
                            goal.status = "blocked"
                            goal.evidence.append({
                                "type": "blocked", "day": current_day,
                                "reason": "No feasible strategy remains.",
                            })
                            self.agent_intents.pop(agent.name, None)
                            current_intent = None

                if current_intent and current_intent.is_active(current_day):
                    continue

            if self.goal_planner:
                for blocked_goal in agent.get_active_goals():
                    if not any(
                        candidate.feasible for candidate in
                        self.goal_planner.generate_strategies(
                            blocked_goal, agent, engine
                        )
                    ):
                        blocked_goal.status = "blocked"
                        blocked_goal.current_intent_id = None
                        blocked_goal.evidence.append({
                            "type": "blocked", "day": current_day,
                            "reason": "No feasible strategy remains.",
                        })
                goal = self.goal_planner.choose_primary_goal(agent, engine, current_day)
                if goal:
                    strategy = self.goal_planner.select_strategy(goal, agent, engine)
                    if strategy:
                        previous_strategy = goal.current_strategy
                        previous_target = goal.current_strategy_target
                        if previous_strategy and (
                            previous_strategy != strategy.name
                            or previous_target != strategy.target_agent
                        ):
                            target = previous_target or (
                                goal.target_agents[0] if goal.target_agents else None
                            )
                            relationship = (
                                engine.relationships.get_score(agent.name, target)
                                if target else None
                            )
                            risk = self.goal_planner.reputation_risk(agent, target)
                            if abs(risk - goal.last_reputation_risk) >= 0.75:
                                trigger = "reputation"
                            elif (
                                relationship is not None
                                and goal.last_relationship_score is not None
                                and relationship // 3 != goal.last_relationship_score // 3
                            ) or (
                                previous_target != strategy.target_agent
                                and strategy.relationship_influenced
                            ):
                                trigger = "relationship"
                            else:
                                trigger = "terminal_state"
                            goal.adaptation_count += 1
                            goal.evidence.append({
                                "type": "strategy_adaptation", "day": current_day,
                                "trigger": trigger,
                                "old_strategy": previous_strategy,
                                "new_strategy": strategy.name,
                                "old_target_agent": previous_target,
                                "preserved_progress": goal.progress,
                                "new_target_agent": strategy.target_agent,
                                "relationship_reason": strategy.relationship_reason,
                                "relationship_snapshot": strategy.relationship_snapshot,
                                "relevant_social_memories": list(
                                    strategy.relevant_social_memories
                                ),
                                "prior_counterpart_memories": [
                                    memory.summary for memory in agent.get_social_memories(
                                        previous_target, limit=3
                                    )
                                ] if previous_target else [],
                            })
                        new_intent = self.intent_planner.create_intent_from_goal(
                            goal, strategy, current_day
                        )
                        goal.current_intent_id = new_intent.id
                        goal.current_strategy = strategy.name
                        goal.current_strategy_target = strategy.target_agent
                        goal.strategy_started_day = current_day
                        goal.last_review_day = current_day
                        target = strategy.target_agent or (
                            goal.target_agents[0] if goal.target_agents else None
                        )
                        goal.last_relationship_score = (
                            engine.relationships.get_score(agent.name, target)
                            if target else None
                        )
                        goal.last_reputation_risk = self.goal_planner.reputation_risk(
                            agent, target
                        )
                        goal.evidence.append({
                            "type": "strategy_selected", "day": current_day,
                            "strategy": strategy.name, "score": strategy.score,
                            "intent_id": new_intent.id,
                            "target_agent": strategy.target_agent,
                            "relationship_influenced": strategy.relationship_influenced,
                            "relationship_reason": strategy.relationship_reason,
                            "relationship_snapshot": strategy.relationship_snapshot,
                            "relevant_social_memories": list(
                                strategy.relevant_social_memories
                            ),
                        })
                        self.agent_intents[agent.name] = new_intent
                    continue
                continue

            new_intent = self.intent_planner.create_intent_for_agent(
                agent=agent,
                engine=engine,
                current_day=current_day,
            )

            if not new_intent:
                continue

            # Prevent all agents from collapsing into the same intent type.
            # With 4 agents, allow at most 2 agents to share the same active intent type.
            if intent_type_counts.get(new_intent.intent_type, 0) >= 2:
                continue

            self.agent_intents[agent.name] = new_intent
            intent_type_counts[new_intent.intent_type] = (
                intent_type_counts.get(new_intent.intent_type, 0) + 1
            )

    def get_agent_intent_text(self, agent_name: str) -> str:
        intent = self.agent_intents.get(agent_name)

        if not intent or intent.status != "active":
            return "No active intent."

        return intent.description

    def update_intent_after_activity(
        self,
        *,
        day: int,
        agent: Agent,
        location_id: str,
        activity_name: str,
    ) -> dict | None:
        """Count a real target-location visit at most once per intent per day."""
        intent = self.agent_intents.get(agent.name)
        if (
            not intent or intent.status != "active" or not intent.target_location
            or intent.target_location != location_id
        ):
            return None
        intent.opportunity_count += 1
        marker = f"Day {day}: reached target location"
        if any(item.startswith(marker) for item in intent.evidence):
            return None
        evidence = f"{marker} {location_id} during '{activity_name}'."
        intent.add_progress(1, evidence)
        goal = agent.get_goal(intent.parent_goal_id)
        if goal:
            goal.add_progress(1, day, {
                "intent_id": intent.id, "strategy": intent.strategy,
                "activity": activity_name, "location": location_id,
            })
            if goal.adaptation_count:
                goal.recovered_after_adaptation = True
        goal_achieved = False
        if goal and self.goal_planner and hasattr(self, "_engine_for_goal_check"):
            goal_achieved, goal_reason = self.goal_planner.goal_is_complete(
                goal, agent, self._engine_for_goal_check
            )
            if goal_achieved:
                goal.mark_achieved(day, goal_reason)
        completed = intent.progress >= intent.progress_goal or goal_achieved
        if completed:
            intent.mark_succeeded(
                day,
                "Parent goal achieved." if goal_achieved
                else "Target-location activity advanced the tactic.",
            )
            self.archive_intent(intent)
            self.agent_intents.pop(agent.name, None)
            if goal:
                goal.current_intent_id = None
                if self.goal_planner and hasattr(self, "_engine_for_goal_check"):
                    achieved, reason = self.goal_planner.goal_is_complete(
                        goal, agent, self._engine_for_goal_check
                    )
                    if achieved and goal.status != "achieved":
                        goal.mark_achieved(day, reason)
        return {
            "agent": agent.name, "intent_id": intent.id,
            "status": intent.status, "progress": intent.progress,
        }

    def adjust_action_weights_for_intent(
        self,
        weights: dict[str, int],
        intent: AgentIntent | None,
        listener_name: str,
    ) -> dict[str, int]:
        adjusted = dict(weights)

        if not intent or intent.status != "active":
            return adjusted

        target_matches = (
            intent.target_agent is None
            or intent.target_agent == listener_name
        )

        if not target_matches:
            return adjusted

        strategy_bonuses = {
            "direct_cooperation": {"cooperate": 4},
            "apologize_directly": {"apologize": 5, "chat": 1},
            "offer_help": {"offer_help": 4},
            "low_risk_chat": {"chat": 4},
            "ask_target_directly": {"ask_for_help": 4},
            "ask_informed_agent": {"ask_for_help": 3, "chat": 1},
            "ask_reliable_partner": {"ask_for_help": 4, "chat": 1},
        }
        for action, bonus in strategy_bonuses.get(intent.strategy, {}).items():
            if action in adjusted:
                adjusted[action] += bonus

        if intent.intent_type == "repair_relationship":
            if "apologize" in adjusted:
                adjusted["apologize"] += 4
            if "offer_help" in adjusted:
                adjusted["offer_help"] += 2
            if "chat" in adjusted:
                adjusted["chat"] += 1
            if "argue" in adjusted:
                adjusted["argue"] = max(1, adjusted["argue"] - 2)

        elif intent.intent_type == "build_friendship":
            if "compliment" in adjusted:
                adjusted["compliment"] += 1
            if "offer_help" in adjusted:
                adjusted["offer_help"] += 3
            if "cooperate" in adjusted:
                adjusted["cooperate"] += 2

        elif intent.intent_type == "investigate":
            if "ask_for_help" in adjusted:
                adjusted["ask_for_help"] += 3
            if "share_rumor" in adjusted:
                adjusted["share_rumor"] += 2
            if "chat" in adjusted:
                adjusted["chat"] += 1

        elif intent.intent_type == "socialize":
            if "chat" in adjusted:
                adjusted["chat"] += 2
            if "ask_for_help" in adjusted:
                adjusted["ask_for_help"] += 1
            if "offer_help" in adjusted:
                adjusted["offer_help"] += 1

        elif intent.intent_type == "seek_work":
            if "ask_for_help" in adjusted:
                adjusted["ask_for_help"] += 1
            if "cooperate" in adjusted:
                adjusted["cooperate"] += 1
            if "chat" in adjusted:
                adjusted["chat"] += 2

        return adjusted

    def update_intents_after_conversation(
        self,
        day: int,
        location_id: str,
        speaker: Agent,
        listener: Agent,
        action: str,
        relationship_change: int,
        new_score: int,
        conversation_tags: list[str],
    ) -> dict | None:
        intent = self.agent_intents.get(speaker.name)

        if not intent or intent.status != "active":
            return None

        applicable = (
            intent.target_agent in (None, listener.name)
            and intent.target_location in (None, location_id)
        )
        if applicable:
            intent.opportunity_count += 1

        progress_amount = self.get_conversation_progress_amount(
            intent=intent,
            location_id=location_id,
            listener=listener,
            action=action,
            relationship_change=relationship_change,
            new_score=new_score,
            conversation_tags=conversation_tags,
        )

        if progress_amount <= 0:
            failure_reason = self.get_conversation_failure_reason(
                intent=intent,
                listener=listener,
                action=action,
                relationship_change=relationship_change,
                new_score=new_score,
            )

            if failure_reason:
                intent.mark_failed(day=day, reason=failure_reason)
                self.archive_intent(intent)
                self.agent_intents.pop(speaker.name, None)
                goal = speaker.get_goal(intent.parent_goal_id)
                if goal:
                    goal.current_intent_id = None
                    goal.evidence.append({
                        "type": "intent_terminal", "day": day,
                        "intent_id": intent.id, "status": intent.status,
                        "reason": failure_reason,
                    })

                return {
                    "agent": speaker.name,
                    "intent_id": intent.id,
                    "intent_type": intent.intent_type,
                    "status": intent.status,
                    "progress": intent.progress,
                    "progress_goal": intent.progress_goal,
                    "reason": failure_reason,
                }

            return None

        evidence = (
            f"Day {day}: {speaker.name} used action '{action}' with "
            f"{listener.name} at {location_id}; relationship change "
            f"{relationship_change:+d}."
        )

        intent.add_progress(
            amount=progress_amount,
            evidence=evidence,
        )

        goal = speaker.get_goal(intent.parent_goal_id)
        if goal:
            goal.add_progress(
                progress_amount,
                day,
                {
                    "intent_id": intent.id, "strategy": intent.strategy,
                    "action": action, "target_agent": listener.name,
                    "location": location_id,
                },
            )
            if goal.adaptation_count:
                goal.recovered_after_adaptation = True

        goal_achieved = False
        goal_reason = ""
        if goal and self.goal_planner and hasattr(self, "_engine_for_goal_check"):
            goal_achieved, goal_reason = self.goal_planner.goal_is_complete(
                goal, speaker, self._engine_for_goal_check
            )

        success_reason = self.get_success_reason(
            intent=intent,
            new_score=new_score,
        )
        if goal_achieved:
            success_reason = "Parent goal achieved."

        if success_reason:
            intent.mark_succeeded(day=day, reason=success_reason)
            self.archive_intent(intent)
            self.agent_intents.pop(speaker.name, None)
            if goal:
                goal.current_intent_id = None
                if self.goal_planner and hasattr(self, "_engine_for_goal_check"):
                    complete, goal_reason = self.goal_planner.goal_is_complete(
                        goal, speaker, self._engine_for_goal_check
                    )
                else:
                    complete = goal.progress >= goal.progress_target
                    goal_reason = "Deterministic goal progress target reached."
                if complete and goal.status != "achieved":
                    goal.mark_achieved(day, goal_reason)

        return {
            "agent": speaker.name,
            "intent_id": intent.id,
            "intent_type": intent.intent_type,
            "status": intent.status,
            "progress": intent.progress,
            "progress_goal": intent.progress_goal,
            "reason": intent.completion_reason,
        }

    def get_conversation_progress_amount(
        self,
        intent: AgentIntent,
        location_id: str,
        listener: Agent,
        action: str,
        relationship_change: int,
        new_score: int,
        conversation_tags: list[str],
    ) -> int:
        tags = set(conversation_tags or [])

        if intent.target_agent and intent.target_agent != listener.name:
            return 0

        if intent.intent_type == "repair_relationship":
            if relationship_change > 0:
                return 1

            if action in {"apologize", "offer_help", "cooperate"}:
                return 1

            return 0

        if intent.intent_type == "build_friendship":
            if new_score >= 3:
                return intent.progress_goal

            if relationship_change > 0:
                return 1

            if action in {"compliment", "offer_help", "cooperate"}:
                return 1

            return 0

        if intent.intent_type == "investigate":
            investigation_tags = {
                "rumor",
                "market",
                "event",
                "town_arc",
                "knowledge",
                "rules",
                "learning",
                "business",
            }

            if action in {"ask_for_help", "share_rumor"}:
                return 1

            if tags & investigation_tags:
                return 1

            if intent.target_location and location_id == intent.target_location:
                return 1

            return 0

        if intent.intent_type == "socialize":
            if action in {"chat", "compliment", "offer_help", "ask_for_help", "cooperate"}:
                return 1

            if intent.target_location and location_id == intent.target_location:
                return 1

            return 0

        if intent.intent_type == "seek_work":
            work_tags = {
                "market",
                "business",
                "wealth",
                "work",
            }

            if action in {"ask_for_help", "cooperate", "offer_help"}:
                return 1

            if tags & work_tags:
                return 1

            if intent.target_location and location_id == intent.target_location:
                return 1

            return 0

        return 0

    def get_conversation_failure_reason(
        self,
        intent: AgentIntent,
        listener: Agent,
        action: str,
        relationship_change: int,
        new_score: int,
    ) -> str | None:
        negative_action = action in {
            "argue",
            "insult",
            "storm_off",
        }

        if intent.intent_type == "repair_relationship":
            if intent.target_agent == listener.name and negative_action:
                return "Repair attempt failed after a hostile interaction."

            if intent.target_agent == listener.name and new_score <= -7:
                return "Repair attempt failed because the relationship became deeply hostile."

        if intent.intent_type == "build_friendship":
            if intent.target_agent == listener.name and negative_action:
                return "Friendship attempt failed after a hostile interaction."

            if intent.target_agent == listener.name and relationship_change < 0:
                return "Friendship attempt failed because the relationship worsened."

        return None

    def get_success_reason(
        self,
        intent: AgentIntent,
        new_score: int,
    ) -> str | None:
        if intent.intent_type == "repair_relationship":
            if intent.progress >= intent.progress_goal and new_score >= 0:
                return "Relationship repair succeeded after positive follow-up."

            return None

        if intent.intent_type == "build_friendship":
            if new_score >= 3:
                return "Friendship goal succeeded because the relationship became friendly."

            if intent.progress >= intent.progress_goal:
                return "Friendship goal succeeded after enough positive interactions."

            return None

        if intent.progress >= intent.progress_goal:
            return f"Intent '{intent.intent_type}' reached its progress goal."

        return None
