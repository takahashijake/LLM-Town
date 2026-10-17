"""Bounded civic work authority. Prose, agreements and inspector reports grant no work."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import re
from typing import TYPE_CHECKING, TypeVar, Iterator

if TYPE_CHECKING:
    from src.agents.agent import Agent
    from src.systems.institution_growth import InstitutionGrowthSystem
    from src.town.location import Location
    from src.systems.town_growth import TownGrowthSystem

Record = TypeVar("Record")

from src.behavior.activity import Activity

PROJECT_ID = 'civic-project:garden_learning'
TEMPLATE = 'garden_learning'
WORK = 'civic_garden_prepare'
WORKSHOP = 'civic_garden_workshop'
EFFECT_ID = 'civic-effect:garden_learning'


def integer(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


@dataclass(frozen=True)
class ProjectPolicy:
    enabled: bool = False
    required_units: int = 4
    minimum_residents: int = 2
    lifetime_days: int = 21
    daily_capacity: int = 1

    def __post_init__(self) -> None:
        if (type(self.enabled) is not bool
                or not integer(self.required_units, 2, 16)
                or not integer(self.minimum_residents, 2, 8)
                or self.minimum_residents > self.required_units
                or not integer(self.lifetime_days, 2, 60)
                or not integer(self.daily_capacity, 1, 4)):
            raise ValueError('invalid collective project policy')

    @classmethod
    def from_config(cls, config: dict) -> ProjectPolicy:
        if type(config) is not dict or not set(config) <= set(cls.__dataclass_fields__):
            raise ValueError('invalid collective project configuration')
        return cls(**config)


@dataclass(frozen=True)
class Project:
    id: str
    template_id: str
    formation_id: str
    institution_id: str
    location_id: str
    activation_day: int
    deadline_day: int
    eligible_actor_ids: tuple[str, ...]
    status: str = 'active'
    resolution_day: int | None = None


@dataclass(frozen=True)
class Contribution:
    id: str
    project_id: str
    actor_id: str
    location_id: str
    day: int
    hour: int
    activity_index: int
    execution_key: str


@dataclass(frozen=True)
class ProjectEffect:
    id: str
    project_id: str
    location_id: str
    available_day: int
    activity_id: str = WORKSHOP


def execution_key(actor: str, day: int, hour: int) -> str:
    return f'civic-execution:{actor}:{day}:{hour}'


def decode_record(cls: type[Record], row: dict) -> Record:
    if type(row) is not dict or set(row) != set(cls.__dataclass_fields__):
        raise ValueError('invalid collective project record schema')
    if cls is Project:
        row = dict(row)
        if type(row['eligible_actor_ids']) not in (list, tuple):
            raise ValueError('invalid civic eligibility witness')
        row['eligible_actor_ids'] = tuple(row['eligible_actor_ids'])
    return cls(**row)


def validate_authority(state: dict, policy: ProjectPolicy, formations: list[dict],
                       agent_ids: set[str], location_ids: set[str],
                       activities: list[dict], arrival_days: dict[str, int] | None = None) -> None:
    """Pure validation shared by restoration and read-only inspection."""
    if type(activities) is not list or any(type(row) is not dict for row in activities):
        raise ValueError('invalid civic activity history')
    arrival_days = arrival_days or {}
    if (type(state) is not dict or set(state) != {
            'schema_version', 'policy', 'projects', 'contributions', 'effects', 'last_review_day'}
            or type(state['schema_version']) is not int or state['schema_version'] != 1
            or type(state['policy']) is not dict
            or set(state['policy']) != set(ProjectPolicy.__dataclass_fields__)
            or ProjectPolicy.from_config(state['policy']) != policy
            or not integer(state['last_review_day'], 0, 10**9)):
        raise ValueError('invalid collective project authority')
    for key, cap in [('projects', 1), ('contributions', policy.required_units), ('effects', 1)]:
        if type(state[key]) is not list or len(state[key]) > cap:
            raise ValueError('collective project capacity exceeded')
    projects = [decode_record(Project, row) for row in state['projects']]
    contributions = [decode_record(Contribution, row) for row in state['contributions']]
    effects = [decode_record(ProjectEffect, row) for row in state['effects']]
    if not policy.enabled and (projects or contributions or effects):
        raise ValueError('disabled policy contains civic authority')
    project = projects[0] if projects else None
    if project:
        formation = next((r for r in formations if r.get('id') == project.formation_id), {})
        if (project.id != PROJECT_ID or project.template_id != TEMPLATE
                or project.location_id != 'community_garden'
                or project.location_id not in location_ids
                or formation.get('institution_key') != 'community_garden_stewardship'
                or formation.get('status') != 'activated'
                or formation.get('institution_id') != project.institution_id
                or formation.get('location_id') != project.location_id
                or not integer(formation.get('activation_day'), 1, 10**9)
                or not integer(project.activation_day, 1, state['last_review_day'])
                or formation['activation_day'] > project.activation_day
                or project.deadline_day != project.activation_day + policy.lifetime_days
                or type(project.deadline_day) is not int
                or type(project.status) is not str
                or project.status not in {'active', 'completed', 'expired', 'cancelled'}
                or not policy.minimum_residents <= len(project.eligible_actor_ids) <= 64
                or any(type(a) is not str or re.fullmatch(r'[A-Za-z0-9_:./|\-]{1,200}', a) is None
                       or a not in agent_ids for a in project.eligible_actor_ids)
                or tuple(sorted(a for a in agent_ids if arrival_days.get(a, 0) <= project.activation_day)[:64])
                != project.eligible_actor_ids):
            raise ValueError('invalid project eligibility binding')
    seen = set()
    indices = set()
    actor_days = set()
    daily_counts = {}
    previous = None
    for c in contributions:
        if (not project or c.project_id != project.id
                or type(c.actor_id) is not str or c.actor_id not in project.eligible_actor_ids
                or c.location_id != project.location_id
                or not integer(c.day, project.activation_day + 1, project.deadline_day)
                or not integer(c.hour, 0, 23)
                or not integer(c.activity_index, 0, len(activities) - 1)
                or c.execution_key != execution_key(c.actor_id, c.day, c.hour)
                or c.id != f'civic-contribution:{c.execution_key}'
                or c.id in seen or c.activity_index in indices or (c.actor_id, c.day) in actor_days
                or (previous is not None and (c.day, c.hour, c.actor_id) <= previous)):
            raise ValueError('invalid contribution identity or chronology')
        row = activities[c.activity_index]
        if (row.get('type') != 'activity' or row.get('activity_id') != WORK
                or row.get('agent_id') != c.actor_id or row.get('location') != c.location_id
                or type(row.get('day')) is not int or row['day'] != c.day
                or type(row.get('hour')) is not int or row['hour'] != c.hour
                or row.get('source_project_id') != project.id
                or row.get('civic_execution_key') != c.execution_key
                or row.get('civic_status') != 'verified'):
            raise ValueError('missing or mismatched contribution execution')
        seen.add(c.id)
        indices.add(c.activity_index)
        actor_days.add((c.actor_id, c.day))
        daily_counts[c.day] = daily_counts.get(c.day, 0) + 1
        if daily_counts[c.day] > policy.daily_capacity:
            raise ValueError('project daily capacity exceeded')
        previous = (c.day, c.hour, c.actor_id)
    if len(contributions) == policy.required_units and (
        len({c.actor_id for c in contributions}) < policy.minimum_residents
        or len({c.day for c in contributions}) < 2
    ):
        raise ValueError('work capacity consumed without required participation')
    met = (len(contributions) == policy.required_units
           and len({c.actor_id for c in contributions}) >= policy.minimum_residents
           and len({c.day for c in contributions}) >= 2)
    if project:
        if project.status == 'active':
            if project.resolution_day is not None or effects or project.deadline_day < state['last_review_day']:
                raise ValueError('invalid active project')
            if met and contributions[-1].day <= state['last_review_day']:
                raise ValueError('unprocessed project completion')
        else:
            if (not integer(project.resolution_day, project.activation_day + 1,
                            state['last_review_day'] + (project.status == 'cancelled'))
                    or any(c.day > project.resolution_day for c in contributions)):
                raise ValueError('invalid terminal project chronology')
            if project.status == 'completed':
                if (not met or project.resolution_day != contributions[-1].day
                        or effects != [ProjectEffect(EFFECT_ID, project.id, project.location_id,
                                                     project.resolution_day + 1)]):
                    raise ValueError('premature or mismatched project effect')
            elif effects or (project.status == 'expired' and project.resolution_day != project.deadline_day + 1):
                raise ValueError('invalid failed project effect')
    elif contributions or effects:
        raise ValueError('orphan civic evidence')
    # A missing section or a removed contribution must not silently erase authority.
    verified = [r for r in activities if r.get('civic_status') == 'verified' and r.get('source_project_id')]
    if (len(verified) != len(contributions)
            or any(r.get('civic_execution_key') not in {c.execution_key for c in contributions} for r in verified)):
        raise ValueError('unreconciled civic execution history')
    workshop_ticks = set()
    for row in activities:
        if row.get('activity_id') == WORK and row.get('civic_status') != 'verified':
            raise ValueError('unverified civic work history')
        if row.get('activity_id') == WORKSHOP and not row.get('source_project_effect_id'):
            raise ValueError('unbound workshop history')
        if row.get('source_project_effect_id'):
            if (not effects or row.get('source_project_effect_id') != EFFECT_ID
                    or row.get('activity_id') != WORKSHOP
                    or row.get('location') != effects[0].location_id
                    or row.get('agent_id') not in agent_ids
                    or not integer(row.get('day'), max(effects[0].available_day,
                                                     arrival_days.get(row.get('agent_id'), 0) + 1),
                                   state['last_review_day'] + 1)
                    or not integer(row.get('hour'), 0, 23)
                    or row.get('civic_execution_key') != execution_key(row.get('agent_id'), row.get('day'), row.get('hour'))
                    or row.get('civic_status') != 'available_effect'
                    or (row.get('day'), row.get('hour')) in workshop_ticks):
                raise ValueError('unauthorized workshop history')
            workshop_ticks.add((row['day'], row['hour']))


class CollectiveProjectSystem:
    """One finite project; activity execution and end-of-day review own transitions."""

    def __init__(self, policy: ProjectPolicy, *, institutions: InstitutionGrowthSystem, agents: list[Agent],
                 locations: list[Location], activity_records: list[dict], state: dict | None = None,
                 town_growth: TownGrowthSystem | None = None):
        self.policy = policy
        self.town_growth = town_growth
        self.institutions = institutions
        self.agents = agents
        self.locations = locations
        self.activities = activity_records
        self.projects: list[Project] = []
        self.contributions: list[Contribution] = []
        self.effects: list[ProjectEffect] = []
        self.last_review_day = 0
        self._offers: dict[tuple[str, int, int], tuple[Activity, tuple]] = {}
        if state is not None:
            self._validate(state)
            self.projects = [decode_record(Project, r) for r in state['projects']]
            self.contributions = [decode_record(Contribution, r) for r in state['contributions']]
            self.effects = [decode_record(ProjectEffect, r) for r in state['effects']]
            self.last_review_day = state['last_review_day']
        else:
            self._validate(self.to_dict())

    def _validate(self, state: dict) -> None:
        validate_authority(state, self.policy,
                           [asdict(r) for r in self.institutions.formation_records],
                           {a.id for a in self.agents}, {l.id for l in self.locations}, self.activities,
                           {r.agent_id: r.activation_day for r in self.town_growth.migration_records
                            if r.status == 'activated'} if self.town_growth else {})

    def to_dict(self) -> dict:
        return {'schema_version': 1, 'policy': asdict(self.policy),
                'projects': [asdict(p) for p in self.projects],
                'contributions': [asdict(c) for c in self.contributions],
                'effects': [asdict(e) for e in self.effects],
                'last_review_day': self.last_review_day}

    def review(self, day: int) -> None:
        if not integer(day, 1, 10**9):
            raise ValueError('invalid civic review day')
        if not self.policy.enabled or day <= self.last_review_day:
            return
        if any(c.day > day for c in self.contributions):
            raise ValueError('review predates execution')
        if not self.projects:
            eligible = sorted((r for r in self.institutions.formation_records
                               if r.status == 'activated' and r.activation_day <= day
                               and r.institution_key == 'community_garden_stewardship'
                               and r.location_id == 'community_garden'
                               and r.location_id in {l.id for l in self.locations}), key=lambda r: r.id)
            if eligible and len({a.id for a in self.agents}) >= self.policy.minimum_residents:
                r = eligible[0]
                self.projects = [Project(PROJECT_ID, TEMPLATE, r.id, r.institution_id,
                                         r.location_id, day, day + self.policy.lifetime_days,
                                         tuple(sorted({a.id for a in self.agents})[:64]))]
        elif self.projects[0].status == 'active':
            p = self.projects[0]
            met = (len(self.contributions) == self.policy.required_units
                   and len({c.actor_id for c in self.contributions}) >= self.policy.minimum_residents
                   and len({c.day for c in self.contributions}) >= 2)
            if met and day != self.contributions[-1].day:
                raise ValueError('completion must review execution day')
            if met:
                self.projects = [replace(p, status='completed', resolution_day=day)]
                self.effects = [ProjectEffect(EFFECT_ID, p.id, p.location_id, day + 1)]
            elif day > p.deadline_day:
                self.projects = [replace(p, status='expired', resolution_day=p.deadline_day + 1)]
        self.last_review_day = day
        self._offers.clear()

    def cancel(self, project_id: str, day: int) -> None:
        if (project_id != PROJECT_ID or not self.projects
                or self.projects[0].status != 'active'
                or not integer(day, max(self.last_review_day, self.projects[0].activation_day + 1),
                               min(self.last_review_day + 1, self.projects[0].deadline_day))):
            raise ValueError('project cannot be cancelled')
        self.projects = [replace(self.projects[0], status='cancelled', resolution_day=day)]
        self._offers.clear()

    def _tick_records(self, day: int, hour: int) -> Iterator[dict]:
        for row in reversed(self.activities):
            if (row.get('day'), row.get('hour')) != (day, hour):
                break
            yield row

    def _can_contribute(self, actor_id: str, day: int) -> bool:
        if not self.projects:
            return False
        p = self.projects[0]
        today = [c for c in self.contributions if c.day == day]
        remaining = self.policy.required_units - len(self.contributions)
        distinct = {c.actor_id for c in self.contributions}
        reserve = self.policy.minimum_residents - len(distinct)
        return (p.status == 'active' and actor_id in p.eligible_actor_ids
                and p.activation_day < day <= p.deadline_day
                and day == self.last_review_day + 1
                and remaining > 0 and len(today) < self.policy.daily_capacity
                and not any(c.actor_id == actor_id for c in today)
                and not (actor_id in distinct and remaining <= reserve)
                and not (remaining == 1 and today and len({c.day for c in self.contributions}) == 1))

    def opportunities(self, agent: Agent, day: int, hour: int) -> list[Activity]:
        if (not self.policy.enabled or not any(agent is resident for resident in self.agents)
                or type(day) is not int or day != self.last_review_day + 1
                or not integer(hour, 0, 23)):
            return []
        # Keep ephemeral offers bounded by population, even over long histories.
        self._offers = {k: v for k, v in self._offers.items() if k[1:] == (day, hour)}
        if len(self._offers) >= 64 and (agent.id, day, hour) not in self._offers:
            return []
        activity = None
        if self.projects:
            p = self.projects[0]
            if self._can_contribute(agent.id, day):
                activity = Activity(WORK, 'Prepare the garden learning program', p.location_id,
                                    'Contribute a work session to an active civic project.',
                                    ['community', 'volunteer'], source_project_id=p.id)
        if activity is None and self.effects and day >= self.effects[0].available_day:
            effect = self.effects[0]
            used = any(r.get('source_project_effect_id') == effect.id
                       for r in self._tick_records(day, hour))
            if not used:
                activity = Activity(WORKSHOP, 'Learn at the community garden workshop', effect.location_id,
                                    'A completed civic project made this learning opportunity available.',
                                    ['knowledge', 'learning'], source_project_effect_id=effect.id)
        if activity:
            self._offers[(agent.id, day, hour)] = (activity, (activity.id, activity.location_id,
                                                         activity.source_project_id, activity.source_project_effect_id, tuple(activity.tags)))
            return [activity]
        return []

    def execute(self, agent: Agent, activity: Activity, record: dict, day: int, hour: int) -> bool:
        """Accept only the executor's exact offered activity and appended record."""
        offer = self._offers.pop((agent.id, day, hour), None)
        if (not integer(day, 1, 10**9) or not integer(hour, 0, 23)
                or type(record.get('day')) is not int or type(record.get('hour')) is not int
                or offer is None or offer[0] is not activity
                or offer[1] != (activity.id, activity.location_id,
                                activity.source_project_id, activity.source_project_effect_id, tuple(activity.tags))
                or not any(agent is resident for resident in self.agents) or not self.activities
                or self.activities[-1] is not record or agent.location_id != activity.location_id
                or record.get('type') != 'activity'
                or record.get('source_project_id') != activity.source_project_id
                or record.get('source_project_effect_id') != activity.source_project_effect_id
                or record.get('agent_id') != agent.id or record.get('day') != day
                or record.get('hour') != hour or record.get('activity_id') != activity.id
                or record.get('location') != activity.location_id):
            return False
        if activity.source_project_id:
            p = self.projects[0]
            if (activity.id != WORK or activity.source_project_id != p.id
                    or activity.location_id != p.location_id
                    or not self._can_contribute(agent.id, day)
                    or record.get('source_project_id') != p.id):
                return False
            key = execution_key(agent.id, day, hour)
            c = Contribution(f'civic-contribution:{key}', p.id, agent.id, p.location_id,
                             day, hour, len(self.activities) - 1, key)
            self.contributions.append(c)
            self.contributions.sort(key=lambda c: (c.day, c.hour, c.actor_id))
            record['civic_execution_key'] = key
            record['civic_status'] = 'verified'
            return True
        if activity.source_project_effect_id and self.effects:
            e = self.effects[0]
            valid = (activity.id == WORKSHOP and activity.location_id == e.location_id
                    and activity.source_project_effect_id == e.id
                    and record.get('source_project_effect_id') == e.id and day >= e.available_day
                    and not any(r.get('source_project_effect_id') == e.id
                                for r in self._tick_records(day, hour) if r is not record))
            if valid:
                record['civic_execution_key'] = execution_key(agent.id, day, hour)
                record['civic_status'] = 'available_effect'
            return valid
        return False

    def signature(self) -> str:
        return sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
