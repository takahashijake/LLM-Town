"""Finite execution contracts for persistent goal-plan strategies."""

from __future__ import annotations

from dataclasses import dataclass


SOCIAL_EXECUTION = "validated_social_action"
ACTIVITY_EXECUTION = "strategy_activity"


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

    def __post_init__(self) -> None:
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
            "seek_information_at_location", ACTIVITY_EXECUTION, "strategy_activity",
            activity_id="goal_seek_information",
            required_activity_tags=("goal_strategy", "seek_information"),
            requires_target_location=True,
        ),
        GoalStrategyExecutionContract(
            "observe_relevant_activity", ACTIVITY_EXECUTION, "strategy_activity",
            activity_id="goal_observe_relevant_activity",
            required_activity_tags=("goal_strategy", "observe_relevant_activity"),
            requires_target_location=True,
        ),
        GoalStrategyExecutionContract(
            "direct_participation", ACTIVITY_EXECUTION, "strategy_activity",
            activity_id="goal_direct_participation",
            required_activity_tags=("goal_strategy", "direct_participation"),
            requires_target_location=True,
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
