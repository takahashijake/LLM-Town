"""Small, durable commitments that survive short-lived tactics."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field


GOAL_STATUSES = {"active", "paused", "achieved", "blocked", "abandoned"}
GOAL_CATEGORIES = {
    "build_friendship",
    "repair_relationship",
    "investigate",
    "socialize",
    "seek_work",
    "increase_knowledge",
    "improve_social_support",
}


def _legacy_category(description: str) -> str:
    text = description.lower()
    if any(word in text for word in ("secret", "betray", "reliable", "investigat")):
        return "investigate"
    if any(word in text for word in ("business", "work", "opportunit")):
        return "seek_work"
    if any(word in text for word in ("friend", "allies", "ally")):
        return "build_friendship"
    if any(word in text for word in ("knowledge", "learn", "understand")):
        return "increase_knowledge"
    if any(word in text for word in ("community", "support", "help the town")):
        return "improve_social_support"
    return "socialize"


def _default_target(category: str) -> int:
    return {
        "build_friendship": 4,
        "repair_relationship": 3,
        "investigate": 3,
        "socialize": 4,
        "seek_work": 3,
        "increase_knowledge": 3,
        "improve_social_support": 4,
    }.get(category, 3)


@dataclass(eq=False)
class Goal:
    id: str
    agent_name: str
    description: str
    category: str
    priority: int
    created_day: int
    review_day: int
    status: str = "active"
    progress: int = 0
    progress_target: int = 3
    target_agents: list[str] = field(default_factory=list)
    target_locations: list[str] = field(default_factory=list)
    success_conditions: list[str] = field(default_factory=list)
    current_intent_id: str | None = None
    current_strategy: str | None = None
    current_strategy_target: str | None = None
    strategy_started_day: int | None = None
    last_review_day: int | None = None
    last_relationship_score: int | None = None
    last_reputation_risk: float = 0.0
    evidence: list[dict] = field(default_factory=list)
    completion_day: int | None = None
    adaptation_count: int = 0
    recovered_after_adaptation: bool = False

    def __post_init__(self) -> None:
        if self.category not in GOAL_CATEGORIES:
            self.category = _legacy_category(self.description)
        if self.status not in GOAL_STATUSES:
            self.status = "active"
        self.priority = max(1, min(5, int(self.priority)))
        self.progress = max(0, int(self.progress))
        self.progress_target = max(1, int(self.progress_target))
        self.target_agents = list(dict.fromkeys(self.target_agents))
        self.target_locations = list(dict.fromkeys(self.target_locations))

    def __str__(self) -> str:
        return self.description

    def __eq__(self, other: object) -> bool:
        # Keeps legacy assertions and callers comparing goals with strings useful.
        if isinstance(other, str):
            return self.description == other
        if isinstance(other, Goal):
            return self.to_dict() == other.to_dict()
        return False

    def is_active(self) -> bool:
        return self.status == "active"

    def add_progress(self, amount: int, day: int, record: dict) -> bool:
        if not self.is_active() or amount <= 0:
            return False
        evidence_key = record.get("evidence_key")
        if evidence_key and any(
            item.get("evidence_key") == evidence_key for item in self.evidence
        ):
            return False
        old_progress = self.progress
        self.progress = min(self.progress_target, self.progress + amount)
        self.evidence.append(
            {"type": "progress", "day": day, "old_progress": old_progress,
             "new_progress": self.progress, **record}
        )
        self.evidence = self.evidence[-30:]
        return True

    def mark_achieved(self, day: int, reason: str) -> None:
        self.status = "achieved"
        self.completion_day = day
        self.current_intent_id = None
        self.evidence.append({"type": "achievement", "day": day, "reason": reason})

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Goal":
        known = cls.__dataclass_fields__
        return cls(**{key: value for key, value in data.items() if key in known})

    @classmethod
    def from_legacy(cls, agent_name: str, description: str, index: int = 0) -> "Goal":
        category = _legacy_category(description)
        digest = hashlib.sha1(
            f"{agent_name}|{index}|{description}".encode("utf-8")
        ).hexdigest()[:12]
        locations = {
            "investigate": ["library"],
            "increase_knowledge": ["library"],
            "seek_work": ["market"],
            "socialize": ["cafe"],
            "improve_social_support": ["town_square"],
        }.get(category, [])
        return cls(
            id=f"goal-{digest}",
            agent_name=agent_name,
            description=description,
            category=category,
            priority=3,
            created_day=0,
            review_day=7,
            progress_target=_default_target(category),
            target_locations=locations,
            success_conditions=[f"Reach {category} progress target"],
            evidence=[{"type": "legacy_conversion", "day": 0}],
        )
