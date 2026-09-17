from src.agents.agent import Agent
from src.behavior.planner import ActivityPlanner
from src.utils.logger import TownLogger


class ActivitySystem:
    def __init__(
        self,
        activity_planner: ActivityPlanner,
        logger: TownLogger,
        activity_records: list[dict],
        economy_system=None,
        material_system=None,
        crime_system=None,
    ):
        self.activity_planner = activity_planner
        self.logger = logger
        self.activity_records = activity_records
        self.economy_system = economy_system
        self.material_system = material_system
        self.crime_system = crime_system

    def get_activity_need_effects(self, activity) -> dict[str, int]:
        effects_by_tag = {
            "wealth": {"wealth": 3},
            "business": {"wealth": 2},
            "market": {"wealth": 1},
            "social": {"social": 2},
            "relationship": {"social": 2},
            "community": {"social": 1},
            "volunteer": {"social": 1},
            "knowledge": {"knowledge": 2},
            "learning": {"knowledge": 2},
            "journalism": {"knowledge": 2},
            "accounting": {"knowledge": 2},
        }

        effects = {}

        for tag in activity.tags:
            for need, amount in effects_by_tag.get(tag, {}).items():
                effects[need] = effects.get(need, 0) + amount

        return effects

    def log_activity_event(
        self,
        day: int,
        hour: int,
        agent: Agent,
        activity,
    ) -> None:
        activity_record = {
            "type": "activity",
            "day": day,
            "hour": hour,
            "agent": agent.name,
            "activity_id": activity.id,
            "activity_name": activity.name,
            "location": activity.location_id,
            "reason": activity.reason,
            "tags": activity.tags,
        }

        self.activity_records.append(activity_record)
        self.logger.log_event(activity_record)

    def run_agent_activities(
        self,
        agents: list[Agent],
        location_ids: list[str],
        day: int,
        hour: int,
        current_daily_event,
        agent_intents: dict,
    ) -> None:
        completed_activities = []
        for agent in agents:
            agent.decay_needs()

            activity = self.activity_planner.choose_activity(
                agent=agent,
                location_ids=location_ids,
                current_day=day,
                hour=hour,
                daily_event=current_daily_event,
                current_intent=agent_intents.get(agent.name),
            )

            agent.set_activity(activity)
            self.log_activity_event(day, hour, agent, activity)

            activity_need_effects = self.get_activity_need_effects(activity)

            for need, amount in activity_need_effects.items():
                agent.satisfy_need(need, amount)

            if self.economy_system is not None:
                self.economy_system.process_activity(
                    agent,
                    activity,
                    day=day,
                    hour=hour,
                )

            if self.material_system is not None:
                self.material_system.process_activity(
                    agent,
                    activity,
                    day=day,
                    hour=hour,
                )

            completed_activities.append((agent, activity))

            print(
                f"{agent.name} chooses activity: {activity.name} "
                f"at {activity.location_id} ({activity.reason})"
            )

        # Crime opportunity depends on everyone's authoritative location for
        # this tick, so evaluate it only after every activity has been chosen.
        if self.crime_system is not None:
            for agent, activity in completed_activities:
                self.crime_system.process_activity(
                    agent,
                    activity,
                    agents=agents,
                    day=day,
                    hour=hour,
                )
