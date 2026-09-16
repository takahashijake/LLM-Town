import re


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
        """Infer the action expressed by a spoken line.

        ``tags`` remains part of the public API for compatibility.  The action
        decision intentionally comes from the utterance itself: model-supplied
        tags are advisory and must not turn ordinary chat into a social act.
        """
        return self.infer_action_with_reason(conversation, tags)[0]

    def infer_action_with_reason(
        self,
        conversation: str,
        tags: list[str] | None = None,
    ) -> tuple[str, str]:
        """Return an inferred action and the deterministic matching rationale.

        Keep this ordering aligned with the Prompt 4 action-language contract.
        The first matching category wins, so a supported uncertain claim is
        still a rumor even if it also contains praise or a request.
        """
        text = conversation.lower()
        rumor_markers = (
            "rumor",
            "gossip",
            "suspicious",
            "shady",
            "secret",
            "mystery",
            "people are saying",
            "someone said",
            "unverified",
            "might be hiding",
            "might be unreliable",
            "from what i saw",
            "someone told me",
            "i heard",
            "word is",
            "i've been told",
        )
        marker = self._first_match(text, rumor_markers)
        if marker:
            return "share_rumor", f"rumor_marker:{marker}"
        # A speaker's own uncertainty is ordinary chat; Prompt 4 reserves
        # share_rumor for uncertain secondhand claims, which need provenance.
        # Apologies
        marker = self._first_match(text, (
            "sorry", "apologize", "i should have handled", "i should've handled",
            "my mistake", "i regret", "i was wrong",
        ))
        if marker:
            return "apologize", f"apology_marker:{marker}"
        marker = self._first_match(text, (
            "good job", "nice work", "you did well", "you seem to know a lot",
            "you're good at", "you are good at", "impressive", "great work",
            "well done", "you always know how", "you're really good",
            "you are really good", "that was thoughtful", "that was kind",
            "that was smart",
            "glad you came", "great to see", "good to see", "this is really helpful",
            "that helps a lot", "great job", "good work", "really come in handy",
            "come in handy", "organization skills", "organizing the volunteers",
            "you handled that really well", "you handled that well",
            "you've got a knack", "you have a knack",
            # Common direct praise variants emitted by instruction-following models.
            "you were excellent", "you are excellent", "you did an excellent job",
            "you've done a great", "you have done a great", "i admire",
            "so organized", "so well organized", "you keep them up",
        ))
        if marker:
            return "compliment", f"compliment_marker:{marker}"
        contribution_praise = re.search(
            r"\b(?:thanks|thank you) for (?:coming|helping|supporting|organizing|"
            r"handling|working|doing)\b|\bi appreciate (?:you|your)\b",
            text,
        )
        if contribution_praise:
            return "compliment", "compliment_pattern:appreciated_contribution"
        # Explicit offers of help. Recommendations and third-party staffing
        # observations are ordinary chat unless the speaker offers assistance.
        marker = self._first_match(text, (
            "i can help", "let me help", "we could help", "lend a hand",
            "pitching in", "i can show you", "i could show you", "i can give you a hand",
            "i could give you a hand", "i can lend a hand", "i could lend a hand",
            "i can help you", "i could help you", "let me help you", "let me take care of",
            "i can organize", "i could organize", "i can pitch in", "i could pitch in",
            "need any help", "do you need help", "want me to help", "would you like help",
            "could i help", "can i help", "need a hand", "want a hand",
            "would you like some help", "would you like me to help",
            "i'm happy to help", "i am happy to help", "i'd be happy to help",
            "i would be happy to help", "count on me", "i'm here to help",
        ))
        if marker:
            return "offer_help", f"offer_marker:{marker}"
        offered_task = re.search(
            r"\bwould you like me to (?:check|find|get|grab|bring|carry|sort|"
            r"organize|review|handle|take care of)\b",
            text,
        )
        if offered_task:
            return "offer_help", "offer_pattern:would_you_like_me_to_task"
        if re.search(r"\bcould you use (?:my|some|a)\b", text):
            return "offer_help", "offer_pattern:could_you_use_offered_resource"
        first_person_help = re.search(
            r"\b(let me|i(?:'ll| will| can| could))\b.{0,45}\bhelp out\b",
            text,
        )
        if first_person_help:
            return "offer_help", "offer_pattern:first_person_help_out"
    
        # Invitations and casual social questions
        marker = self._first_match(text, (
            "want to check it out", "want to check it out together", "want to join",
            "want to join me", "want to come", "would you like to join",
            "would you like to come", "would you want to join", "would you fancy joining",
            "would you be interested", "interested?", "interested in checking",
            "maybe we could go", "maybe we could grab", "we could check it out",
            "what do you think",
        ))
        if marker:
            return "chat", f"social_invitation:{marker}"
        marker = self._first_match(text, (
            "team up", "work together", "do this together", "pitch in together",
            "join forces", "coordinate", "let's work", "we could work",
            "we should work", "want to team", "want to pitch in",
            "coordinate our efforts", "coordinate our work", "work on this together",
            "plan this together", "let's tackle this together", "let us tackle this together",
            "let's handle this together", "let us handle this together", "let's collaborate",
            "let us collaborate", "we can tackle this together",
            "sort these supplies together", "organize these supplies together",
        ))
        if marker:
            return "cooperate", f"cooperation_marker:{marker}"
        concrete_joint_task = re.search(
            r"\b(sort|organize|repair|handle|finish|solve|clean)\b.{0,50}\btogether\b",
            text,
        )
        if concrete_joint_task:
            return "cooperate", f"cooperation_pattern:{concrete_joint_task.group(1)}_together"
        tentative_joint_task = re.search(
            r"\blet(?:'s| us) see if we can\b.{0,50}\b(sort|organize|repair|handle|finish|solve|clean|fix|find)\b",
            text,
        )
        if tentative_joint_task:
            return "cooperate", f"cooperation_pattern:lets_see_{tentative_joint_task.group(1)}"
        coordinated_split = re.search(
            r"\blet(?:'s| us)\b.{0,45}\b(split|divide)\b.{0,45}"
            r"\b(area|areas|work|task|tasks|coverage|ground)\b",
            text,
        )
        if coordinated_split:
            return "cooperate", f"cooperation_pattern:{coordinated_split.group(1)}_task"
        explicit_joint_plan = re.search(
            r"\b(?:let(?:'s| us)|how about we)\b.{0,30}"
            r"\b(split up|divide up|sort|organize|repair|handle|clean|cover|brainstorm)\b",
            text,
        )
        if explicit_joint_plan:
            return "cooperate", "cooperation_pattern:explicit_joint_plan"
        joint_task_question = re.search(
            r"\bdo you think we could\b.{0,35}"
            r"\b(find|check|sort|organize|repair|handle|clean|cover)\b",
            text,
        )
        if joint_task_question:
            return "cooperate", "cooperation_pattern:joint_task_question"
    
        # Genuine requests for help, advice, or information
        marker = self._first_match(text, (
            "can you help", "could you help", "would you help", "need your help",
            "i could use your help", "i could use some advice", "any advice",
            "do you know how", "can you show me", "could you show me",
            "do you know anything about", "do you know if", "would you know where",
            "any chance you could tell me", "i'm trying to find out",
            "could you give me advice", "can you give me advice", "what should i do",
            "where should i start", "can you explain", "could you explain",
            "can you teach me", "could you teach me", "would you mind helping", "i need advice",
            "i need help figuring", "would you be able to help", "could you assist",
            "can you assist", "i could really use", "i'm looking for advice",
            "i am looking for advice", "please help me", "do you have any contacts",
            "can you tell me", "could you tell me", "would you tell me",
            "could you recommend", "can you recommend", "would you recommend",
            "could use some help", "if you could show me", "do you have any tips",
            "could you grab me", "can you grab me", "do you have any extra",
            "could you point me", "can you point me", "could you check if",
            "can you check if",
        ))
        if marker:
            return "ask_for_help", f"request_marker:{marker}"
        if re.search(r"\bcould you (?:maybe |perhaps )?point me\b", text):
            return "ask_for_help", "request_pattern:point_me_to_resource"
        direct_assistance_request = re.search(
            r"\b(?:can|could|would) you (?:please )?"
            r"(?:check|show|explain|teach|tell|recommend|grab|bring|find|review|"
            r"look|walk|help|use)\b",
            text,
        )
        if direct_assistance_request:
            return "ask_for_help", "request_pattern:direct_assistance"
        polite_assistance_request = re.search(
            r"\bwould you mind (?:showing|checking|explaining|teaching|telling|"
            r"recommending|grabbing|bringing|finding|reviewing|looking|walking|"
            r"helping|using)\b",
            text,
        )
        if polite_assistance_request:
            return "ask_for_help", "request_pattern:polite_assistance"
        if re.search(r"\bcould you (?:give|share) me (?:some )?tips\b", text):
            return "ask_for_help", "request_pattern:tips"
        if re.search(r"\bdo you know where\b", text):
            return "ask_for_help", "request_pattern:resource_location"
    
        # Romantic confession
        marker = self._first_match(text, (
            "i love you", "i have feelings for you", "i'm in love with you",
            "romantic feelings",
        ))
        if marker:
            return "confess_feelings", f"confession_marker:{marker}"
    
        # Rumors / gossip
        # Arguments
        marker = self._first_match(text, (
            "why are you", "argue", "you are wrong", "you're wrong",
            "that makes no sense", "that does not make sense", "i disagree",
            "i do not agree", "i don't agree", "you handled that poorly",
            "you made this harder", "i think you're mistaken", "i think you are mistaken",
            "that is not acceptable", "that's not acceptable", "you should not have",
            "i have an issue with", "my issue with your",
        ))
        if marker:
            return "argue", f"argument_marker:{marker}"
    
        # Insults
        marker = self._first_match(text, ("stupid", "idiot"))
        if marker:
            return "insult", f"insult_marker:{marker}"
    
        # Leaving conversation
        marker = self._first_match(text, ("bye", "done talking"))
        if marker:
            return "storm_off", f"departure_marker:{marker}"
    
        return "chat", "no_action_language"

    def validate_action_semantics(
        self,
        action: str,
        conversation: str,
    ) -> tuple[bool, str]:
        """Conservatively validate a model-supplied non-chat action label.

        Deterministic inference is deliberately narrower than generation.  A
        parsed label may fill a lexical gap only when the utterance still
        contains language that this policy recognizes as that exact social
        move.  This prevents ordinary questions and positive observations
        from acquiring help/cooperation effects merely because the model
        emitted an ambitious label.
        """
        if action == "chat":
            return True, "chat_requires_no_special_language"
        inferred, reason = self.infer_action_with_reason(conversation, [])
        if inferred == action:
            return True, reason
        return False, f"semantic_validator_inferred_{inferred}"

    @staticmethod
    def _first_match(text: str, markers: tuple[str, ...]) -> str | None:
        return next((marker for marker in markers if marker in text), None)

    def get_relationship_effect(self, action: str) -> int:
        return self.ACTION_EFFECTS.get(action, 0)
