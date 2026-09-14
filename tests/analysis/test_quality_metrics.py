from src.analysis.quality_metrics import analyze_run


def build_state() -> dict:
    return {
        "current_day": 1,
        "agents": [
            {
                "name": "Maya",
                "memory": [
                    {"type": "conversation"},
                    {"type": "daily_event"},
                    {"type": "town_arc_participation"},
                ],
                "memory_archive": [],
                "daily_journals": [{"day": 1, "summary": "A day."}],
                "needs": {"social": 60},
            }
        ],
        "relationship_scores": {"Ethan|Maya": 4},
        "relationship_events": [
            {"action": "compliment", "relationship_change": 1}
        ],
        "agent_intents": {},
        "intent_history": [{"intent_type": "socialize", "status": "succeeded"}],
        "town_arcs": [{"name": "Community Project", "status": "resolved"}],
    }


def test_analyze_run_returns_structured_quality_metrics():
    conversations = [
        {
            "day": 1,
            "hour": 8,
            "speaker": "Maya",
            "listener": "Ethan",
            "location": "cafe",
            "conversation": "Hello.",
            "action": "chat",
            "tags": ["event", "community"],
            "speaker_intent_type": "socialize",
            "speaker_intent_target_location": "cafe",
        },
        {
            "day": 1,
            "hour": 12,
            "speaker": "Maya",
            "listener": "Ethan",
            "location": "cafe",
            "conversation": "Hello.",
            "action": "chat",
            "tags": [],
            "speaker_intent_type": "socialize",
            "speaker_intent_target_location": "cafe",
        },
    ]
    events = [
        {
            "type": "activity",
            "day": 1,
            "hour": 8,
            "agent": "Ethan",
            "activity_name": "Meet residents",
            "location": "cafe",
        }
    ]
    arc_changes = [
        {
            "arc_name": "Community Project",
            "action": "cooperate",
            "old_progress": 0,
            "new_progress": 1,
            "old_tension": 2,
            "new_tension": 1,
        }
    ]

    metrics = analyze_run(conversations, build_state(), events, arc_changes)

    assert metrics["conversations"]["total"] == 2
    assert metrics["conversations"]["repeated_instances"] == 1
    assert metrics["conversations"]["repetition_rate"] == 0.5
    assert metrics["conversations"]["daily_event_rate"] == 0.5
    assert metrics["intent_followthrough"]["action_compatibility_rate"] == 1.0
    assert metrics["intent_followthrough"]["target_location_rate"] == 1.0
    assert metrics["intent_followthrough"]["actions_by_intent"] == {
        "socialize": {"chat": 2}
    }
    assert metrics["intent_followthrough"]["action_pipeline"]["final_counts"] == {
        "chat": 2
    }
    assert metrics["relationships"]["average_score"] == 4
    assert metrics["intents"]["success_rate"] == 1.0
    assert metrics["town_arcs"]["causal_changes"] == 1
    assert metrics["town_arcs"]["tension_decreases"] == 1
    assert metrics["journals"]["coverage_rate"] == 1.0


def test_compliment_quality_check_uses_documented_five_percent_floor():
    conversations = [
        {
            "conversation": f"Line {index}",
            "action": "compliment" if index == 0 else "chat",
            "tags": [],
        }
        for index in range(100)
    ]

    metrics = analyze_run(conversations, build_state())

    check = metrics["quality"]["checks"]["compliment_rate"]
    assert check["value"] == 0.01
    assert check["status"] == "warn"
    assert check["passed"] is False


def test_intent_action_compatibility_uses_only_applicable_intents():
    conversations = [
        {
            "speaker": "Maya",
            "listener": "Ethan",
            "location": "library",
            "conversation": "Could you advise me?",
            "action": "ask_for_help",
            "speaker_intent_type": "socialize",
            "speaker_intent_target_location": "cafe",
        },
        {
            "speaker": "Maya",
            "listener": "Ethan",
            "location": "cafe",
            "conversation": "Could you advise me?",
            "action": "ask_for_help",
            "speaker_intent_type": "socialize",
            "speaker_intent_target_location": "cafe",
        },
        {
            "speaker": "Maya",
            "listener": "Ethan",
            "location": "cafe",
            "conversation": "We can work together.",
            "action": "cooperate",
            "speaker_intent_type": "repair_relationship",
            "speaker_intent_target_agent": "Ethan",
        },
    ]

    metrics = analyze_run(conversations, build_state())["intent_followthrough"]

    assert metrics["conversations_with_intent"] == 3
    assert metrics["intent_action_opportunities"] == 2
    assert metrics["intent_not_applicable"] == 1
    assert metrics["compatible_actions"] == 2
    assert metrics["action_compatibility_rate"] == 1.0


def test_empty_run_marks_conversation_checks_as_no_data():
    metrics = analyze_run([], {})

    assert metrics["conversations"]["total"] == 0
    assert metrics["quality"]["checks"]["chat_rate"]["status"] == "no_data"
    assert metrics["quality"]["checks"]["chat_rate"]["passed"] is None
