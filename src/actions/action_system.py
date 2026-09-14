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
        "cooperate": 1, 
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
        "cooperate": {"social": 2},
    }
    # Reputation describes perceived conduct, not pair affinity. Ordinary chat,
    # requests, and rumor speech have no automatic reputation effect.
    REPUTATION_EFFECTS = {
        "compliment": {"helpfulness": 0.25},
        "apologize": {"trustworthiness": 0.40, "hostility": -0.40},
        "offer_help": {"helpfulness": 1.0},
        "cooperate": {"cooperativeness": 1.0, "helpfulness": 0.25},
        "argue": {"hostility": 0.35},
        "insult": {"hostility": 1.0, "trustworthiness": -0.25},
        "storm_off": {"hostility": 0.60, "cooperativeness": -0.50},
    }
    def get_allowed_actions_for_relationship(self, relationship_score: int) -> list[str]:
        if relationship_score <= -7:
            return [
                "chat",
                "argue",
                "insult",
                "storm_off",
                "apologize",
            ]
    
        if relationship_score <= -3:
            return [
                "chat",
                "argue",
                "storm_off",
                "apologize",
                "share_rumor",
            ]
    
        if relationship_score >= 7:
            return [
                "chat",
                "compliment",
                "offer_help",
                "ask_for_help",
                "cooperate",
                "apologize",
                "argue",
            ]
    
        if relationship_score >= 3:
            return [
                "chat",
                "compliment",
                "offer_help",
                "ask_for_help",
                "cooperate",
                "apologize",
                "argue",
                "share_rumor",
            ]
    
        return [
            "chat",
            "compliment",
            "offer_help",
            "ask_for_help",
            "cooperate",
            "share_rumor",
            "argue",
        ]
        
    def get_need_effects(self, action: str) -> dict[str, int]:
        return self.ACTION_NEED_EFFECTS.get(action, {})

    def get_reputation_effects(self, action: str) -> dict[str, float]:
        return dict(self.REPUTATION_EFFECTS.get(action, {}))
    
    def infer_action(self, conversation: str, tags: list[str]) -> str:
        text = conversation.lower()
        rumor_markers = [
            "rumor",
            "gossip",
            "suspicious",
            "shady",
            "secret",
            "mystery",
            "not sure",
            "people are saying",
            "someone said",
            "unverified",
            "might be hiding",
            "might be unreliable",
            "from what i saw",
            "someone told me",
        ]
        if any(marker in text for marker in rumor_markers):
            return "share_rumor"
        # Apologies
        if (
            "sorry" in text
            or "apologize" in text
            or "i should have handled" in text
            or "i should've handled" in text
            or "my mistake" in text
            or "i regret" in text
            or "i was wrong" in text
        ):
            return "apologize"
        if (
            "rumor" in text
            or "gossip" in text
            or "suspicious" in text
            or "secretive" in text
            or "strange" in text
            or "i heard something" in text
            or "people are saying" in text
            or "someone said" in text
            or "not sure it's true" in text
            or "not sure it is true" in text
            or "might be unreliable" in text
            or "seems unreliable" in text
            or "unverified" in text
        ):
            return "share_rumor"
        if (
            "good job" in text
            or "nice work" in text
            or "you did well" in text
            or "you seem to know a lot" in text
            or "you're good at" in text
            or "you are good at" in text
            or "impressive" in text
            or "great work" in text
            or "well done" in text
            or "you always know how" in text
            or "you're really good" in text
            or "you are really good" in text
            or "that was thoughtful" in text
            or "that was kind" in text
            or "that was smart" in text
            or "thanks for" in text
            or "thank you for" in text
            or "i appreciate" in text
            or "glad you came" in text
            or "great to see" in text
            or "good to see" in text
            or "this is really helpful" in text
            or "that helps a lot" in text
            or "great job" in text
            or "good work" in text
            or "really come in handy" in text
            or "come in handy" in text
            or "organization skills" in text
            or "organizing the volunteers" in text
        ):
            return "compliment"
        # Explicit offers of help. Recommendations and third-party staffing
        # observations are ordinary chat unless the speaker offers assistance.
        if (
            "i can help" in text
            or "let me help" in text
            or "we could help" in text
            or "lend a hand" in text
            or "pitching in" in text
            or "i can show you" in text
            or "i could show you" in text
            or "i can give you a hand" in text
            or "i could give you a hand" in text
            or "i can lend a hand" in text
            or "i could lend a hand" in text
            or "i can help you" in text
            or "i could help you" in text
            or "let me help you" in text
            or "let me take care of" in text
            or "i can organize" in text
            or "i could organize" in text
            or "i can pitch in" in text
            or "i could pitch in" in text
            or "need any help" in text
            or "do you need help" in text
            or "want me to help" in text
            or "would you like help" in text
            or "could i help" in text
            or "can i help" in text
            or "need a hand" in text
            or "want a hand" in text
        ):
            return "offer_help"
    
        # Invitations and casual social questions
        if (
            "want to check it out" in text
            or "want to check it out together" in text
            or "want to join" in text
            or "want to join me" in text
            or "want to come" in text
            or "would you like to join" in text
            or "would you like to come" in text
            or "would you want to join" in text
            or "would you fancy joining" in text
            or "would you be interested" in text
            or "interested?" in text
            or "interested in checking" in text
            or "maybe we could go" in text
            or "maybe we could grab" in text
            or "we could check it out" in text
            or "what do you think" in text
        ):
            return "chat"
        if (
            "team up" in text
            or "work together" in text
            or "do this together" in text
            or "pitch in together" in text
            or "join forces" in text
            or "coordinate" in text
            or "let's work" in text
            or "we could work" in text
            or "we should work" in text
            or "want to team" in text
            or "want to pitch in" in text
            or "coordinate our efforts" in text
            or "coordinate our work" in text
            or "work on this together" in text
            or "plan this together" in text
        ):
            return "cooperate"
    
        # Genuine requests for help, advice, or information
        if (
            "can you help" in text
            or "could you help" in text
            or "would you help" in text
            or "need your help" in text
            or "i could use your help" in text
            or "i could use some advice" in text
            or "any advice" in text
            or "do you know how" in text
            or "can you show me" in text
            or "could you show me" in text
            or "do you know anything about" in text
            or "do you know if" in text
            or "would you know where" in text
            or "any chance you could tell me" in text
            or "i'm trying to find out" in text
            or "could you give me advice" in text
            or "can you give me advice" in text
            or "what should i do" in text
            or "where should i start" in text
            or "can you explain" in text
            or "could you explain" in text
            or "can you teach me" in text
            or "could you teach me" in text
            or "would you mind helping" in text
            or "i need advice" in text
            or "i need help figuring" in text
        ):
            return "ask_for_help"
    
        # Romantic confession
        if (
            "i love you" in text
            or "i have feelings for you" in text
            or "i'm in love with you" in text
            or "romantic feelings" in text
        ):
            return "confess_feelings"
    
        # Rumors / gossip
        if (
            "rumor" in text
            or "gossip" in text
            or "suspicious" in text
            or "secretive" in text
            or "strange" in text
        ):
            return "share_rumor"
    
        # Arguments
        if (
            "why are you" in text
            or "argue" in text
            or "issue" in text
            or "you are wrong" in text
            or "you're wrong" in text
            or "that makes no sense" in text
            or "that does not make sense" in text
            or "i disagree" in text
            or "i do not agree" in text
            or "i don't agree" in text
            or "you handled that poorly" in text
            or "you made this harder" in text
        ):
            return "argue"
    
        # Insults
        if "stupid" in text or "idiot" in text:
            return "insult"
    
        # Leaving conversation
        if "bye" in text or "done talking" in text:
            return "storm_off"
    
        return "chat"

    def get_relationship_effect(self, action: str) -> int:
        return self.ACTION_EFFECTS.get(action, 0)
