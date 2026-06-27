import random

from src.agents.agent import Agent
from src.behavior.activity import Activity


class ActivityPlanner:
    def create_intent_activity(self, current_intent) -> Activity:
        return Activity(
            id=f"intent_{current_intent.intent_type}",
            name=f"Work on intent: {current_intent.intent_type}",
            location_id=current_intent.target_location,
            reason=current_intent.description,
            tags=self.get_intent_activity_tags(current_intent),
        )
    
    def should_prioritize_intent_before_event(self, current_intent) -> bool:
        if not current_intent:
            return False

        priority_by_intent = {
            "repair_relationship": 0.55,
            "build_friendship": 0.45,
            "socialize": 0.45,
            "investigate": 0.30,
            "seek_work": 0.25,
        }

        probability = priority_by_intent.get(current_intent.intent_type, 0.30)

        return random.random() < probability
    
    def get_intent_activity_probability(self, intent) -> float:
        if not intent:
            return 0.0

        probabilities = {
            "investigate": 0.40,
            "seek_work": 0.40,
            "socialize": 0.45,
            "build_friendship": 0.35,
            "repair_relationship": 0.35,
        }

        return probabilities.get(intent.intent_type, 0.40)
    def get_intent_activity_tags(self, intent) -> list[str]:
        base_tags = ["intent", intent.intent_type]

        tags_by_intent = {
            "investigate": ["knowledge", "learning"],
            "seek_work": ["wealth", "business", "market"],
            "socialize": ["social", "relationship"],
            "build_friendship": ["social", "relationship"],
            "repair_relationship": ["social", "relationship"],
        }

        return base_tags + tags_by_intent.get(intent.intent_type, [])
        
    def choose_activity(
        self,
        agent: Agent,
        location_ids: list[str],
        current_day: int,
        hour: int,
        daily_event=None,
        current_intent=None,
    ) -> Activity:
        agent.initialize_needs()

        if (
            current_intent
            and current_intent.target_location
            and current_intent.target_location in location_ids
            and self.should_prioritize_intent_before_event(current_intent)
        ):
            return self.create_intent_activity(current_intent)

        # Sometimes attend the daily event if it is relevant.
        if daily_event and self.should_attend_daily_event(agent, daily_event):
            return Activity(
                id="attend_event",
                name=f"Attend {daily_event.name}",
                location_id=daily_event.location_id,
                reason=f"{agent.name} is interested in today's event: {daily_event.name}.",
                tags=["event", daily_event.id] + daily_event.tags,
            )

        if current_intent and current_intent.target_location:
            follow_probability = self.get_intent_activity_probability(current_intent)

            if (
                current_intent.target_location in location_ids
                and random.random() < follow_probability
            ):
                return self.create_intent_activity(current_intent)

        # Otherwise choose based on goals, occupation, and needs.
        candidates = self.get_candidate_activities(agent, location_ids)

        if not candidates:
            fallback_location = agent.choose_location_by_need(location_ids)
            return Activity(
                id="wander",
                name="Wander around town",
                location_id=fallback_location,
                reason=f"{agent.name} is choosing a location based on current needs.",
                tags=["wander", agent.get_primary_need()],
            )

        return random.choice(candidates)

    def should_attend_daily_event(self, agent: Agent, daily_event) -> bool:
        text = " ".join(
            [
                agent.occupation,
                agent.personality,
                " ".join(agent.goals),
                agent.get_primary_need(),
            ]
        ).lower()

        event_text = " ".join(
            [
                daily_event.id,
                daily_event.name,
                daily_event.description,
                " ".join(daily_event.tags),
            ]
        ).lower()

        relevance_keywords = {
            "local journalist": ["debate", "town hall", "rumor", "fundraiser", "poetry", "book", "lost"],
            "accountant": ["market", "merchant", "inspection", "supplier", "fundraiser", "business"],
            "community organizer": ["volunteer", "cleanup", "school", "fundraiser", "town hall", "repair"],
            "merchant": ["market", "supplier", "inspection", "bakery", "business", "fair"],
        }

        occupation_keywords = relevance_keywords.get(agent.occupation.lower(), [])

        is_relevant = any(keyword in event_text for keyword in occupation_keywords)

        if is_relevant:
            return random.random() < 0.75

        # Still allow some general town participation.
        return random.random() < 0.20

    def get_candidate_activities(
        self,
        agent: Agent,
        location_ids: list[str],
    ) -> list[Activity]:
        text = " ".join(
            [
                agent.occupation,
                agent.personality,
                " ".join(agent.goals),
                agent.get_primary_need(),
            ]
        ).lower()

        candidates = []

        def add_activity(
            activity_id: str,
            name: str,
            location_id: str,
            reason: str,
            tags: list[str],
        ) -> None:
            if location_id in location_ids:
                candidates.append(
                    Activity(
                        id=activity_id,
                        name=name,
                        location_id=location_id,
                        reason=reason,
                        tags=tags,
                    )
                )

        # Need-based activities
        primary_need = agent.get_primary_need()

        if primary_need == "social":
            add_activity(
                "socialize",
                "Socialize with townspeople",
                "cafe",
                f"{agent.name} wants more social contact.",
                ["social", "relationship"],
            )
            add_activity(
                "public_socialize",
                "Talk with people in the town square",
                "town_square",
                f"{agent.name} wants to be around people.",
                ["social", "town_life"],
            )

        if primary_need == "wealth":
            add_activity(
                "seek_work",
                "Look for work or business opportunities",
                "market",
                f"{agent.name} wants to improve wealth.",
                ["wealth", "business"],
            )

        if primary_need == "knowledge":
            add_activity(
                "learn",
                "Look for information",
                "library",
                f"{agent.name} wants to learn something useful.",
                ["knowledge", "learning"],
            )

        # Occupation / goal-based activities
        if "journalist" in text or "secrets" in text:
            add_activity(
                "investigate_story",
                "Investigate a possible story",
                "town_square",
                f"{agent.name} is looking for town stories or rumors.",
                ["journalism", "rumor", "knowledge"],
            )
            add_activity(
                "check_records",
                "Check records for leads",
                "library",
                f"{agent.name} is looking for background information.",
                ["journalism", "learning"],
            )

        if "accountant" in text or "reliable allies" in text:
            add_activity(
                "review_records",
                "Review records and numbers",
                "library",
                f"{agent.name} wants reliable information before trusting others.",
                ["accounting", "knowledge"],
            )
            add_activity(
                "observe_market",
                "Observe business activity",
                "market",
                f"{agent.name} is watching for financial opportunities or risks.",
                ["accounting", "business"],
            )

        if "community organizer" in text or "help the town" in text:
            add_activity(
                "organize_community",
                "Organize community support",
                "town_square",
                f"{agent.name} wants to help the town community.",
                ["community", "volunteer", "social"],
            )
            add_activity(
                "meet_residents",
                "Meet residents",
                "cafe",
                f"{agent.name} wants to build goodwill with residents.",
                ["community", "social"],
            )

        if "merchant" in text or "business opportunities" in text:
            add_activity(
                "pursue_business",
                "Look for business opportunities",
                "market",
                f"{agent.name} wants to find business opportunities.",
                ["business", "market", "wealth"],
            )
            add_activity(
                "network",
                "Network with townspeople",
                "cafe",
                f"{agent.name} wants to grow influence through relationships.",
                ["business", "social"],
            )

        return candidates