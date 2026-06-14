import random

from src.agents.agent import Agent
from src.behavior.activity import Activity


class ActivityPlanner:
    def choose_activity(
        self,
        agent: Agent,
        location_ids: list[str],
        current_day: int,
        hour: int,
        daily_event=None,
    ) -> Activity:
        agent.initialize_needs()

        # Sometimes attend the daily event if it is relevant.
        if daily_event and self.should_attend_daily_event(agent, daily_event):
            return Activity(
                id="attend_event",
                name=f"Attend {daily_event.name}",
                location_id=daily_event.location_id,
                reason=f"{agent.name} is interested in today's event: {daily_event.name}.",
                tags=["event", daily_event.id] + daily_event.tags,
            )

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