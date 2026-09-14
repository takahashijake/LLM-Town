class SocialBehaviorPolicy:
    POSITIVE_ACTIONS = {
        "compliment",
        "offer_help",
        "cooperate",
        "confess_feelings",
    }

    NEGATIVE_ACTIONS = {
        "argue",
        "insult",
        "storm_off",
        "share_rumor",
    }

    def get_base_action_weights(
        self,
        relationship_label: str,
    ) -> dict[str, int]:
        if relationship_label in ["tense", "enemies"]:
            return {
                "chat": 8,
                "apologize": 3,
                "argue": 2,
                "storm_off": 1,
                "insult": 1,
            }

        if relationship_label in ["friendly", "close friends"]:
            return {
                "chat": 7,
                "compliment": 2,
                "cooperate": 1,
                "offer_help": 2,
                "ask_for_help": 1,
                "confess_feelings": 1,
            }

        return {
            "chat": 8,
            "cooperate": 1,
            "offer_help": 2,
            "ask_for_help": 2,
            "compliment": 1,
            "share_rumor": 1,
            "argue": 1,
        }

    def score_relationship_history(self, recent_events) -> int:
        score = 0

        for event in recent_events or []:
            score += event.relationship_change

            if event.action in self.POSITIVE_ACTIONS:
                score += 1

            if event.action in self.NEGATIVE_ACTIONS:
                score -= 1

        return score

    def get_action_weights(
        self,
        allowed_actions: list[str],
        relationship_label: str,
        recent_events=None,
    ) -> dict[str, int]:
        allowed = set(allowed_actions)

        base_weights = self.get_base_action_weights(relationship_label)

        weights = {
            action: weight
            for action, weight in base_weights.items()
            if action in allowed
        }

        if not weights:
            return {"chat": 1}

        history_score = self.score_relationship_history(recent_events)

        if history_score >= 2:
            self._increase(weights, allowed, "compliment", 1)
            self._increase(weights, allowed, "offer_help", 1)
            self._increase(weights, allowed, "cooperate", 1)
            self._increase(weights, allowed, "ask_for_help", 1)
            self._decrease(weights, "argue", 1)

        elif history_score <= -2:
            self._increase(weights, allowed, "apologize", 3)
            self._increase(weights, allowed, "chat", 2)
            self._increase(weights, allowed, "argue", 1)
            self._decrease(weights, "compliment", 2)
            self._decrease(weights, "offer_help", 1)
            self._decrease(weights, "cooperate", 1)

        return {
            action: max(1, weight)
            for action, weight in weights.items()
            if action in allowed and weight > 0
        }

    def adjust_action_weights_for_reputation(
        self,
        weights: dict[str, int],
        reputation_beliefs: dict,
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Apply small, interpretable changes without replacing relationships."""
        adjusted = dict(weights)
        deltas: dict[str, int] = {}

        def supported_score(dimension: str) -> float:
            belief = reputation_beliefs.get(dimension)
            if belief is None or getattr(belief, "confidence", 0.0) < 0.35:
                return 0.0
            return float(getattr(belief, "score", 0.0))

        trust = supported_score("trustworthiness")
        helpfulness = supported_score("helpfulness")
        cooperation = supported_score("cooperativeness")
        hostility = supported_score("hostility")

        def change(action: str, amount: int) -> None:
            if action not in adjusted or amount == 0:
                return
            old = adjusted[action]
            adjusted[action] = max(1, old + amount)
            actual = adjusted[action] - old
            if actual:
                deltas[action] = deltas.get(action, 0) + actual

        if trust >= 1.5:
            change("cooperate", 1)
        elif trust <= -1.5:
            change("cooperate", -1)
            change("ask_for_help", -1)

        if helpfulness >= 1.5:
            change("ask_for_help", 1)
        elif helpfulness <= -1.5:
            change("ask_for_help", -1)

        if cooperation >= 1.5:
            change("cooperate", 1)
        elif cooperation <= -1.5:
            change("cooperate", -1)

        if hostility >= 1.5:
            change("chat", 1)
            change("offer_help", -1)
            change("cooperate", -1)
            change("ask_for_help", -1)
        elif hostility <= -1.5:
            change("cooperate", 1)

        return adjusted, deltas

    def _increase(
        self,
        weights: dict[str, int],
        allowed: set[str],
        action: str,
        amount: int,
    ) -> None:
        if action not in allowed:
            return

        weights[action] = weights.get(action, 0) + amount

    def _decrease(
        self,
        weights: dict[str, int],
        action: str,
        amount: int,
    ) -> None:
        if action not in weights:
            return

        weights[action] = max(1, weights[action] - amount)
