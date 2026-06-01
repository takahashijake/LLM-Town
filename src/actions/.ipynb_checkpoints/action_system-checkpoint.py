class ActionSystem:
    ACTION_EFFECTS = {
        "chat": 0,
        "compliment": 0,
        "apologize": 1,
        "offer_help": 0,
        "ask_for_help": 0,
        "argue": 0,
        "insult": -1,
        "storm_off": -1,
        "confess_feelings": 1,
        "share_rumor": 0,
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
            
        return "chat"

    def get_relationship_effect(self, action: str) -> int:
        return self.ACTION_EFFECTS.get(action, 0)