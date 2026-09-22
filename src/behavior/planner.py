import random
from dataclasses import asdict, dataclass

from src.agents.agent import Agent
from src.behavior.activity import Activity


@dataclass(frozen=True)
class CommitmentDecision:
    commitment_id: str
    selected: bool
    decision_type: str
    urgency: float
    feasibility: str
    pressure: float
    competing_priority: float
    stochastic_adjustment: float
    attempted_in_window: bool
    reason: str


class ActivityPlanner:
    """Compare inspectable bounded priorities; randomness only breaks close calls."""

    COMMITMENT_PRESSURE_BASE = 0.20
    COMMITMENT_URGENCY_WEIGHT = 0.60
    COMMITMENT_DUE_BONUS = 0.15
    COMMITMENT_ATTEMPT_PENALTY = 0.18
    COMMITMENT_PREPARATION_PENALTY = 0.12
    # A visible lapse/resolve term preserves occasional failures without making
    # the commitment itself a Bernoulli gate. Due pressure still dominates
    # ordinary activity through most of this bounded range.
    DECISION_JITTER = 0.75

    @staticmethod
    def _goal_texts(agent) -> list[str]:
        if hasattr(agent, "goal_descriptions"):
            return agent.goal_descriptions()
        return [str(goal) for goal in getattr(agent, "goals", [])]

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
            "build_friendship": 0.40,
            "socialize": 0.35,
            "investigate": 0.20,
            "seek_work": 0.18,
        }

        probability = priority_by_intent.get(current_intent.intent_type, 0.25)

        return random.random() < probability
    
    def get_intent_activity_probability(self, intent) -> float:
        if not intent:
            return 0.0

        probabilities = {
            "investigate": 0.28,
            "seek_work": 0.30,
            "socialize": 0.35,
            "build_friendship": 0.30,
            "repair_relationship": 0.35,
        }

        return probabilities.get(intent.intent_type, 0.30)
        
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
        commitment_opportunities=None,
    ) -> Activity:
        agent.initialize_needs()
        deferred_commitment_decision = None

        feasible_commitments = [
            item for item in (commitment_opportunities or [])
            if item.feasibility == "feasible"
        ]
        preparable_commitments = [
            item for item in (commitment_opportunities or [])
            if item.feasibility == "temporarily_infeasible" and item.preparation_action_id
        ]
        actionable = feasible_commitments + preparable_commitments
        if actionable:
            decisions = [self.commitment_decision(agent, item, current_intent, daily_event)
                         for item in actionable]
            decision, opportunity = max(
                zip(decisions, actionable),
                key=lambda pair: (pair[0].pressure + pair[0].stochastic_adjustment,
                                  pair[1].urgency, pair[1].commitment_id),
            )
            if decision.selected:
                if decision.decision_type == "prepare":
                    return self.create_commitment_preparation_activity(agent, opportunity, decision)
                return self.create_commitment_activity(agent, opportunity, decision)
            deferred_commitment_decision = asdict(decision)

        if (
            current_intent
            and current_intent.target_location
            and current_intent.target_location in location_ids
            and self.should_prioritize_intent_before_event(current_intent)
        ):
            activity = self.create_intent_activity(current_intent)
            activity.commitment_decision = deferred_commitment_decision
            return activity

        # Sometimes attend the daily event if it is relevant.
        if daily_event and self.should_attend_daily_event(agent, daily_event):
            activity = Activity(
                id="attend_event",
                name=f"Attend {daily_event.name}",
                location_id=daily_event.location_id,
                reason=f"{agent.name} is interested in today's event: {daily_event.name}.",
                tags=["event", daily_event.id] + daily_event.tags,
            )
            activity.commitment_decision = deferred_commitment_decision
            return activity

        if current_intent and current_intent.target_location:
            follow_probability = self.get_intent_activity_probability(current_intent)

            if (
                current_intent.target_location in location_ids
                and random.random() < follow_probability
            ):
                activity = self.create_intent_activity(current_intent)
                activity.commitment_decision = deferred_commitment_decision
                return activity

        # Otherwise choose based on goals, occupation, and needs.
        candidates = self.get_candidate_activities(agent, location_ids)

        if not candidates:
            fallback_location = agent.choose_location_by_need(location_ids)
            activity = Activity(
                id="wander",
                name="Wander around town",
                location_id=fallback_location,
                reason=f"{agent.name} is choosing a location based on current needs.",
                tags=["wander", agent.get_primary_need()],
            )
            activity.commitment_decision = deferred_commitment_decision
            return activity

        activity = random.choice(candidates)
        activity.commitment_decision = deferred_commitment_decision
        return activity

    def _competing_priority(self, agent, current_intent, daily_event) -> tuple[float, str]:
        values = [(0.18, "ordinary_activity")]
        if current_intent:
            values.append((self.get_intent_activity_probability(current_intent) + 0.20,
                           f"intent:{current_intent.intent_type}"))
        if daily_event:
            values.append((0.52, f"event:{daily_event.id}"))
        agent.initialize_needs()
        primary = agent.get_primary_need()
        need_value = float(agent.needs.get(primary, 50))
        values.append((min(0.90, 0.25 + max(0.0, 50.0 - need_value) / 60.0),
                       f"need:{primary}"))
        return max(values, key=lambda value: value[0])

    def commitment_decision(self, agent, opportunity, current_intent=None,
                            daily_event=None) -> CommitmentDecision:
        preparation = opportunity.feasibility != "feasible"
        pressure = (self.COMMITMENT_PRESSURE_BASE
                    + opportunity.urgency * self.COMMITMENT_URGENCY_WEIGHT
                    + (self.COMMITMENT_DUE_BONUS if opportunity.urgency >= 1.0 else 0.0)
                    - (self.COMMITMENT_ATTEMPT_PENALTY if opportunity.attempted_in_window else 0.0)
                    - (self.COMMITMENT_PREPARATION_PENALTY if preparation else 0.0))
        pressure = max(0.0, min(1.0, pressure))
        competing, competitor = self._competing_priority(agent, current_intent, daily_event)
        jitter = (0.5 - random.random()) * 2.0 * self.DECISION_JITTER
        selected = pressure + jitter >= competing
        reason = (f"commitment pressure {pressure:.3f} plus bounded adjustment {jitter:.3f} "
                  f"{'met' if selected else 'did not meet'} competing {competitor} "
                  f"priority {competing:.3f}")
        return CommitmentDecision(
            opportunity.commitment_id, selected, "prepare" if preparation else "execute",
            opportunity.urgency, opportunity.feasibility, pressure, competing, jitter,
            opportunity.attempted_in_window, reason,
        )

    def create_commitment_activity(self, agent: Agent, opportunity,
                                   decision: CommitmentDecision | None = None) -> Activity:
        names = {
            "help": "Help fulfill an agreed task",
            "meet": "Attend an agreed meeting",
            "transfer": "Deliver a promised resource",
        }
        return Activity(
            id=f"commitment_{opportunity.commitment_type}",
            name=names[opportunity.commitment_type],
            location_id=opportunity.target_location or agent.location_id,
            reason=(
                f"{agent.name} is acting on accepted commitment "
                f"{opportunity.commitment_id}."
            ),
            tags=["commitment", opportunity.commitment_type],
            source_commitment_id=opportunity.commitment_id,
            commitment_priority=(decision.pressure if decision else opportunity.urgency),
            commitment_decision=asdict(decision) if decision else None,
        )

    def create_commitment_preparation_activity(self, agent, opportunity,
                                               decision: CommitmentDecision) -> Activity:
        return Activity(
            id=opportunity.preparation_action_id,
            name="Acquire a promised resource through an authorized seller",
            location_id=opportunity.preparation_location or agent.location_id,
            reason=(f"{agent.name} is preparing for accepted commitment "
                    f"{opportunity.commitment_id}: {opportunity.preparation_reason}."),
            tags=["commitment", "preparation", "purchase"],
            source_commitment_id=opportunity.commitment_id,
            commitment_priority=decision.pressure,
            commitment_decision=asdict(decision),
        )

    def should_attend_daily_event(self, agent: Agent, daily_event) -> bool:
        text = " ".join(
            [
                agent.occupation,
                agent.personality,
                " ".join(self._goal_texts(agent)),
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
                " ".join(self._goal_texts(agent)),
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
            add_activity(
                "buy_meal",
                "Buy a prepared meal",
                "market",
                f"{agent.name} wants a meal from the market stall.",
                ["purchase"],
            )
            add_activity(
                "eat_meal",
                "Eat an owned prepared meal",
                "cafe",
                f"{agent.name} wants to use a meal they already own.",
                ["consume"],
            )

        if primary_need == "wealth":
            add_activity(
                "seek_work",
                "Look for work or business opportunities",
                "market",
                f"{agent.name} wants to improve wealth.",
                ["wealth", "business"],
            )
            # This is only a proposal route. CrimeSystem remains authoritative
            # and rejects attempts without material and location opportunity.
            if agent.personality.lower() == "skeptical":
                add_activity(
                    "attempt_theft",
                    "Attempt to take unattended trade supplies",
                    "market",
                    f"{agent.name} is considering a risky shortcut to material security.",
                    ["unauthorized_take"],
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
                ["journalism", "rumor", "knowledge", "work"],
            )
            add_activity(
                "check_records",
                "Check records for leads",
                "library",
                f"{agent.name} is looking for background information.",
                ["journalism", "learning", "work"],
            )

        if "accountant" in text or "reliable allies" in text:
            add_activity(
                "review_records",
                "Review records and numbers",
                "library",
                f"{agent.name} wants reliable information before trusting others.",
                ["accounting", "knowledge", "work"],
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
                ["community", "volunteer", "social", "work"],
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
                "restock_market",
                "Prepare and restock market meals",
                "market",
                f"{agent.name} wants to replenish prepared market stock.",
                ["business", "market", "work", "production"],
            )
            add_activity(
                "pursue_business",
                "Look for business opportunities",
                "market",
                f"{agent.name} wants to find business opportunities.",
                ["business", "market", "wealth", "work"],
            )
            add_activity(
                "network",
                "Network with townspeople",
                "cafe",
                f"{agent.name} wants to grow influence through relationships.",
                ["business", "social"],
            )

        return candidates
