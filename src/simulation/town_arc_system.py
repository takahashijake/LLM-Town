import json
import random
from pathlib import Path

from src.agents.agent import Agent
from src.agents.memory import Memory
from src.town.town_arc import TownArc


class TownArcSystem:
    def __init__(
        self,
        town_arcs: list[TownArc],
        town_arc_change_records: list[dict],
    ):
        self.town_arcs = town_arcs
        self.town_arc_change_records = town_arc_change_records

    def get_active_town_arcs(self) -> list[TownArc]:
        return [
            arc
            for arc in self.town_arcs
            if arc.is_active()
        ]

    def create_town_arc_from_daily_event(
        self,
        day: int,
        daily_event,
    ) -> TownArc | None:
        event_tags = set(daily_event.tags)

        active_arc_names = {
            arc.name
            for arc in self.get_active_town_arcs()
        }

        if "market" in event_tags or "wealth" in event_tags or "business" in event_tags:
            if "Market Pressure" in active_arc_names:
                return None

            return TownArc(
                id=f"arc_market_pressure_day_{day}",
                name="Market Pressure",
                description=(
                    "Residents are paying closer attention to market prices, "
                    "business opportunities, and whether local merchants are acting fairly."
                ),
                status="active",
                location_id="market",
                involved_agents=[],
                tags=["market", "business", "wealth"],
                tension=2,
                progress=0,
                created_day=day,
                updated_day=day,
            )

        if "community" in event_tags or "volunteer" in event_tags or "help" in event_tags:
            if "Community Project" in active_arc_names:
                return None

            return TownArc(
                id=f"arc_community_project_day_{day}",
                name="Community Project",
                description=(
                    "Residents are becoming more involved in shared town projects, "
                    "repairs, volunteering, and public cooperation."
                ),
                status="active",
                location_id="town_square",
                involved_agents=[],
                tags=["community", "volunteer", "social"],
                tension=1,
                progress=0,
                created_day=day,
                updated_day=day,
            )

        if "learning" in event_tags or "rules" in event_tags:
            if "Public Questions" in active_arc_names:
                return None

            return TownArc(
                id=f"arc_public_questions_day_{day}",
                name="Public Questions",
                description=(
                    "Residents are asking more questions about records, rules, "
                    "local decisions, and recent town activity."
                ),
                status="active",
                location_id="library",
                involved_agents=[],
                tags=["knowledge", "rules", "learning"],
                tension=2,
                progress=0,
                created_day=day,
                updated_day=day,
            )

        return None

    def should_create_town_arc(self, day: int) -> bool:
        active_arcs = self.get_active_town_arcs()

        if not active_arcs:
            return True

        if len(active_arcs) >= 2:
            return False

        return random.random() < 0.35

    def update_town_arcs(
        self,
        day: int,
        current_daily_event,
        agents: list[Agent],
    ) -> None:
        for arc in self.get_active_town_arcs():
            if arc.updated_day == day:
                continue

            previous_tension = arc.tension
            previous_progress = arc.progress

            arc.progress += random.choice([0, 1])
            arc.tension += random.choice([-1, 0, 0, 1])
            arc.tension = max(0, min(5, arc.tension))
            arc.updated_day = day

            changed_significantly = (
                abs(arc.tension - previous_tension) >= 2
                or arc.progress > previous_progress
            )

            if day - arc.created_day >= 3 and arc.progress >= 2:
                arc.status = "resolved"
                arc.resolved_day = day

                print(
                    f"Town arc resolved: {arc.name} "
                    f"(location={arc.location_id or 'town'}, "
                    f"tension={arc.tension}, progress={arc.progress})"
                )

                self.remember_town_arc_for_all_agents(
                    day=day,
                    arc=arc,
                    reason="resolved",
                    agents=agents,
                )

            elif changed_significantly:
                changes = []

                if arc.tension != previous_tension:
                    changes.append(f"tension {previous_tension}->{arc.tension}")

                if arc.progress != previous_progress:
                    changes.append(f"progress {previous_progress}->{arc.progress}")

                change_text = ", ".join(changes) if changes else "no major numeric change"

                print(
                    f"Town arc updated: {arc.name} "
                    f"({change_text})"
                )

                self.remember_town_arc_for_all_agents(
                    day=day,
                    arc=arc,
                    reason="updated",
                    agents=agents,
                )

        if current_daily_event and self.should_create_town_arc(day):
            new_arc = self.create_town_arc_from_daily_event(
                day=day,
                daily_event=current_daily_event,
            )

            if new_arc:
                self.town_arcs.append(new_arc)

                print(
                    f"Town arc created: {new_arc.name} "
                    f"(location={new_arc.location_id or 'town'}, "
                    f"tension={new_arc.tension}, progress={new_arc.progress})"
                )

                self.remember_town_arc_for_all_agents(
                    day=day,
                    arc=new_arc,
                    reason="created",
                    agents=agents,
                )

    def create_town_arc_memory(self, day: int, arc: TownArc) -> Memory:
        return Memory(
            day=day,
            hour=0,
            type="town_arc",
            description=(
                f"Town arc: {arc.name}. {arc.description} "
                f"Status: {arc.status}. Tension: {arc.tension}. Progress: {arc.progress}."
            ),
            participants=arc.involved_agents,
            location=arc.location_id or "town",
            importance=3,
            sentiment=arc.tension,
            tags=["town_arc", arc.id] + arc.tags,
        )

    def remember_town_arc_for_all_agents(
        self,
        day: int,
        arc: TownArc,
        reason: str,
        agents: list[Agent],
    ) -> None:
        arc_memory = Memory(
            day=day,
            hour=0,
            type="town_arc",
            description=(
                f"Town arc {reason}: {arc.name}. {arc.description} "
                f"Status: {arc.status}. Tension: {arc.tension}. Progress: {arc.progress}."
            ),
            participants=arc.involved_agents,
            location=arc.location_id or "town",
            importance=3,
            sentiment=arc.tension,
            tags=["town_arc", reason, arc.id] + arc.tags,
        )

        for agent in agents:
            should_remember = reason in {"created", "resolved"}

            if not should_remember:
                agent_location = getattr(agent, "location_id", None)
                agent_activity_tags = set(getattr(agent, "current_activity_tags", []))
                arc_tags = set(arc.tags)

                should_remember = (
                    agent_location == arc.location_id
                    or bool(agent_activity_tags & arc_tags)
                    or agent.name in arc.involved_agents
                )

            if should_remember:
                agent.remember(arc_memory)

    def get_relevant_town_arcs_for_context(
        self,
        location_id: str,
    ) -> list[dict]:
        relevant_arcs = []

        for arc in self.get_active_town_arcs():
            if arc.location_id and arc.location_id != location_id:
                continue

            relevant_arcs.append(
                {
                    "id": arc.id,
                    "name": arc.name,
                    "description": arc.description,
                    "status": arc.status,
                    "location_id": arc.location_id,
                    "tags": arc.tags,
                    "tension": arc.tension,
                    "progress": arc.progress,
                }
            )

        return relevant_arcs[:2]

    def apply_conversation_to_town_arcs(
        self,
        day: int,
        location_id: str,
        speaker: Agent,
        listener: Agent,
        action: str,
        conversation_tags: list[str],
    ) -> None:
        tags = set(conversation_tags or [])

        for arc in self.get_active_town_arcs():
            arc_tags = set(arc.tags)

            is_relevant = (
                location_id == arc.location_id
                or bool(tags & arc_tags)
            )

            if not is_relevant:
                continue

            old_progress = arc.progress
            old_tension = arc.tension

            if action in {"cooperate", "offer_help"}:
                arc.progress = min(5, arc.progress + 1)
                arc.tension = max(0, arc.tension - 1)

            elif action == "ask_for_help":
                arc.progress = min(5, arc.progress + 1)

            elif action == "apologize":
                arc.tension = max(0, arc.tension - 1)

            elif action in {"share_rumor", "argue", "insult", "storm_off"}:
                arc.tension = min(5, arc.tension + 1)

            else:
                continue

            for agent_name in [speaker.name, listener.name]:
                if agent_name not in arc.involved_agents:
                    arc.involved_agents.append(agent_name)

            if arc.progress != old_progress or arc.tension != old_tension:
                arc.updated_day = day

                record = {
                    "day": day,
                    "arc_id": arc.id,
                    "arc_name": arc.name,
                    "location": location_id,
                    "speaker": speaker.name,
                    "listener": listener.name,
                    "action": action,
                    "old_progress": old_progress,
                    "new_progress": arc.progress,
                    "old_tension": old_tension,
                    "new_tension": arc.tension,
                    "tags": conversation_tags,
                }

                self.town_arc_change_records.append(record)

                arc_change_log = Path("logs/town_arc_changes.jsonl")
                arc_change_log.parent.mkdir(parents=True, exist_ok=True)

                with arc_change_log.open("a", encoding="utf-8") as file:
                    file.write(json.dumps(record) + "\n")

                arc_memory = Memory(
                    day=day,
                    hour=0,
                    type="town_arc_participation",
                    description=(
                        f"{speaker.name} and {listener.name} affected the town arc '{arc.name}' "
                        f"through action '{action}'. "
                        f"Progress changed from {old_progress} to {arc.progress}; "
                        f"tension changed from {old_tension} to {arc.tension}."
                    ),
                    participants=[speaker.name, listener.name],
                    location=location_id,
                    importance=3,
                    sentiment=arc.tension,
                    tags=["town_arc", "participation", arc.id, action] + arc.tags,
                )

                speaker.remember(arc_memory)
                listener.remember(arc_memory)

    def adjust_action_weights_for_town_arcs(
        self,
        weights: dict[str, int],
        location_id: str,
        conversation_tags: list[str] | None = None,
    ) -> dict[str, int]:
        adjusted = dict(weights)
        tags = set(conversation_tags or [])

        relevant_arcs = self.get_relevant_town_arcs_for_context(location_id)

        if not relevant_arcs:
            return adjusted

        arc_tags = set()

        for arc in relevant_arcs:
            arc_tags.update(arc.get("tags", []))

        # Community arcs should produce more helping/cooperation.
        if {"community", "volunteer", "social"} & arc_tags:
            if "cooperate" in adjusted:
                adjusted["cooperate"] += 2
            if "offer_help" in adjusted:
                adjusted["offer_help"] += 2
            if "ask_for_help" in adjusted:
                adjusted["ask_for_help"] += 1

        # Market pressure should produce some questions, rumors, and disagreement.
        if {"market", "business", "wealth"} & arc_tags:
            if "ask_for_help" in adjusted:
                adjusted["ask_for_help"] += 2
            if "share_rumor" in adjusted:
                adjusted["share_rumor"] += 1
            if "argue" in adjusted:
                adjusted["argue"] += 1
            if "cooperate" in adjusted:
                adjusted["cooperate"] += 1

        # Public questions should produce investigation/help-seeking.
        if {"knowledge", "rules", "learning"} & arc_tags:
            if "ask_for_help" in adjusted:
                adjusted["ask_for_help"] += 2
            if "cooperate" in adjusted:
                adjusted["cooperate"] += 1
            if "share_rumor" in adjusted:
                adjusted["share_rumor"] += 1

        return adjusted
        