"""Real model-free trajectories, independent reconstruction and hostile save checks."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import random
import time

from src.analysis.causal_inspector import trace
from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.systems.collective_projects import PROJECT_ID, WORKSHOP

DAYS = 100
SEED = 11


def engine(root: Path, name: str, config: Path, *, load: bool = False) -> SimulationEngine:
    return SimulationEngine('data/agents.json', 'data/locations.json', llm_client=FakeLLMClient(),
                            state_path=root / f'{name}.json', logs_dir=root / f'{name}-logs',
                            town_growth_path=config, simulation_seed=SEED, load_state=load)


def authoritative_signature(town: SimulationEngine) -> str:
    """Public deterministic systems and behavior; excludes legacy UUID memories."""
    payload = {name: getattr(town, name).to_dict() for name in (
        'economy', 'materials', 'town_growth', 'location_growth', 'event_ecology',
        'institution_growth', 'commerce_growth', 'collective_projects',
        'crime', 'justice', 'commitment_system', 'plan_system', 'growth_proposals')}
    payload['activities'] = [{k: r.get(k) for k in (
        'day', 'hour', 'agent_id', 'activity_id', 'location', 'source_project_id',
        'source_project_effect_id', 'civic_execution_key', 'civic_status',
        'source_event_template_id', 'source_event_occurrence_id', 'material_result_id')}
        for r in town.activity_records]
    payload['needs'] = [(a.id, a.location_id, a.needs) for a in town.agents]
    payload['relationship_scores'] = sorted((a, b, score) for (a, b), score in town.relationships.scores.items())
    payload['goals'] = [(a.id, [{k: g.to_dict().get(k) for k in (
        'id', 'category', 'priority', 'created_day', 'review_day', 'deadline_day',
        'status', 'progress', 'progress_target', 'completed_day', 'target_locations', 'target_agent')}
        for g in a.goals if hasattr(g, 'to_dict')]) for a in town.agents]
    payload['intents'] = {name: {k: intent.to_dict().get(k) for k in (
        'id', 'intent_type', 'strategy', 'parent_goal_id', 'source_goal_plan_id',
        'source_goal_plan_revision', 'target_location', 'target_agent', 'status')}
        for name, intent in town.agent_intents.items()}
    payload['town_arcs'] = [{k: arc.to_dict().get(k) for k in ('id', 'status', 'tension', 'progress')}
                            for arc in town.town_arcs]
    payload['daily_events'] = [{k: r.get(k) for k in ('day', 'template_id', 'occurrence_id', 'location_id')}
                               for r in town.daily_event_history]
    return sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def evaluate(root: Path) -> dict:
    """Write only to the explicitly selected directory; fail on any invariant."""
    root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    config_data = json.loads(Path('data/town_growth.json').read_text())
    config_data['collective_projects'] = {'enabled': True}
    config = root / 'v9-config.json'
    config.write_text(json.dumps(config_data, indent=2))
    caller_random = random.getstate()
    checks = {}
    checkpoints = {}
    try:
        random.seed(SEED)
        full = engine(root, 'uninterrupted', config)
        original_save = full.state.save

        def capture(town, day, hour, *, day_complete=False):
            original_save(town, day, hour, day_complete=day_complete)
            civic = town.collective_projects
            if not civic.projects:
                return
            labels = []
            if civic.projects[0].status == 'active' and not civic.contributions and day_complete:
                labels.append('formation')
            if len(civic.contributions) == 1 and day_complete:
                labels.append('one_contribution')
            if len(civic.contributions) == civic.policy.required_units and not civic.effects:
                labels.append('before_completion')
            if civic.effects and day_complete:
                labels.append('after_completion')
            for label in labels:
                if label not in checkpoints:
                    payload = town.state.path.read_text()
                    checkpoints[label] = json.loads(payload)
                    (root / f'{label}.json').write_text(payload)

        full.state.save = capture
        with redirect_stdout(StringIO()):
            full.run(DAYS, [8])
        project = full.collective_projects.projects[0]
        contributions = full.collective_projects.contributions
        signature = authoritative_signature(full)
        checks['all_checkpoint_states_exercised'] = set(checkpoints) == {
            'formation', 'one_contribution', 'before_completion', 'after_completion'}
        checks['incomplete_has_no_effect'] = not checkpoints['one_contribution']['collective_projects']['effects']
        checks['verified_independent_residents'] = len({c.actor_id for c in contributions}) >= 2
        checks['work_over_multiple_days'] = len({c.day for c in contributions}) >= 2
        checks['all_work_requirements_met'] = len(contributions) == 4 and project.status == 'completed'
        workshop = [r for r in full.activity_records if r.get('activity_id') == WORKSHOP]
        checks['subsequent_workshop_executed'] = bool(workshop) and min(r['day'] for r in workshop) > project.resolution_day
        checks['workshop_capacity'] = len({(r['day'], r['hour']) for r in workshop}) == len(workshop)
        checks['one_event_per_day'] = len(full.daily_event_history) == DAYS == len({r['day'] for r in full.daily_event_history})
        checks['money_conserved'] = full.economy.conservation_holds() and full.economy.ledger_reconstructs_balances()
        checks['materials_reconcile'] = full.materials.provenance_reconciles() and full.materials.material_history_reconstructs_inventories()
        before_review = full.collective_projects.to_dict()
        full.collective_projects.review(DAYS)
        full.collective_projects.review(project.resolution_day)
        checks['review_replay_no_change'] = full.collective_projects.to_dict() == before_review
        reconstruction_signatures = {}
        for label, saved in checkpoints.items():
            (root / f'resumed-{label}.json').write_text(json.dumps(saved))
            random.seed(987654)  # independent reconstruction cannot inherit the caller's stream
            resumed = engine(root, f'resumed-{label}', config, load=True)
            with redirect_stdout(StringIO()):
                resumed.run(DAYS - saved['current_day'], [8])
            reconstruction_signatures[label] = authoritative_signature(resumed)
            checks[f'resume_{label}_equivalent'] = reconstruction_signatures[label] == signature
        save = json.loads((root / 'uninterrupted.json').read_text())
        evidence = trace(save, type='project', identity=PROJECT_ID, depth=3, limit=100)
        checks['causal_work_and_effect_verified'] = {'verified_civic_work', 'project_progress',
            'unlocked_learning_activity', 'enabled_workshop_execution'} <= {e['relationship'] for e in evidence['edges']}
        checks['independent_inspection_equal'] = evidence == trace(root / 'resumed-after_completion.json',
                                                                  type='project', identity=PROJECT_ID, depth=3, limit=100)
        mutations = {
            'missing_authority': lambda s: s.pop('collective_projects'),
            'null_authority': lambda s: s.update(collective_projects=None),
            'missing_rng': lambda s: s.pop('v9_random_state'),
            'counter_rewind': lambda s: s['collective_projects'].update(last_review_day=0),
            'counter_jump': lambda s: s['collective_projects'].update(last_review_day=DAYS + 1),
            'duplicate_id': lambda s: s['collective_projects']['contributions'].append(deepcopy(s['collective_projects']['contributions'][0])),
            'other_actor': lambda s: s['collective_projects']['contributions'][0].update(actor_id='agent_001'),
            'wrong_branch': lambda s: s['collective_projects']['projects'][0].update(formation_id='institution-formation:9999'),
            'premature_effect': lambda s: s['collective_projects']['effects'][0].update(available_day=1),
            'removed_work': lambda s: s['collective_projects'].update(contributions=[]),
        }
        for name, mutate in mutations.items():
            changed = deepcopy(save)
            mutate(changed)
            (root / 'attacked.json').write_text(json.dumps(changed))
            prior_rng = random.getstate()
            try:
                engine(root, 'attacked', config, load=True)
            except (ValueError, TypeError, KeyError):
                checks[f'reject_{name}'] = random.getstate() == prior_rng
            else:
                checks[f'reject_{name}'] = False
        disabled = deepcopy(config_data)
        disabled['collective_projects'] = {'enabled': False}
        disabled_config = root / 'disabled-config.json'
        disabled_config.write_text(json.dumps(disabled))
        (root / 'attacked.json').write_text(json.dumps(save))
        try:
            engine(root, 'attacked', disabled_config, load=True)
        except ValueError:
            checks['disabled_policy_rejects_authorized_effect_save'] = True
        else:
            checks['disabled_policy_rejects_authorized_effect_save'] = False
        damaged = deepcopy(save)
        damaged['collective_projects']['contributions'][0]['actor_id'] = 'ghost'
        unresolved = trace(damaged, type='project', identity=PROJECT_ID)
        checks['forgery_withholds_civic_edges'] = not any(e['relationship'] in {
            'project_progress', 'unlocked_learning_activity'} for e in unresolved['edges'])
        result = {'schema_version': 1, 'kind': 'v9_collective_projects',
                  'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks,
                  'seed': SEED, 'days': DAYS, 'project': as_project(full),
                  'signature': signature, 'reconstruction_signatures': reconstruction_signatures,
                  'workshop_executions': len(workshop), 'elapsed_seconds': round(time.perf_counter() - started, 3)}
        (root / 'report.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
        (root / 'causal-evidence.json').write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
        (root / 'rejected-evidence.json').write_text(json.dumps(unresolved, indent=2, sort_keys=True) + '\n')
        lines = [f"Garden project activated on day {project.activation_day} at {project.location_id}."]
        lines += [f"Day {c.day}, {c.hour}:00: {c.actor_id} executed {c.execution_key}." for c in contributions]
        lines += ["The one-contribution checkpoint has no completed-project benefit.",
                  f"Verified requirements completed on day {project.resolution_day}.",
                  f"The workshop became available on day {full.collective_projects.effects[0].available_day}; {len(workshop)} subsequent sessions executed.",
                  f"Forged actor evidence was rejected; all four reconstruction signatures match: {all(checks[f'resume_{label}_equivalent'] for label in checkpoints)}."]
        (root / 'walkthrough.txt').write_text('\n'.join(lines) + '\n')
        return result
    finally:
        random.setstate(caller_random)


def as_project(town: SimulationEngine) -> dict:
    return town.collective_projects.to_dict()
