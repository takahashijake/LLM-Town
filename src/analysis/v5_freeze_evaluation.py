"""Integrated V5 freeze-candidate gate over the final dynamic town."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from src.analysis.causal_memory_evaluation import evaluate_causal_memory
from src.analysis.commitment_evaluation import run_commitment_evaluation
from src.analysis.crime_evaluation import run_crime_evaluation
from src.analysis.economy_evaluation import run_economy_evaluation
from src.analysis.justice_evaluation import run_justice_evaluation
from src.analysis.material_evaluation import run_material_evaluation
from src.analysis.multi_site_growth_evaluation import evaluate_multi_site_growth
from src.analysis.production_evaluation import run_production_evaluation
from src.analysis.v2_evaluation import run_v2_evaluation
from src.analysis.v3_freeze_evaluation import evaluate_v3_freeze
from src.analysis.v4_freeze_evaluation import evaluate_v4_freeze


def evaluate_v5_freeze() -> dict:
    """Cross-check frozen cores and final-world, cross-branch authority."""
    multi_site = evaluate_multi_site_growth()
    with TemporaryDirectory() as directory:
        work = Path(directory)
        with redirect_stdout(StringIO()):
            component_results = {
                "economy": run_economy_evaluation(work / "economy"),
                "materials": run_material_evaluation(work / "materials"),
                "production": run_production_evaluation(work / "production"),
                "crime": run_crime_evaluation(work / "crime"),
                "justice": run_justice_evaluation(work / "justice"),
                "commitments": run_commitment_evaluation(work / "commitments"),
                "causal_memory": evaluate_causal_memory(),
                "v2": run_v2_evaluation(work / "v2"),
                "v3": evaluate_v3_freeze(),
                "v4": evaluate_v4_freeze(),
            }

    signature = multi_site["diagnostics"].get("long_horizon_signature", {})
    phase_scenarios = multi_site.get("scenarios", {})
    scenarios = {
        "phase6_multi_site_gate_passes": multi_site["passed"],
        "all_frozen_core_gates_pass": all(
            result.get("passed", False) for result in component_results.values()
        ),
        "final_world_contains_six_provenanced_residents": (
            len(signature.get("resident_ids", ())) == 6
            and len(signature.get("migration_ids", ())) == 2
        ),
        "final_world_contains_two_provenanced_places": (
            len(signature.get("location_activation_ids", ())) == 2
        ),
        "final_world_contains_two_independent_institutions": (
            len(signature.get("formation_ids", ())) == 2
            and len(set(signature.get("employees", ()))) == 2
            and len(set(signature.get("employer_account_ids", ()))) == 2
        ),
        "final_world_preserves_single_scoped_commerce_branch": (
            len(signature.get("commerce_activation_ids", ())) == 1
            and len(signature.get("dynamic_sellers", ())) == 1
        ),
        "growth_and_economic_authority_are_jointly_deterministic": all(
            phase_scenarios.get(name, False) for name in (
                "fresh_resume_repeat_authority_matches",
                "two_finite_migrations_activate",
                "two_finite_places_activate",
                "two_institutions_form",
                "both_dynamic_jobs_work_and_receive_wages",
                "garden_procurement_production_and_sales_continue",
            )
        ),
        "cross_branch_authority_is_jointly_isolated": all(
            phase_scenarios.get(name, False) for name in (
                "institution_location_and_event_evidence_is_isolated",
                "pavilion_institution_is_noncommercial",
                "pavilion_institution_on_garden_rejected",
                "garden_institution_on_pavilion_rejected",
                "garden_commerce_on_pavilion_rejected",
                "forged_second_employment_memory_rejected",
            )
        ),
        "final_world_conserves_money_goods_and_provenance": all(
            multi_site.get("invariants", {}).get(name, False) for name in (
                "currency_conserved", "ledger_reconstructs",
                "materials_conserved", "material_history_reconstructs",
                "material_provenance_valid", "production_provenance_valid",
                "outcome_memory_isolated",
            )
        ),
        "finite_growth_stabilizes_after_exhaustion": all(
            phase_scenarios.get(name, False) for name in (
                "finite_growth_stabilizes_without_sequence_churn",
                "bounded_review_histories_remain_bounded",
            )
        ),
    }
    invariants = {
        f"{name}_gate_passes": result.get("passed", False)
        for name, result in component_results.items()
    }
    invariants["multi_site_invariants_pass"] = (
        multi_site["invariants_passed"] == multi_site["invariant_count"]
    )
    failed_scenarios = sorted(name for name, value in scenarios.items() if not value)
    failed_invariants = sorted(name for name, value in invariants.items() if not value)
    return {
        "passed": not failed_scenarios and not failed_invariants,
        "scenario_count": len(scenarios),
        "scenarios_passed": len(scenarios) - len(failed_scenarios),
        "invariant_count": len(invariants),
        "invariants_passed": len(invariants) - len(failed_invariants),
        "scenarios": scenarios,
        "invariants": invariants,
        "diagnostics": {
            "failed_scenarios": failed_scenarios,
            "failed_invariants": failed_invariants,
            "component_summaries": {
                name: {
                    "passed": result.get("passed", False),
                    "scenarios_passed": result.get("scenarios_passed"),
                    "scenario_count": result.get("scenario_count"),
                    "invariants_passed": result.get("invariants_passed"),
                    "invariant_count": result.get("invariant_count"),
                }
                for name, result in component_results.items()
            },
            "multi_site_summary": {
                "passed": multi_site["passed"],
                "scenarios_passed": multi_site["scenarios_passed"],
                "scenario_count": multi_site["scenario_count"],
                "invariants_passed": multi_site["invariants_passed"],
                "invariant_count": multi_site["invariant_count"],
            },
        },
    }
