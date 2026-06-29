from src.agents.agent import Agent
from src.agents.intent import AgentIntent
from src.behavior.intent_planner import IntentPlanner


class IntentSystem:
    def __init__(
        self,
        intent_planner: IntentPlanner,
        agent_intents: dict[str, AgentIntent],
        intent_history: list[AgentIntent] | None = None,
    ):
        self.intent_planner = intent_planner
        self.agent_intents = agent_intents
        self.intent_history = intent_history if intent_history is not None else []

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
        intent_type_counts = {}

        for agent_name, intent in list(self.agent_intents.items()):
            if intent.status == "active" and intent.is_expired(current_day):
                intent.mark_failed(
                    day=current_day,
                    reason="Intent expired before reaching enough progress.",
                    status="expired",
                )
                self.archive_intent(intent)
                self.agent_intents.pop(agent_name, None)
                continue

            if intent.is_active(current_day):
                intent_type_counts[intent.intent_type] = (
                    intent_type_counts.get(intent.intent_type, 0) + 1
                )

        for agent in agents:
            current_intent = self.agent_intents.get(agent.name)

            if current_intent and current_intent.is_active(current_day):
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

        success_reason = self.get_success_reason(
            intent=intent,
            new_score=new_score,
        )

        if success_reason:
            intent.mark_succeeded(day=day, reason=success_reason)
            self.archive_intent(intent)
            self.agent_intents.pop(speaker.name, None)

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