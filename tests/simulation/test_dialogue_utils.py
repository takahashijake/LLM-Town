from types import SimpleNamespace

from src.simulation.dialogue_utils import (
    clean_dialogue_text,
    fix_stale_event_reference,
    get_previous_event_keywords,
    has_rumor_marker,
    is_narration,
)


def test_clean_dialogue_text_fixes_spacing_and_activity_grammar():
    dirty = (
        "My work as a local journalist has kept me busy near the library."
        "I have been focused on check records for leads today."
    )

    cleaned = clean_dialogue_text(dirty)

    assert "library. I" in cleaned
    assert "check records" not in cleaned
    assert "checking records" in cleaned


def test_is_narration_detects_name_prefixed_dialogue():
    assert is_narration(
        conversation="Maya: I should check the records.",
        speaker_name="Maya",
        listener_name="Ethan",
    )


def test_is_narration_detects_speaker_addressing_themself():
    assert is_narration(
        conversation="Maya, I noticed some new stalls here.",
        speaker_name="Maya",
        listener_name="Ethan",
    )


def test_is_narration_detects_action_description():
    assert is_narration(
        conversation="Maya noticed Ethan looking worried.",
        speaker_name="Maya",
        listener_name="Ethan",
    )


def test_is_narration_detects_subjectless_action_summary():
    assert is_narration(
        conversation="Spoke about the art workshop she mentioned earlier.",
        speaker_name="Maya",
        listener_name="Ethan",
    )


def test_has_rumor_marker_requires_specific_marker():
    assert not has_rumor_marker(
        "I heard the poetry readings were inspiring today."
    )

    assert has_rumor_marker(
        "Someone said the vendor might be hiding something."
    )


def test_get_previous_event_keywords_only_uses_prior_days():
    history = [
        {"day": 1, "name": "Book Club"},
        {"day": 2, "name": "Library Fundraiser"},
        {"day": 3, "name": "Farmers Market"},
    ]

    keywords = get_previous_event_keywords(
        daily_event_history=history,
        current_day=3,
    )

    assert "book club" in keywords
    assert "library fundraiser" in keywords
    assert "farmers market" not in keywords


def test_fix_stale_event_reference_changes_old_today_reference():
    current_event = SimpleNamespace(name="Farmers Market")

    fixed = fix_stale_event_reference(
        conversation="The Library Fundraiser today still has people talking.",
        current_day=3,
        current_daily_event=current_event,
        daily_event_history=[
            {"day": 1, "name": "Book Club"},
            {"day": 2, "name": "Library Fundraiser"},
        ],
    )

    assert "today" not in fixed.lower()
    assert "recently" in fixed.lower()
