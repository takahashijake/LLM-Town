"""Finite execution contracts for persistent goal-plan strategies."""

from __future__ import annotations

from dataclasses import dataclass


SOCIAL_EXECUTION = "validated_social_action"
ACTIVITY_EXECUTION = "strategy_activity"
DELEGATION_EXECUTION = "authoritative_commitment_outcome"
DAILY_EVENT_AT_TARGET = "daily_event_at_target_location"
OWNED_GOOD = "owned_good"
DEPENDENCY_KINDS = frozenset({DAILY_EVENT_AT_TARGET, OWNED_GOOD})
MAX_STRATEGY_DEPENDENCIES = 2


@dataclass(frozen=True)
class GoalStrategyDependencyContract:
    """One finite, authoritative prerequisite for a strategy revision."""

    kind: str
    authority: str
    preparation_activity_id: str | None = None
    subject_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in DEPENDENCY_KINDS:
            raise ValueError(f"unknown goal strategy dependency kind: {self.kind}")
        if self.kind == DAILY_EVENT_AT_TARGET:
            if (self.authority != "current_daily_event" or self.preparation_activity_id
                    or self.subject_id):
                raise ValueError("malformed daily-event dependency contract")
        elif self.kind == OWNED_GOOD:
            if (
                self.authority != "material_inventory"
                or self.preparation_activity_id != "goal_acquire_reference_book"
                or self.subject_id != "reference_book"
            ):
                raise ValueError("malformed owned-good dependency contract")


@dataclass(frozen=True)
class GoalStrategyExecutionContract:
    strategy: str
    execution_mode: str
    evidence_type: str
    required_social_action: str | None = None
    target_agent_policy: str = "none"
    activity_id: str | None = None
    required_activity_tags: tuple[str, ...] = ()
    requires_target_location: bool = False
    dependencies: tuple[GoalStrategyDependencyContract, ...] = ()
    delegated_commitment_type: str | None = None
    delegated_task_code: str | None = None
    delegated_task: str | None = None

    @property
    def dependency(self) -> GoalStrategyDependencyContract | None:
        """Compatibility view for the existing zero/one-dependency contracts."""
        return self.dependencies[0] if len(self.dependencies) == 1 else None

    def __post_init__(self) -> None:
        if len(self.dependencies) > MAX_STRATEGY_DEPENDENCIES:
            raise ValueError("goal strategy dependencies exceed bounded maximum")
        identities = [(item.kind, item.subject_id) for item in self.dependencies]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate goal strategy dependencies")
        if self.execution_mode == SOCIAL_EXECUTION:
            if not self.required_social_action or self.activity_id:
                raise ValueError(f"malformed social strategy contract: {self.strategy}")
            if self.target_agent_policy not in {"selected_required", "selected_if_present"}:
                raise ValueError(f"malformed social target policy: {self.strategy}")
        elif self.execution_mode == ACTIVITY_EXECUTION:
            if self.required_social_action or not self.activity_id:
                raise ValueError(f"malformed activity strategy contract: {self.strategy}")
            if not self.requires_target_location or not self.required_activity_tags:
                raise ValueError(f"malformed activity location contract: {self.strategy}")
        elif self.execution_mode == DELEGATION_EXECUTION:
            if (
                self.required_social_action != "ask_for_help"
                or self.target_agent_policy != "selected_required"
                or not self.requires_target_location
                or self.activity_id
                or self.dependencies
                or self.delegated_commitment_type != "help"
                or self.delegated_task_code != "goal_research_help"
                or self.delegated_task != "help with research"
                or self.evidence_type != "commitment_fulfilled"
            ):
                raise ValueError(f"malformed delegation strategy contract: {self.strategy}")
        else:
            raise ValueError(f"unknown strategy execution mode: {self.execution_mode}")


GOAL_STRATEGY_EXECUTION_CONTRACTS = {
    contract.strategy: contract
    for contract in (
        GoalStrategyExecutionContract(
            "direct_cooperation", SOCIAL_EXECUTION, "social_action",
            required_social_action="cooperate", target_agent_policy="selected_required",
        ),
        GoalStrategyExecutionContract(
            "apologize_directly", SOCIAL_EXECUTION, "social_action",
            required_social_action="apologize", target_agent_policy="selected_required",
        ),
        GoalStrategyExecutionContract(
            "offer_help", SOCIAL_EXECUTION, "social_action",
            required_social_action="offer_help", target_agent_policy="selected_required",
        ),
        GoalStrategyExecutionContract(
            "low_risk_chat", SOCIAL_EXECUTION, "social_action",
            required_social_action="chat", target_agent_policy="selected_if_present",
        ),
        GoalStrategyExecutionContract(
            "ask_target_directly", SOCIAL_EXECUTION, "social_action",
            required_social_action="ask_for_help", target_agent_policy="selected_required",
        ),
        GoalStrategyExecutionContract(
            "ask_informed_agent", SOCIAL_EXECUTION, "social_action",
            required_social_action="ask_for_help", target_agent_policy="selected_required",
        ),
        GoalStrategyExecutionContract(
            "ask_reliable_partner", SOCIAL_EXECUTION, "social_action",
            required_social_action="ask_for_help", target_agent_policy="selected_required",
        ),
        GoalStrategyExecutionContract(
            "request_research_help", DELEGATION_EXECUTION,
            "commitment_fulfilled", required_social_action="ask_for_help",
            target_agent_policy="selected_required", requires_target_location=True,
            delegated_commitment_type="help",
            delegated_task_code="goal_research_help",
            delegated_task="help with research",
        ),
        GoalStrategyExecutionContract(
            "seek_information_at_location", ACTIVITY_EXECUTION, "strategy_activity",
            activity_id="goal_seek_information",
            required_activity_tags=("goal_strategy", "seek_information"),
            requires_target_location=True,
        ),
        GoalStrategyExecutionContract(
            "study_reference_material", ACTIVITY_EXECUTION, "strategy_activity",
            activity_id="goal_study_reference_material",
            required_activity_tags=("goal_strategy", "study_reference_material"),
            requires_target_location=True,
            dependencies=(GoalStrategyDependencyContract(
                OWNED_GOOD, "material_inventory",
                preparation_activity_id="goal_acquire_reference_book",
                subject_id="reference_book",
            ),),
        ),
        GoalStrategyExecutionContract(
            "study_reference_material_at_active_location",
            ACTIVITY_EXECUTION, "strategy_activity",
            activity_id="goal_study_reference_material_at_active_location",
            required_activity_tags=(
                "goal_strategy", "study_reference_material_at_active_location",
            ),
            requires_target_location=True,
            dependencies=(
                GoalStrategyDependencyContract(
                    OWNED_GOOD, "material_inventory",
                    preparation_activity_id="goal_acquire_reference_book",
                    subject_id="reference_book",
                ),
                GoalStrategyDependencyContract(
                    DAILY_EVENT_AT_TARGET, "current_daily_event",
                ),
            ),
        ),
        GoalStrategyExecutionContract(
            "observe_relevant_activity", ACTIVITY_EXECUTION, "strategy_activity",
            activity_id="goal_observe_relevant_activity",
            required_activity_tags=("goal_strategy", "observe_relevant_activity"),
            requires_target_location=True,
            dependencies=(GoalStrategyDependencyContract(
                DAILY_EVENT_AT_TARGET, "current_daily_event",
            ),),
        ),
        GoalStrategyExecutionContract(
            "direct_participation", ACTIVITY_EXECUTION, "strategy_activity",
            activity_id="goal_direct_participation",
            required_activity_tags=("goal_strategy", "direct_participation"),
            requires_target_location=True,
            dependencies=(GoalStrategyDependencyContract(
                DAILY_EVENT_AT_TARGET, "current_daily_event",
            ),),
        ),
    )
}


def strategy_contract(strategy: str) -> GoalStrategyExecutionContract | None:
    return GOAL_STRATEGY_EXECUTION_CONTRACTS.get(strategy)


def strategy_vocabulary() -> frozenset[str]:
    return frozenset(GOAL_STRATEGY_EXECUTION_CONTRACTS)


def registered_social_actions() -> frozenset[str]:
    return frozenset(
        contract.required_social_action
        for contract in GOAL_STRATEGY_EXECUTION_CONTRACTS.values()
        if contract.required_social_action
    )


def required_social_action(strategy: str) -> str | None:
    contract = strategy_contract(strategy)
    return contract.required_social_action if contract else None
