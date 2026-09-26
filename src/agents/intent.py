from dataclasses import dataclass, asdict, field
import uuid


@dataclass
class AgentIntent:
    agent_name: str
    intent_type: str
    description: str
    created_day: int
    expires_day: int
    priority: int
    target_agent: str | None = None
    target_location: str | None = None
    status: str = "active"
    progress: int = 0
    progress_goal: int = 2
    completed_day: int | None = None
    completion_reason: str = ""
    evidence: list[str] = field(default_factory=list)
    parent_goal_id: str | None = None
    source_goal_plan_id: str | None = None
    source_goal_plan_revision: int = 0
    strategy: str = ""
    strategy_score: float = 0.0
    relationship_influenced: bool = False
    relationship_reason: str = ""
    relationship_snapshot: dict = field(default_factory=dict)
    relevant_social_memories: list[str] = field(default_factory=list)
    opportunity_count: int = 0
    expiration_reason: str = ""
    terminal_trigger: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def is_expired(self, current_day: int) -> bool:
        return current_day > self.expires_day

    def is_active(self, current_day: int) -> bool:
        return self.status == "active" and not self.is_expired(current_day)

    def involves_agent(self, agent_name: str) -> bool:
        return self.target_agent == agent_name

    def add_progress(
        self,
        amount: int,
        evidence: str,
        max_evidence: int = 5,
    ) -> None:
        if self.status != "active":
            return

        self.progress = max(0, self.progress + amount)

        if evidence:
            self.evidence.append(evidence)
            self.evidence = self.evidence[-max_evidence:]

    def mark_succeeded(self, day: int, reason: str) -> None:
        self.status = "succeeded"
        self.completed_day = day
        self.completion_reason = reason

    def mark_failed(
        self,
        day: int,
        reason: str,
        status: str = "failed",
    ) -> None:
        self.status = status
        self.completed_day = day
        self.completion_reason = reason

    def mark_superseded(self, day: int, reason: str, trigger: str = "") -> None:
        self.mark_failed(day=day, reason=reason, status="superseded")
        self.terminal_trigger = trigger

    def mark_blocked(self, day: int, reason: str) -> None:
        self.mark_failed(day=day, reason=reason, status="blocked")

    def to_dict(self) -> dict:
        return asdict(self)
