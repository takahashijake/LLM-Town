from src.agents.agent import Agent
from src.agents.intent import AgentIntent
from src.behavior.intent_planner import IntentPlanner


class IntentSystem:
    def __init__(
        self,
        intent_planner: IntentPlanner,
        agent_intents: dict[str, AgentIntent],
    ):
        self.intent_planner = intent_planner
        self.agent_intents = agent_intents

    def get_intent_listener_weight_bonus(
        self,
        speaker: Agent,
        listener: Agent,
    ) -> int:
        intent = self.agent_intents.get(speaker.name)

        if not intent:
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

        for intent in self.agent_intents.values():
            if not intent.is_expired(current_day):
                intent_type_counts[intent.intent_type] = (
                    intent_type_counts.get(intent.intent_type, 0) + 1
                )

        for agent in agents:
            current_intent = self.agent_intents.get(agent.name)

            if current_intent and not current_intent.is_expired(current_day):
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

        if not intent:
            return "No active intent."

        return intent.description

    def adjust_action_weights_for_intent(
        self,
        weights: dict[str, int],
        intent: AgentIntent | None,
        listener_name: str,
    ) -> dict[str, int]:
        adjusted = dict(weights)

        if not intent:
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