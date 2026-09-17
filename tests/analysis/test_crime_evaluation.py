from src.analysis.crime_evaluation import run_crime_evaluation


def test_crime_evaluation_passes_and_is_deterministic(tmp_path):
    first = run_crime_evaluation(tmp_path / "one")
    second = run_crime_evaluation(tmp_path / "two")
    assert first == second
    assert first["passed"] is True
    assert all(first["invariants"].values())
    assert first["counts"]["incidents_created"] == 2
    assert first["counts"]["unauthorized_transfers"] == 2
    assert first["counts"]["hearsay_records"] == 1
    assert first["failed_attempts"] == {
        "insufficient_stock": "insufficient_stock",
        "location_mismatch": "actor_not_present",
        "resume_replay": "duplicate_event",
    }

