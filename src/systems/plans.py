"""Bounded authoritative multi-tick plans built from deterministic sources."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from src.systems.outcome_memory import KnowledgeRecipient


PLAN_SCHEMA_VERSION = 2
PLAN_STATUSES = {"active", "completed", "abandoned", "failed", "expired"}
STEP_STATUSES = {"pending", "completed", "skipped", "failed"}
KNOWN_ACTION_TYPES = {
    "commitment_acquire_resource", "commitment_help", "commitment_meet",
    "commitment_transfer",
}
TERMINAL_PLAN_STATUSES = PLAN_STATUSES - {"active"}
TEMPLATE_ACTIONS = {
    "help": ("commitment_help",),
    "meet": ("commitment_meet",),
    "transfer": ("commitment_acquire_resource", "commitment_transfer"),
}


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
        self.planning_records: list[dict] = []

    def to_dict(self) -> dict:
        return {"schema_version": PLAN_SCHEMA_VERSION,
                "plans": [plan.to_dict() for plan in self.plans],
                "next_number": self.next_number,
                "execution_records": list(self.execution_records),
                "planning_records": list(self.planning_records)}

    @classmethod
    def from_dict(cls, data: dict | None, *, commitment_system=None, agents=None,
                  outcome_memory=None) -> "PlanSystem":
        data = data or {}
        version = int(data.get("schema_version", 1))
        if version not in {1, PLAN_SCHEMA_VERSION}:
            raise ValueError(f"unsupported plan schema version: {version}")
        system = cls([AgentPlan.from_dict(item) for item in data.get("plans", [])],
                     next_number=data.get("next_number", 1),
                     commitment_system=commitment_system, agents=agents,
                     outcome_memory=outcome_memory)
        system.execution_records = list(data.get("execution_records", []))
        system.planning_records = list(data.get("planning_records", []))
        system._synchronize_terminal_sources()
        system.validate_invariants()
        return system

    def _synchronize_terminal_sources(self) -> None:
        if self.commitment_system is None:
            return
        commitments = {item.id: item for item in self.commitment_system.commitments}
        for plan in self.plans:
            source = commitments.get(plan.source_id)
            if not plan.active or source is None or source.status == "accepted":
                continue
            status = {"fulfilled": "completed", "failed": "failed",
                      "expired": "expired"}.get(source.status, "abandoned")
            self._terminate(
                plan, status, source.resolution_day or plan.created_day,
                f"source_{source.status}",
            )

    @staticmethod
    def plan_id_for(agent_id: str, commitment_id: str) -> str:
        """Return an owner-scoped ID derived only from immutable source identity."""
        return f"plan:commitment:{agent_id}:{commitment_id}"

    def _template_for(self, item) -> tuple[tuple[str, ...] | None, str]:
        """Select one explicit bounded template, or explain why none is safe."""
        if item.commitment_type == "transfer":
            # Preserve the mature transfer path, including its authoritative
            # feasibility checks for stock, affordability, and ownership.
            return TEMPLATE_ACTIONS["transfer"], ""
        location = str(item.metadata.get("location", "")).strip()
        has_time = item.due_day is not None or item.due_tick is not None
        if item.commitment_type == "meet":
            if not location:
                return None, "missing_meeting_location"
            if location not in self.commitment_system.location_ids:
                return None, "invalid_meeting_location"
            if not has_time:
                return None, "missing_meeting_time"
            return TEMPLATE_ACTIONS["meet"], ""
        if item.commitment_type == "help":
            if not str(item.metadata.get("task", "")).strip():
                return None, "missing_help_task"
            if not location:
                return None, "missing_help_location"
            if location not in self.commitment_system.location_ids:
                return None, "invalid_help_location"
            if not has_time:
                return None, "missing_help_time"
            return TEMPLATE_ACTIONS["help"], ""
        return None, "unsupported_commitment_type"

    def _record_planning_decision(self, item, day: int, reason: str) -> None:
        if any(record.get("commitment_id") == item.id for record in self.planning_records):
            return
        self.planning_records.append({
            "commitment_id": item.id,
            "agent_id": item.counterpart_id,
            "commitment_type": item.commitment_type,
            "eligible": not reason,
            "reason": reason or "bounded_template_available",
            "day": int(day),
        })

    def ensure_commitment_plans(self, day: int) -> None:
        commitments = {item.id: item for item in self.commitment_system.commitments}
        for plan in self.plans:
            if not plan.active:
                continue
            source = commitments.get(plan.source_id)
            if source is None or source.status != "accepted":
                status = {
                    "fulfilled": "completed", "failed": "failed", "expired": "expired",
                }.get(source.status if source else "", "abandoned")
                self._terminate(plan, status, day, f"source_{source.status if source else 'missing'}")
        existing = {(plan.source_type, plan.source_id) for plan in self.plans}
        for item in self.commitment_system.commitments:
            if item.status != "accepted" or ("commitment", item.id) in existing:
                continue
            actions, reason = self._template_for(item)
            self._record_planning_decision(item, day, reason)
            if actions is None:
                continue
            plan_id = self.plan_id_for(item.counterpart_id, item.id)
            plan = AgentPlan(
                id=plan_id, agent_id=item.counterpart_id,
                plan_type=f"commitment_{item.commitment_type}", source_type="commitment",
                source_id=item.id, created_day=day,
                steps=[PlanStep(f"{plan_id}:step:{index}:{action}", action)
                       for index, action in enumerate(actions, 1)],
                transitions=[{"day": day, "type": "created", "source_id": item.id}],
            )
            self.plans.append(plan)
            self.next_number += 1
            self._remember_plan(plan, day, "plan_created", 0)
            existing.add(("commitment", item.id))
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
                if feasibility != "feasible":
                    self._record_observation(plan, step, day, tick, reason)
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
                         tick: int | None, execution_key: str,
                         source_commitment_id: str | None = None,
                         action_type: str | None = None) -> None:
        plan = self.get(plan_id)
        step = plan.current_step
        if not plan.active or step is None or step.id != step_id:
            return
        if source_commitment_id is not None and source_commitment_id != plan.source_id:
            return
        if action_type is not None and action_type != step.action_type:
            return
        if not self._has_authoritative_proof(plan, step, execution_key):
            return
        if any(record["execution_key"] == execution_key for record in self.execution_records):
            return
        self.execution_records.append({"plan_id": plan_id, "step_id": step_id,
                                       "source_commitment_id": plan.source_id,
                                       "action_type": step.action_type,
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

    def _has_authoritative_proof(self, plan, step, execution_key: str) -> bool:
        if step.action_type == "commitment_acquire_resource":
            return any(
                record.get("commitment_id") == plan.source_id
                and record.get("exchange_id") == execution_key
                for record in self.commitment_system.attempt_records
            )
        return any(
            record.get("source_commitment_id") == plan.source_id
            and record.get("activity_id") == step.action_type
            and (record.get("event_key") == execution_key
                 or record.get("material_transfer_id") == execution_key)
            for record in self.commitment_system.execution_records
        )

    def _record_observation(self, plan, step, day, tick, reason) -> None:
        observation_key = f"observation:{plan.id}:{step.id}:{day}:{tick}:{reason}"
        if any(event.get("observation_key") == observation_key
               for event in plan.transitions):
            return
        plan.transitions.append({
            "day": day, "tick": tick, "type": "blocked_observation",
            "step_id": step.id, "reason": reason,
            "observation_key": observation_key,
        })

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
            source = self.commitment_system.get(plan.source_id)
            if source.status == "accepted":
                self.commitment_system.transition(
                    source.id, "failed", day=day, tick=tick,
                    reason=f"plan_failed:{reason}",
                    evidence={"plan_id": plan.id, "plan_step_id": step.id},
                )
            self._remember_plan(plan, day, "plan_failed", -1)

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

    def context_for_commitment(self, commitment_id: str) -> dict:
        plan = next((item for item in self.plans
                     if item.source_type == "commitment"
                     and item.source_id == commitment_id), None)
        decision = next((item for item in self.planning_records
                         if item.get("commitment_id") == commitment_id), None)
        if plan is None:
            return {
                "plan_status": "not_planned",
                "plan_stage": "unsupported" if decision and not decision["eligible"] else "unplanned",
                "no_plan_reason": decision.get("reason", "") if decision else "",
            }
        step = plan.current_step
        stage = "terminal"
        if plan.active and step:
            stage = ("preparing" if step.action_type == "commitment_acquire_resource"
                     else "pending")
        return {
            "plan_status": plan.status, "plan_stage": stage,
            "plan_type": plan.plan_type,
        }

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
            "one_plan_per_source": len({(plan.source_type, plan.source_id) for plan in self.plans}) == len(self.plans),
            "stable_plan_ids": all(
                plan.id.startswith("plan-") or plan.id == self.plan_id_for(plan.agent_id, plan.source_id)
                for plan in self.plans
            ),
            "execution_matches_source": all(
                record.get("source_commitment_id", next(
                    (plan.source_id for plan in self.plans if plan.id == record.get("plan_id")), ""
                )) == next((plan.source_id for plan in self.plans
                            if plan.id == record.get("plan_id")), None)
                for record in self.execution_records
            ),
            "terminal_source_no_active_plan": all(
                not plan.active or self.commitment_system.get(plan.source_id).status == "accepted"
                for plan in self.plans
            ) if self.commitment_system else True,
        }
        if not all(checks.values()):
            raise ValueError(f"plan invariant violation: {[key for key, value in checks.items() if not value]}")
        return checks
