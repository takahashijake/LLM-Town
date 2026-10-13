"""Optional model-free persistence observations for the existing benchmark."""
from __future__ import annotations

import json
from pathlib import Path
import random
import time
from typing import TYPE_CHECKING

from src.analysis.collective_project_evaluation import authoritative_signature
from src.analysis.observatory import checkpoint, canonical

if TYPE_CHECKING:
    from src.simulation.engine import SimulationEngine


def configure_profile(profile: str, run_dir: Path, seed: int) -> dict:
    """Reuse trusted release configurations; never accept provider code from a save."""
    if profile == 'v6':
        from src.analysis.v6_freeze_evaluation import MultiBranchProvider, write_config
        path = write_config(run_dir)
        provider = MultiBranchProvider()
    else:
        data = json.loads(Path('data/town_growth.json').read_text())
        data['collective_projects'] = {'enabled': profile == 'v9'}
        path = run_dir / 'profile-config.json'
        path.write_text(json.dumps(data))
        provider = None
    return {'town_growth_path': path, 'growth_proposal_provider': provider,
            'simulation_seed': seed}


class PersistenceObservations:
    """Aggregate checkpoint timings and public counts, retaining all authority."""

    def __init__(self, town: SimulationEngine) -> None:
        self.town = town
        self.samples: list[dict] = []
        self.save_seconds = 0.0
        self.save_count = 0
        original = town.state.save

        def observed_save(engine, day, hour, *, day_complete=False):
            started = time.perf_counter()
            original(engine, day, hour, day_complete=day_complete)
            self.save_seconds += time.perf_counter() - started
            self.save_count += 1
            if day_complete:
                self.samples.append({
                    'day': day, 'state_bytes': engine.state.path.stat().st_size,
                    'population': len(engine.agents), 'locations': len(engine.locations),
                    'institutions': len(engine.institution_growth.formation_records),
                    'events': len(engine.daily_event_history),
                    'transactions': len(engine.economy.ledger),
                    'activities': len(engine.activity_records),
                    'contributions': len(engine.collective_projects.contributions),
                })
        town.state.save = observed_save

    def finish(self, reconstruct) -> dict:
        """Measure reconstruction/projection and gate identity preservation only."""
        town = self.town
        before_bytes = town.state.path.read_bytes()
        before_rng = random.getstate()
        signature = authoritative_signature(town)
        try:
            started = time.perf_counter()
            restored = reconstruct()
            load_seconds = time.perf_counter() - started
            matches = authoritative_signature(restored) == signature
        finally:
            random.setstate(before_rng)
        started = time.perf_counter()
        report = checkpoint(town.state.path)
        projection_seconds = time.perf_counter() - started
        unchanged = town.state.path.read_bytes() == before_bytes
        try:
            import resource
        except ImportError:
            rss = None
        else:
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if not matches or not unchanged:
            raise ValueError('benchmark reconstruction changed authoritative state or input')
        return {
            'save_count': self.save_count, 'save_seconds': self.save_seconds,
            'reconstruction_seconds': load_seconds,
            'public_projection_seconds': projection_seconds,
            'public_projection_bytes': len(canonical(report)),
            'process_peak_rss_native_units': rss,
            'authority_signature': signature, 'reconstruction_matches': matches,
            'inspection_preserves_input': unchanged, 'daily_samples': self.samples,
            'timing_policy': 'Observations only; no absolute wall-clock gate. RSS is process lifetime peak.',
        }
