import random

from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.simulation.dialogue_utils import has_rumor_marker


class ConversationPolicy:
    def __init__(
        self,
        actions: ActionSystem,
        recent_dialogues: list[str],
        recent_actions: list[str],
    ):
        self.actions = actions
        self.recent_dialogues = recent_dialogues
        self.recent_actions = recent_actions

    def remember_dialogue(self, conversation: str, limit: int = 50) -> None:
        normalized = conversation.strip().lower()

        if not normalized:
            return

        self.recent_dialogues.append(normalized)
        self.recent_dialogues = self.recent_dialogues[-limit:]

    def is_repeated_dialogue(self, conversation: str) -> bool:
        normalized = conversation.strip().lower()

        if not normalized:
            return False

        return normalized in self.recent_dialogues

    def get_non_repeated_fallback_dialogue(
        self,
        speaker: Agent,
        listener: Agent,
        relationship_label: str,
        location_id: str | None = None,
        suggested_action: str = "chat",
    ) -> str:
        activity = getattr(speaker, "current_activity", "this")
        occupation = getattr(speaker, "occupation", "resident")
        location_text = location_id or getattr(speaker, "location_id", "town")
        location_phrase = location_text.replace("_", " ")
        article = "an" if occupation[:1].lower() in "aeiou" else "a"

        candidates_by_action = {
            "compliment": [
                f"You handled the work near the {location_phrase} well.",
                f"You seem to understand this situation better than most people.",
                f"Your help with {activity.lower()} has been useful.",
            ],
            "offer_help": [
                f"I can help with {activity.lower()} if you need another pair of hands.",
                f"I can take care of part of this work at {location_text}.",
                f"I can help you sort through this before it gets harder.",
            ],
            "ask_for_help": [
                f"Could you give me advice about {activity.lower()}?",
                f"Do you know where I should start with this work at {location_text}?",
                f"Can you help me understand what people need here?",
            ],
            "cooperate": [
                f"We could work together on {activity.lower()} today.",
                f"If we coordinate at {location_text}, this will go smoother.",
                f"Let's split up the work and handle this together.",
            ],
            "share_rumor": [
                f"Someone said there may be more going on at {location_text}, but I am not sure it is true.",
                f"I heard an uncertain story about {location_text}, and people are starting to talk.",
                f"There is a rumor about this situation, but I do not know if I trust it yet.",
            ],
            "argue": [
                f"I disagree with how this is being handled at {location_text}.",
                f"That plan for {activity.lower()} does not make sense to me.",
                f"I think you are overlooking the real problem here.",
            ],
            "apologize": [
                f"I'm sorry about how I handled things earlier.",
                f"I should have been more careful with what I said.",
                f"I apologize if I made this harder than it needed to be.",
            ],
            "chat": [
                f"My work as {article} {occupation} has kept me busy near the {location_phrase}.",
                f"I have been focused on {activity.lower()} today.",
                f"{location_text.replace('_', ' ').title()} has been important to my plans today.",
                f"I keep noticing small changes while working on {activity.lower()}.",
                f"This part of town feels different when I am focused on {activity.lower()}.",
            ],
        }

        candidates = candidates_by_action.get(suggested_action, candidates_by_action["chat"])

        if relationship_label == "tense":
            candidates = [
                f"I am still not sure we agree about what is happening at {location_text}.",
                f"I would rather keep this focused on {activity.lower()}.",
            ] + candidates

        if relationship_label == "enemies":
            candidates = [
                f"Let's keep this short and focus on what needs to be done.",
                f"I do not want this conversation to become another argument.",
            ] + candidates

        for candidate in candidates:
            if not self.is_repeated_dialogue(candidate):
                return candidate

        return f"I am focused on {activity.lower()} right now."

    def remember_action(self, action: str, limit: int = 50) -> None:
        self.recent_actions.append(action)
        self.recent_actions = self.recent_actions[-limit:]

    def should_cap_action(self, action: str) -> bool:
        if action == "chat":
            return False

        recent_window = self.recent_actions[-20:]

        if len(recent_window) < 5:
            return False

        action_count = recent_window.count(action)
        action_rate = action_count / len(recent_window)

        if action == "share_rumor" and action_rate >= 0.20:
            return True

        if action == "compliment" and action_rate >= 0.15:
            return True

        non_chat_count = sum(
            1 for recent_action in recent_window
            if recent_action != "chat"
        )
        non_chat_rate = non_chat_count / len(recent_window)

        if action != "chat" and non_chat_rate >= 0.50:
            return True

        return False

    def choose_final_action_with_reason(
        self,
        conversation: str,
        parsed_action: str,
        conversation_tags: list[str],
        allowed_actions: list[str],
        inferred_action: str | None = None,
    ) -> tuple[str, str]:
        if inferred_action is None:
            inferred_action = self.actions.infer_action(
                conversation,
                conversation_tags,
            )

        if parsed_action == "share_rumor" and inferred_action == "chat":
            if has_rumor_marker(conversation):
                final_action = "share_rumor"
                reason = "parsed_rumor_with_marker"
            else:
                final_action = "chat"
                reason = "parsed_rumor_without_marker"

        elif inferred_action != "chat" and inferred_action in allowed_actions:
            final_action = inferred_action
            reason = "trusted_inferred_non_chat"

        elif parsed_action != "chat" and parsed_action in allowed_actions:
            final_action = parsed_action
            reason = "trusted_parsed_non_chat"

        elif parsed_action in allowed_actions:
            final_action = parsed_action
            reason = "used_parsed_action"

        else:
            final_action = "chat"
            reason = "fallback_chat_action_not_allowed"

        if self.should_cap_action(final_action):
            return "chat", f"capped_{final_action}"

        return final_action, reason

    def choose_final_action(
        self,
        conversation: str,
        parsed_action: str,
        conversation_tags: list[str],
        allowed_actions: list[str],
        inferred_action: str | None = None,
    ) -> str:
        action, _reason = self.choose_final_action_with_reason(
            conversation=conversation,
            parsed_action=parsed_action,
            conversation_tags=conversation_tags,
            allowed_actions=allowed_actions,
            inferred_action=inferred_action,
        )

        return action

    def choose_weighted_action(self, weights: dict[str, int]) -> str:
        weighted_actions = []

        for action, weight in weights.items():
            weighted_actions.extend([action] * weight)

        if not weighted_actions:
            return "chat"

        return random.choice(weighted_actions)