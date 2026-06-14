class ActionSystem:
    ACTION_EFFECTS = {
        "chat": 0,
        "compliment": 1,
        "apologize": 2,
        "offer_help": 1,
        "ask_for_help": 0,
        "argue": -1,
        "insult": -2,
        "storm_off": -2,
        "confess_feelings": 1,
        "share_rumor": -1,
    }

    ACTION_NEED_EFFECTS = {
        "chat": {"social": 1},
        "compliment": {"social": 2},
        "apologize": {"social": 2},
        "offer_help": {"social": 1},
        "ask_for_help": {"knowledge": 2},
        "argue": {},
        "insult": {},
        "storm_off": {},
        "confess_feelings": {"social": 3},
        "share_rumor": {"knowledge": 1},
    }
    def get_allowed_actions_for_relationship(self, relationship_score: int) -> list[str]:
        if relationship_score <= -6:
            return ["chat", "argue", "insult", "storm_off"]
    
        if relationship_score <= -3:
            return ["chat", "argue", "storm_off"]
    
        if relationship_score >= 6:
            return ["chat", "compliment", "offer_help", "ask_for_help", "confess_feelings"]
    
        if relationship_score >= 3:
            return ["chat", "compliment", "offer_help", "ask_for_help"]
    
        return ["chat", "compliment", "offer_help", "ask_for_help", "share_rumor"]
        
    def get_need_effects(self, action: str) -> dict[str, int]:
        return self.ACTION_NEED_EFFECTS.get(action, {})
    
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