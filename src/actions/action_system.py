class ActionSystem:
    ACTION_EFFECTS = {
        "chat": 0,
        "compliment": 1,
        "apologize": 1,
        "offer_help": 1,
        "ask_for_help": 0,
        "argue": -1,
        "insult": -2,
        "storm_off": -1,
        "confess_feelings": 2,
        "share_rumor": -1,
    }

    def infer_action(self, conversation: str, tags: list[str]) -> str:
        text = conversation.lower()

        if "sorry" in text or "apologize" in text:
            return "apologize"

        if "help" in text:
            return "offer_help"

        if "love" in text or "feelings" in text:
            return "confess_feelings"

        if "rumor" in text or "trust" in text or "suspicious" in text:
            return "share_rumor"

        if "why are you" in text or "argue" in text or "issue" in text:
            return "argue"

        if "stupid" in text or "idiot" in text:
            return "insult"

        if "bye" in text or "done talking" in text:
            return "storm_off"

        if "friendly" in tags or "close friends" in tags:
            return "compliment"

        return "chat"

    def get_relationship_effect(self, action: str) -> int:
        return self.ACTION_EFFECTS.get(action, 0)