"""Agent-specific, evidence-backed reputation beliefs.

Relationships describe a pair's bond.  Reputation describes what one agent
believes about another agent's general conduct.  This module deliberately has
no town-wide score: every belief belongs to an observer and every hearsay
update carries an explicit transmission path.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.actions.action_system import ActionSystem
    from src.agents.agent import Agent


REPUTATION_DIMENSIONS = (
    "trustworthiness",
    "helpfulness",
    "cooperativeness",
    "hostility",
)
REPUTATION_SOURCE_TYPES = (
    "direct_interaction",
    "direct_observation",
    "public_event",
    "hearsay",
)
MAX_REPUTATION_SCORE = 5.0
MAX_RUMOR_DEPTH = 2

SOURCE_CONFIDENCE_LIMITS = {
    "direct_interaction": 1.0,
    "direct_observation": 0.85,
    "public_event": 0.75,
    "hearsay": 0.60,
}
SOURCE_PRIORITY = {
    "hearsay": 0,
    "public_event": 1,
    "direct_observation": 2,
    "direct_interaction": 3,
}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@dataclass
class ReputationEvidence:
    """One causally acquired piece of social information."""

    evidence_id: str
    value: float
    confidence: float
    source_type: str
    source_agent: str
    day: int
    transmission_depth: int = 0
    transmission_chain: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.source_type not in REPUTATION_SOURCE_TYPES:
            raise ValueError(f"Unknown reputation source type: {self.source_type}")
        self.value = _clamp(float(self.value), -1.0, 1.0)
        self.confidence = _clamp(
            float(self.confidence),
            0.0,
            SOURCE_CONFIDENCE_LIMITS[self.source_type],
        )
        self.transmission_depth = max(0, int(self.transmission_depth))
        self.transmission_chain = list(dict.fromkeys(self.transmission_chain))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReputationBelief:
    """One observer's bounded belief about one target and dimension."""

    target_agent: str
    dimension: str
    score: float = 0.0
    confidence: float = 0.0
    source_type: str = "hearsay"
    last_updated_day: int = 0
    evidence: list[ReputationEvidence] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.dimension not in REPUTATION_DIMENSIONS:
            raise ValueError(f"Unknown reputation dimension: {self.dimension}")
        self.evidence = [
            item if isinstance(item, ReputationEvidence) else ReputationEvidence(**item)
            for item in self.evidence
        ]
        if self.evidence:
            self.recalculate()

    def add_evidence(self, item: ReputationEvidence) -> bool:
        """Add or upgrade evidence, returning whether the belief changed."""
        for index, existing in enumerate(self.evidence):
            if existing.evidence_id != item.evidence_id:
                continue
            existing_rank = (
                SOURCE_PRIORITY[existing.source_type], existing.confidence
            )
            item_rank = (SOURCE_PRIORITY[item.source_type], item.confidence)
            if item_rank <= existing_rank:
                return False
            self.evidence[index] = item
            self.recalculate()
            return True

        self.evidence.append(item)
        self.recalculate()
        return True

    def recalculate(self) -> None:
        direct = [
            item for item in self.evidence
            if item.source_type in {"direct_interaction", "direct_observation"}
        ]
        indirect = [item for item in self.evidence if item not in direct]
        direct_signal = sum(item.value * item.confidence for item in direct)
        indirect_signal = sum(item.value * item.confidence for item in indirect)

        # Once direct experience exists, accumulated hearsay may qualify it but
        # cannot swamp it. This keeps testimony useful without making it more
        # authoritative than lived experience.
        if direct:
            indirect_limit = max(0.5, abs(direct_signal) * 0.75)
            indirect_signal = _clamp(
                indirect_signal, -indirect_limit, indirect_limit
            )

        signal = direct_signal + indirect_signal
        self.score = round(
            MAX_REPUTATION_SCORE * math.tanh(signal / MAX_REPUTATION_SCORE),
            4,
        )
        strongest = max(
            self.evidence,
            key=lambda item: (
                SOURCE_PRIORITY[item.source_type], item.confidence, item.day
            ),
        )
        self.source_type = strongest.source_type
        self.confidence = round(
            max(item.confidence for item in self.evidence), 4
        )
        if not direct and all(
            item.source_type == "hearsay" for item in self.evidence
        ):
            self.confidence = min(
                self.confidence, SOURCE_CONFIDENCE_LIMITS["hearsay"]
            )
        self.last_updated_day = max(item.day for item in self.evidence)

    def to_dict(self) -> dict:
        return {
            "target_agent": self.target_agent,
            "dimension": self.dimension,
            "score": self.score,
            "confidence": self.confidence,
            "source_type": self.source_type,
            "last_updated_day": self.last_updated_day,
            "evidence": [item.to_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReputationBelief":
        return cls(
            target_agent=data["target_agent"],
            dimension=data["dimension"],
            score=data.get("score", 0.0),
            confidence=data.get("confidence", 0.0),
            source_type=data.get("source_type", "hearsay"),
            last_updated_day=data.get("last_updated_day", 0),
            evidence=data.get("evidence", []),
        )


class ReputationSystem:
    """Apply direct conduct and explicit rumor transmissions to beliefs."""

    def __init__(
        self,
        actions: "ActionSystem",
        update_records: list[dict] | None = None,
    ):
        self.actions = actions
        self.update_records = update_records if update_records is not None else []

    @staticmethod
    def _belief(
        observer: "Agent",
        target_agent: str,
        dimension: str,
    ) -> ReputationBelief:
        target_beliefs = observer.reputation_beliefs.setdefault(target_agent, {})
        belief = target_beliefs.get(dimension)
        if not isinstance(belief, ReputationBelief):
            belief = ReputationBelief(
                target_agent=target_agent,
                dimension=dimension,
            )
            target_beliefs[dimension] = belief
        return belief

    def _apply_evidence(
        self,
        *,
        observer: "Agent",
        target_agent: str,
        dimension: str,
        evidence: ReputationEvidence,
        day: int,
        third_party: bool,
    ) -> dict | None:
        if observer.name == target_agent or dimension not in REPUTATION_DIMENSIONS:
            return None
        belief = self._belief(observer, target_agent, dimension)
        old_score = belief.score
        old_confidence = belief.confidence
        if not belief.add_evidence(evidence):
            return None
        record = {
            "observer": observer.name,
            "target_agent": target_agent,
            "dimension": dimension,
            "old_score": old_score,
            "new_score": belief.score,
            "old_confidence": old_confidence,
            "new_confidence": belief.confidence,
            "evidence_confidence": evidence.confidence,
            "source_type": evidence.source_type,
            "source_agent": evidence.source_agent,
            "evidence_id": evidence.evidence_id,
            "day": day,
            "transmission_depth": evidence.transmission_depth,
            "third_party": third_party,
        }
        self.update_records.append(record)
        return record

    def record_direct_action(
        self,
        *,
        day: int,
        hour: int,
        actor: "Agent",
        observer: "Agent",
        action: str,
    ) -> list[dict]:
        updates = []
        effects = self.actions.get_reputation_effects(action)
        for dimension, value in effects.items():
            evidence = ReputationEvidence(
                evidence_id=(
                    f"conversation:{day}:{hour}:{actor.name}:{observer.name}:"
                    f"{action}:{dimension}"
                ),
                value=value,
                confidence=0.90,
                source_type="direct_interaction",
                source_agent=actor.name,
                day=day,
                transmission_chain=[observer.name],
            )
            update = self._apply_evidence(
                observer=observer,
                target_agent=actor.name,
                dimension=dimension,
                evidence=evidence,
                day=day,
                third_party=False,
            )
            if update:
                updates.append(update)
        return updates

    def record_observation(
        self,
        *,
        day: int,
        observer: "Agent",
        target_agent: str,
        dimension: str,
        value: float,
        evidence_id: str,
        public: bool = False,
    ) -> dict | None:
        source_type = "public_event" if public else "direct_observation"
        confidence = 0.70 if public else 0.80
        return self._apply_evidence(
            observer=observer,
            target_agent=target_agent,
            dimension=dimension,
            evidence=ReputationEvidence(
                evidence_id=evidence_id,
                value=value,
                confidence=confidence,
                source_type=source_type,
                source_agent=target_agent,
                day=day,
                transmission_chain=[observer.name],
            ),
            day=day,
            third_party=False,
        )

    def select_shareable_claim(
        self,
        speaker: "Agent",
        listener: "Agent",
    ) -> dict | None:
        candidates = []
        for target_name, dimensions in speaker.reputation_beliefs.items():
            if target_name in {speaker.name, listener.name}:
                continue
            for dimension, belief in dimensions.items():
                if not isinstance(belief, ReputationBelief):
                    continue
                for evidence in belief.evidence:
                    if (
                        evidence.transmission_depth >= MAX_RUMOR_DEPTH
                        or listener.name in evidence.transmission_chain
                        or abs(evidence.value) < 0.1
                    ):
                        continue
                    candidates.append(
                        (
                            abs(evidence.value) * evidence.confidence,
                            evidence.day,
                            target_name,
                            dimension,
                            evidence.evidence_id,
                            evidence,
                        )
                    )
        if not candidates:
            return None
        *_rank, evidence = max(candidates, key=lambda item: item[:-1])
        target_name = _rank[2]
        dimension = _rank[3]
        return {
            "subject_agent": target_name,
            "dimension": dimension,
            "value": evidence.value,
            "confidence": evidence.confidence,
            "evidence_id": evidence.evidence_id,
            "originating_source": evidence.source_agent,
            "source_type": evidence.source_type,
            "transmission_depth": evidence.transmission_depth,
            "transmission_chain": list(evidence.transmission_chain),
        }

    def transmit_rumor(
        self,
        *,
        day: int,
        speaker: "Agent",
        listener: "Agent",
        claim: dict | None,
    ) -> dict | None:
        if not claim:
            return None
        subject = claim.get("subject_agent", "")
        dimension = str(claim.get("dimension", ""))
        belief = speaker.reputation_beliefs.get(subject, {}).get(dimension)
        owned_evidence = None
        if isinstance(belief, ReputationBelief):
            owned_evidence = next(
                (
                    item for item in belief.evidence
                    if item.evidence_id == claim.get("evidence_id")
                ),
                None,
            )
        if owned_evidence is None:
            return None
        chain = list(owned_evidence.transmission_chain)
        depth = owned_evidence.transmission_depth
        if (
            not subject
            or not claim.get("evidence_id")
            or subject in {speaker.name, listener.name}
            or listener.name in chain
            or depth >= MAX_RUMOR_DEPTH
        ):
            return None

        teller_belief = listener.reputation_beliefs.get(speaker.name, {}).get(
            "trustworthiness"
        )
        credibility = 0.50
        if isinstance(teller_belief, ReputationBelief):
            credibility += 0.06 * teller_belief.score * teller_belief.confidence
        credibility = _clamp(credibility, 0.25, 0.65)
        confidence = min(
            SOURCE_CONFIDENCE_LIMITS["hearsay"],
            owned_evidence.confidence * credibility,
        )
        if confidence <= 0:
            return None
        evidence = ReputationEvidence(
            evidence_id=str(claim.get("evidence_id", "")),
            value=owned_evidence.value,
            confidence=confidence,
            source_type="hearsay",
            source_agent=speaker.name,
            day=day,
            transmission_depth=depth + 1,
            transmission_chain=[*chain, listener.name],
        )
        return self._apply_evidence(
            observer=listener,
            target_agent=subject,
            dimension=dimension,
            evidence=evidence,
            day=day,
            third_party=True,
        )

    @staticmethod
    def format_beliefs_for_context(
        observer: "Agent",
        target_agent: str,
        limit: int = 2,
    ) -> list[str]:
        beliefs = observer.reputation_beliefs.get(target_agent, {})
        ranked = sorted(
            (
                belief for belief in beliefs.values()
                if isinstance(belief, ReputationBelief) and abs(belief.score) >= 0.2
            ),
            key=lambda belief: abs(belief.score) * belief.confidence,
            reverse=True,
        )
        lines = []
        for belief in ranked[:limit]:
            strength = "slightly" if abs(belief.score) < 1.5 else "somewhat"
            if abs(belief.score) >= 3.0:
                strength = "strongly"
            descriptors = {
                "trustworthiness": ("trustworthy", "untrustworthy"),
                "helpfulness": ("helpful", "unhelpful"),
                "cooperativeness": ("cooperative", "uncooperative"),
                "hostility": ("hostile", "non-hostile"),
            }
            positive, negative = descriptors[belief.dimension]
            descriptor = positive if belief.score > 0 else negative
            source = (
                "direct experience"
                if belief.source_type in {"direct_interaction", "direct_observation"}
                else "secondhand information"
            )
            lines.append(
                f"The speaker believes {target_agent} is {strength} "
                f"{descriptor}, based on {source}."
            )
        return lines

    @staticmethod
    def format_rumor_claim(claim: dict | None) -> str:
        if not claim:
            return ""
        dimension = claim["dimension"]
        value = float(claim["value"])
        words = {
            "trustworthiness": ("trustworthy", "unreliable"),
            "helpfulness": ("helpful", "unhelpful"),
            "cooperativeness": ("cooperative", "uncooperative"),
            "hostility": ("hostile", "calm rather than hostile"),
        }
        descriptor = words[dimension][0 if value > 0 else 1]
        return (
            f"The speaker can share a cautious claim that "
            f"{claim['subject_agent']} seems {descriptor}; this comes from "
            "the speaker's own stored evidence and will be hearsay to the listener."
        )

    @staticmethod
    def format_rumor_dialogue(claim: dict) -> str:
        dimension = claim["dimension"]
        value = float(claim["value"])
        words = {
            "trustworthiness": ("trustworthy", "unreliable"),
            "helpfulness": ("helpful", "unhelpful"),
            "cooperativeness": ("cooperative", "uncooperative"),
            "hostility": ("hostile", "calm rather than hostile"),
        }
        descriptor = words[dimension][0 if value > 0 else 1]
        prefix = (
            "From what I saw"
            if claim.get("source_type") in {
                "direct_interaction", "direct_observation", "public_event"
            }
            else "Someone told me"
        )
        return (
            f"{prefix}, {claim['subject_agent']} seemed {descriptor}, "
            "though you should judge for yourself."
        )
