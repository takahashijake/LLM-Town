"""Bounded authoritative multi-tick plans built from deterministic sources."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from src.systems.outcome_memory import KnowledgeRecipient


PLAN_STATUSES = {"active", "completed", "abandoned", "failed", "expired"}
STEP_STATUSES = {"pending", "completed", "skipped", "failed"}
KNOWN_ACTION_TYPES = {"commitment_acquire_resource", "commitment_transfer"}
TERMINAL_PLAN_STATUSES = PLAN_STATUSES - {"active"}


@dataclass
class PlanStep:
    id: str
    action_type: str
    status: str = "pending"
    attempts: int = 0
    max_attempts: int = 3
    execution_key: str | None = None
    last_reason: str = ""

    def __post_init__(self) -> None:
        if self.action_type not in KNOWN_ACTION_TYPES:
            raise ValueError(f"unknown plan action type: {self.action_type}")
        if self.status not in STEP_STATUSES:
            raise ValueError(f"invalid plan step status: {self.status}")
        if self.max_attempts < 1 or self.attempts < 0:
            raise ValueError("plan step attempts must be bounded and non-negative")

    @classmethod
    def from_dict(cls, data: dict) -> "PlanStep":
        return cls(**{key: value for key, value in data.items()
                      if key in cls.__dataclass_fields__})


@dataclass
class AgentPlan:
    id: str
    agent_id: str
    plan_type: str
    source_type: str
    source_id: str
    created_day: int
    steps: list[PlanStep]
    status: str = "active"
    current_step_index: int = 0
    completed_day: int | None = None
    terminal_reason: str = ""
    transitions: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in PLAN_STATUSES:
            raise ValueError(f"invalid plan status: {self.status}")
        if not self.steps or len(self.steps) > 4:
            raise ValueError("plans require one to four bounded steps")

    @property
    def active(self) -> bool:
        return self.status == "active"

    @property
    def current_step(self) -> PlanStep | None:
        if not self.active or not 0 <= self.current_step_index < len(self.steps):
            return None
        return self.steps[self.current_step_index]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentPlan":
        values = {key: value for key, value in data.items()
                  if key in cls.__dataclass_fields__}
        values["steps"] = [PlanStep.from_dict(step) for step in values["steps"]]
        return cls(**values)


@dataclass(frozen=True)
class PlanOpportunity:
    plan_id: str
    step_id: str
    commitment_id: str
    agent_id: str
    counterpart_id: str
    commitment_type: str
    action_type: str
    target_location: str | None
    target_good_id: str | None
    quantity: int | None
    urgency: float
    feasibility: str
    infeasibility_reason: str
    provenance: str
    attempted_in_window: bool = False
    preparation_action_id: str | None = None
    preparation_location: str | None = None
    preparation_reason: str = ""


class PlanSystem:
    """Owns plan lifecycle; delegates every world mutation to existing systems."""

    def __init__(self, plans=None, *, next_number=1, commitment_system=None, agents=None,
                 outcome_memory=None):
        self.plans = list(plans or [])
        self.next_number = max(1, int(next_number))
        self.commitment_system = commitment_system
        self.agents = list(agents or [])
        self.outcome_memory = outcome_memory
        self.execution_records: list[dict] = []

    def to_dict(self) -> dict:
        return {"plans": [plan.to_dict() for plan in self.plans],
                "next_number": self.next_number,
                "execution_records": list(self.execution_records)}

    @classmethod
    def from_dict(cls, data: dict | None, *, commitment_system=None, agents=None,
                  outcome_memory=None) -> "PlanSystem":
        data = data or {}
        system = cls([AgentPlan.from_dict(item) for item in data.get("plans", [])],
                     next_number=data.get("next_number", 1),
                     commitment_system=commitment_system, agents=agents,
                     outcome_memory=outcome_memory)
        system.execution_records = list(data.get("execution_records", []))
        system.validate_invariants()
        return system

    def ensure_commitment_plans(self, day: int) -> None:
        commitments = {item.id: item for item in self.commitment_system.commitments}
        for plan in self.plans:
            if not plan.active:
                continue
            source = commitments.get(plan.source_id)
            if source is None or source.status != "accepted":
                status = "completed" if source and source.status == "fulfilled" else "abandoned"
                self._terminate(plan, status, day, f"source_{source.status if source else 'missing'}")
        existing = {(plan.source_type, plan.source_id) for plan in self.plans}
        for item in self.commitment_system.commitments:
            if (item.status != "accepted" or item.commitment_type != "transfer"
                    or ("commitment", item.id) in existing):
                continue
            plan = AgentPlan(
                id=f"plan-{self.next_number:08d}", agent_id=item.counterpart_id,
                plan_type="commitment_transfer", source_type="commitment",
                source_id=item.id, created_day=day,
                steps=[
                    PlanStep(f"plan-{self.next_number:08d}:acquire", "commitment_acquire_resource"),
                    PlanStep(f"plan-{self.next_number:08d}:deliver", "commitment_transfer"),
                ],
                transitions=[{"day": day, "type": "created", "source_id": item.id}],
            )
            self.plans.append(plan)
            self.next_number += 1
        self.validate_invariants()

    def opportunities_for_agent(self, agent_id: str, *, day: int, tick: int | None) -> list[PlanOpportunity]:
        self.ensure_commitment_plans(day)
        results = []
        for plan in self.plans:
            if not plan.active or plan.agent_id != agent_id:
                continue
            source_opportunities = self.commitment_system.opportunities_for_agent(
                agent_id, day=day, tick=tick)
            source = next((item for item in source_opportunities
                           if item.commitment_id == plan.source_id), None)
            if source is None:
                continue
            step = plan.current_step
            if step.action_type == "commitment_acquire_resource" and source.feasibility == "feasible":
                self._complete_step(plan, step, day, tick, "resource_already_owned", None)
                step = plan.current_step
            if step is None:
                continue
            if step.action_type == "commitment_acquire_resource":
                action_id = source.preparation_action_id
                # Preserve the commitment opportunity's temporary-infeasibility
                # marker: ActivityPlanner uses it to choose the preparation
                # action instead of attempting delivery.
                feasibility = source.feasibility
                location = source.preparation_location
                reason = source.preparation_reason or source.infeasibility_reason
                if not action_id:
                    observation_key = f"blocked:{day}:{tick}"
                    if not any(event.get("observation_key") == observation_key
                               for event in plan.transitions):
                        self.record_failure(plan.id, step.id, day=day, tick=tick,
                                            reason=reason or "no_acquisition_route")
                        plan.transitions[-1]["observation_key"] = observation_key
                    if not plan.active:
                        self._remember_plan(plan, day, "plan_failed", -1)
                        continue
            else:
                action_id = None
                feasibility = source.feasibility
                location = source.target_location
                reason = source.infeasibility_reason
            results.append(PlanOpportunity(
                plan.id, step.id, source.commitment_id, agent_id,
                source.counterpart_id, source.commitment_type, step.action_type,
                location, source.target_good_id, source.quantity, source.urgency,
                feasibility, reason, f"plan:{plan.id}:step:{step.id}",
                source.attempted_in_window, action_id, source.preparation_location,
                source.preparation_reason,
            ))
        return results

    def record_execution(self, plan_id: str, step_id: str, *, day: int,
                         tick: int | None, execution_key: str) -> None:
        plan = self.get(plan_id)
        step = plan.current_step
        if not plan.active or step is None or step.id != step_id:
            return
        if any(record["execution_key"] == execution_key for record in self.execution_records):
            return
        self.execution_records.append({"plan_id": plan_id, "step_id": step_id,
                                       "day": day, "tick": tick,
                                       "execution_key": execution_key})
        if step.action_type == "commitment_acquire_resource" and self.outcome_memory:
            source = self.commitment_system.get(plan.source_id)
            quantity = int(source.metadata.get("quantity", 1))
            good = source.metadata.get("good_id", "item").replace("_", " ")
            self.outcome_memory.project(
                source_system="materials", source_id=execution_key,
                event_type="important_acquisition", day=day, hour=tick,
                recipients=[KnowledgeRecipient(
                    plan.agent_id, "self_action",
                    f"I acquired {quantity} {good} through an authorized purchase for my promise.",
                    (), 1, 4,
                )],
            )
        self._complete_step(plan, step, day, tick, "authoritative_execution", execution_key)
        self.validate_invariants()

    def record_failure(self, plan_id: str, step_id: str, *, day: int,
                       tick: int | None, reason: str) -> None:
        plan = self.get(plan_id)
        step = plan.current_step
        if not plan.active or step is None or step.id != step_id:
            return
        step.attempts += 1
        step.last_reason = reason
        plan.transitions.append({"day": day, "tick": tick, "type": "blocked",
                                 "step_id": step.id, "reason": reason,
                                 "attempt": step.attempts})
        if step.attempts >= step.max_attempts:
            step.status = "failed"
            self._terminate(plan, "failed", day, f"attempt_budget:{reason}")

    def _complete_step(self, plan, step, day, tick, reason, execution_key) -> None:
        step.status = "completed"
        step.execution_key = execution_key
        step.last_reason = reason
        plan.transitions.append({"day": day, "tick": tick, "type": "step_completed",
                                 "step_id": step.id, "reason": reason,
                                 "execution_key": execution_key})
        plan.current_step_index += 1
        if plan.current_step_index == len(plan.steps):
            self._terminate(plan, "completed", day, "all_steps_completed")
            self._remember_plan(plan, day, "plan_completed", 1)

    def _remember_plan(self, plan, day, event_type, sentiment) -> None:
        """Plan mechanics are self-private unless another system exposes them."""
        if self.outcome_memory is None:
            return
        reason = plan.terminal_reason.replace("_", " ")
        self.outcome_memory.project(
            source_system="plans", source_id=plan.id, event_type=event_type,
            day=day, hour=0,
            recipients=[KnowledgeRecipient(
                plan.agent_id, "self_action",
                f"My plan {event_type.replace('_', ' ')}: {reason}.",
                (), sentiment,
            )],
        )

    @staticmethod
    def _terminate(plan, status, day, reason) -> None:
        if not plan.active:
            return
        plan.status = status
        plan.completed_day = day
        plan.terminal_reason = reason
        plan.transitions.append({"day": day, "type": status, "reason": reason})

    def get(self, plan_id: str) -> AgentPlan:
        matches = [plan for plan in self.plans if plan.id == plan_id]
        if len(matches) != 1:
            raise ValueError(f"unknown plan: {plan_id}")
        return matches[0]

    def validate_invariants(self) -> dict[str, bool]:
        ids = [plan.id for plan in self.plans]
        source_ids = {item.id for item in self.commitment_system.commitments} if self.commitment_system else set()
        record_keys = [record["execution_key"] for record in self.execution_records]
        checks = {
            "unique_plan_ids": len(ids) == len(set(ids)),
            "valid_statuses": all(plan.status in PLAN_STATUSES for plan in self.plans),
            "valid_sources": all(plan.source_type == "commitment" and plan.source_id in source_ids for plan in self.plans),
            "agent_owns_plan": all((not self.commitment_system) or self.commitment_system.get(plan.source_id).counterpart_id == plan.agent_id for plan in self.plans),
            "known_actions": all(step.action_type in KNOWN_ACTION_TYPES for plan in self.plans for step in plan.steps),
            "step_index_bounded": all(0 <= plan.current_step_index <= len(plan.steps) for plan in self.plans),
            "terminal_not_active_step": all(plan.active or plan.current_step is None for plan in self.plans),
            "completed_steps_complete": all(plan.status != "completed" or all(step.status in {"completed", "skipped"} for step in plan.steps) for plan in self.plans),
            "execution_unique": len(record_keys) == len(set(record_keys)),
            "execution_references_step": all(any(plan.id == record["plan_id"] and any(step.id == record["step_id"] for step in plan.steps) for plan in self.plans) for record in self.execution_records),
        }
        if not all(checks.values()):
            raise ValueError(f"plan invariant violation: {[key for key, value in checks.items() if not value]}")
        return checks
