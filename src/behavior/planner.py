import random
from dataclasses import asdict, dataclass

from src.agents.agent import Agent
from src.behavior.activity import Activity
from src.behavior.goal_strategy_contracts import ACTIVITY_EXECUTION, strategy_contract


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
    """Compare bounded priorities; randomness only breaks close calls."""

    def __init__(self) -> None:
        self.location_affinities: dict[str, tuple[str, ...]] = {}

    def set_location_affinities(self, locations: list) -> None:
        """Expose closed descriptive metadata to ordinary activity selection."""
        self.location_affinities = {
            item.id: tuple(item.affinities or ()) for item in locations
        }

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

    def create_intent_activity(self, current_intent, goal_dependency=None) -> Activity:
        strategy = getattr(current_intent, "strategy", "")
        source_goal_plan_id = getattr(current_intent, "source_goal_plan_id", None)
        contract = strategy_contract(strategy)
        if source_goal_plan_id and (
            contract is None or contract.execution_mode != ACTIVITY_EXECUTION
        ):
            raise ValueError("bound goal intent has no activity execution contract")
        if contract is not None and contract.execution_mode == ACTIVITY_EXECUTION:
            return Activity(
                id=contract.activity_id,
                name={
                    "seek_information_at_location": "Seek goal-relevant information",
                    "observe_relevant_activity": "Observe goal-relevant activity",
                    "direct_participation": "Participate directly in goal-relevant activity",
                    "study_reference_material": "Study owned reference material",
                    "study_reference_material_at_active_location": (
                        "Study owned reference material at an active location"
                    ),
                }[strategy],
                location_id=current_intent.target_location,
                reason=current_intent.description,
                tags=list(contract.required_activity_tags)
                + self.get_intent_activity_tags(current_intent),
                source_goal_id=current_intent.parent_goal_id,
                source_goal_plan_id=source_goal_plan_id,
                source_goal_plan_revision=current_intent.source_goal_plan_revision,
                source_goal_strategy=strategy,
                source_intent_id=current_intent.id,
                source_goal_dependency_kind=getattr(goal_dependency, "kind", None),
                source_goal_dependency_subject=getattr(goal_dependency, "subject_id", None),
                source_goal_dependency_authority_ref=getattr(
                    goal_dependency, "authority_reference", None
                ),
                source_goal_dependencies=(tuple({
                    "kind": item.kind,
                    "subject_id": item.subject_id,
                    "authority_reference": item.authority_reference,
                } for item in getattr(goal_dependency, "dependencies", ()))
                if len(getattr(goal_dependency, "dependencies", ())) > 1 else ()),
            )
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
        goal_dependency=None,
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
            current_intent is not None
            and goal_dependency is not None
            and goal_dependency.status == "preparable"
            and goal_dependency.preparation_activity_id
            and goal_dependency.plan_id == current_intent.source_goal_plan_id
            and goal_dependency.revision == current_intent.source_goal_plan_revision
            and goal_dependency.strategy == current_intent.strategy
            and goal_dependency.preparation_location in location_ids
        ):
            return self.create_goal_preparation_activity(
                agent, current_intent, goal_dependency.preparation,
            )

        intent_contract = (
            strategy_contract(getattr(current_intent, "strategy", ""))
            if current_intent else None
        )
        dependency_required = bool(
            intent_contract is not None and bool(intent_contract.dependencies)
        )
        dependency_allows_intent = (
            not dependency_required
            or (
                goal_dependency is not None
                and goal_dependency.status == "satisfied"
                and current_intent is not None
                and goal_dependency.plan_id == current_intent.source_goal_plan_id
                and goal_dependency.revision == current_intent.source_goal_plan_revision
                and goal_dependency.strategy == current_intent.strategy
            )
        )
        activity_executes_intent = (
            intent_contract is None
            or intent_contract.execution_mode == ACTIVITY_EXECUTION
        )

        if (
            current_intent
            and activity_executes_intent
            and dependency_allows_intent
            and current_intent.target_location
            and current_intent.target_location in location_ids
            and self.should_prioritize_intent_before_event(current_intent)
        ):
            activity = self.create_intent_activity(current_intent, goal_dependency)
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

        if (
            current_intent and activity_executes_intent
            and dependency_allows_intent and current_intent.target_location
        ):
            follow_probability = self.get_intent_activity_probability(current_intent)

            if (
                current_intent.target_location in location_ids
                and random.random() < follow_probability
            ):
                activity = self.create_intent_activity(current_intent, goal_dependency)
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
            source_plan_id=getattr(opportunity, "plan_id", None),
            source_plan_step_id=getattr(opportunity, "step_id", None),
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
            source_plan_id=getattr(opportunity, "plan_id", None),
            source_plan_step_id=getattr(opportunity, "step_id", None),
        )

    def create_goal_preparation_activity(self, agent, intent, dependency) -> Activity:
        return Activity(
            id=dependency.preparation_activity_id,
            name="Acquire reference material through an authorized seller",
            location_id=dependency.preparation_location,
            reason=(f"{agent.name} is preparing the bound goal strategy through "
                    "a current authorized purchase route."),
            tags=["goal_strategy", "preparation", "purchase", "reference_book"],
            source_goal_id=intent.parent_goal_id,
            source_goal_plan_id=intent.source_goal_plan_id,
            source_goal_plan_revision=intent.source_goal_plan_revision,
            source_goal_strategy=intent.strategy,
            source_intent_id=intent.id,
            source_goal_dependency_kind=dependency.kind,
            source_goal_dependency_subject=dependency.subject_id,
            source_goal_dependency_authority_ref=dependency.authority_reference,
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

        # Configured public places participate only in ordinary need behavior.
        # Their closed affinities do not grant commerce, event, crime, plan, or
        # employment authority.
        for location_id, affinities in self.location_affinities.items():
            if primary_need not in affinities:
                continue
            add_activity(
                f"ordinary_{primary_need}_{location_id}",
                {
                    "social": "Spend time with other residents",
                    "knowledge": "Explore and learn in a public place",
                    "community": "Take part in ordinary community life",
                }.get(primary_need, "Spend time in a public place"),
                location_id,
                f"{agent.name} chose an active public place for {primary_need} needs.",
                ["ordinary_public_activity", primary_need],
            )

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
