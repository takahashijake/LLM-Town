from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine
from src.agents.intent import AgentIntent
from src.simulation.dialogue_utils import has_rumor_marker

def build_engine():
    return SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        load_state=False,
        llm_client=FakeLLMClient(),
    )


def test_choose_suggested_action_returns_chat_when_only_chat_allowed():
    engine = build_engine()

    suggested_action = engine.choose_suggested_action(
        ["chat"],
        "neutral",
    )

    assert suggested_action == "chat"


def test_choose_suggested_action_returns_allowed_action():
    engine = build_engine()

    allowed_actions = ["chat", "compliment", "offer_help"]

    for _ in range(20):
        suggested_action = engine.choose_suggested_action(
            allowed_actions,
            "neutral",
        )

        assert suggested_action in allowed_actions


def test_choose_suggested_action_handles_empty_actions():
    engine = build_engine()

    suggested_action = engine.choose_suggested_action(
        [],
        "neutral",
    )

    assert suggested_action == "chat"


def test_choose_suggested_action_returns_allowed_action_for_neutral():
    engine = build_engine()

    allowed_actions = [
        "chat",
        "compliment",
        "offer_help",
        "ask_for_help",
        "cooperate",
        "share_rumor",
    ]

    for _ in range(20):
        suggested_action = engine.choose_suggested_action(
            allowed_actions,
            "neutral",
        )

        assert suggested_action in allowed_actions


def test_choose_suggested_action_does_not_suggest_cooperate_when_tense_if_not_allowed():
    engine = build_engine()

    allowed_actions = ["chat", "apologize", "argue", "storm_off"]

    for _ in range(20):
        suggested_action = engine.choose_suggested_action(
            allowed_actions,
            "tense",
        )

        assert suggested_action in allowed_actions
        assert suggested_action != "cooperate"

def test_repair_intent_increases_apology_weight_for_target():
    engine = build_engine()

    intent = AgentIntent(
        agent_name="Maya",
        intent_type="repair_relationship",
        target_agent="Carlos",
        target_location=None,
        description="Maya wants to repair her relationship with Carlos.",
        created_day=1,
        expires_day=3,
        priority=5,
    )

    base_weights = {
        "chat": 8,
        "apologize": 1,
        "argue": 2,
        "offer_help": 1,
    }

    adjusted = engine.adjust_action_weights_for_intent(
        weights=base_weights,
        intent=intent,
        listener_name="Carlos",
    )

    assert adjusted["apologize"] > base_weights["apologize"]
    assert adjusted["offer_help"] > base_weights["offer_help"]
    assert adjusted["argue"] < base_weights["argue"]


def test_targeted_intent_does_not_affect_non_target_listener():
    engine = build_engine()

    intent = AgentIntent(
        agent_name="Maya",
        intent_type="repair_relationship",
        target_agent="Carlos",
        target_location=None,
        description="Maya wants to repair her relationship with Carlos.",
        created_day=1,
        expires_day=3,
        priority=5,
    )

    base_weights = {
        "chat": 8,
        "apologize": 1,
        "argue": 2,
        "offer_help": 1,
    }

    adjusted = engine.adjust_action_weights_for_intent(
        weights=base_weights,
        intent=intent,
        listener_name="Lena",
    )

    assert adjusted == base_weights

def test_plain_i_heard_is_not_enough_for_rumor_marker():
    assert not has_rumor_marker(
        "I heard the poetry readings were really inspiring today."
    )


def test_specific_rumor_marker_is_preserved():
    assert has_rumor_marker(
        "Someone said the new vendor might be hiding something."
    )

def test_build_friendship_boosts_help_more_than_compliment():
    engine = build_engine()

    intent = AgentIntent(
        agent_name="Maya",
        intent_type="build_friendship",
        target_agent="Lena",
        target_location=None,
        description="Maya wants to strengthen her bond with Lena.",
        created_day=1,
        expires_day=3,
        priority=4,
    )

    base_weights = {
        "chat": 8,
        "compliment": 1,
        "offer_help": 1,
        "cooperate": 1,
    }

    adjusted = engine.adjust_action_weights_for_intent(
        weights=base_weights,
        intent=intent,
        listener_name="Lena",
    )

    assert adjusted["compliment"] == 2
    assert adjusted["offer_help"] == 4
    assert adjusted["cooperate"] == 3

def test_socialize_intent_does_not_boost_compliment():
    engine = build_engine()

    intent = AgentIntent(
        agent_name="Lena",
        intent_type="socialize",
        target_agent=None,
        target_location="cafe",
        description="Lena wants to spend time with other residents.",
        created_day=1,
        expires_day=2,
        priority=2,
    )

    base_weights = {
        "chat": 8,
        "compliment": 1,
        "ask_for_help": 1,
        "offer_help": 1,
    }

    adjusted = engine.adjust_action_weights_for_intent(
        weights=base_weights,
        intent=intent,
        listener_name="Carlos",
    )

    assert adjusted["chat"] == 10
    assert adjusted["compliment"] == 1
    assert adjusted["ask_for_help"] == 2
    assert adjusted["offer_help"] == 2

def test_investigate_intent_boosts_share_rumor():
    engine = build_engine()

    intent = AgentIntent(
        agent_name="Maya",
        intent_type="investigate",
        target_agent=None,
        target_location="library",
        description="Maya wants to gather information.",
        created_day=1,
        expires_day=2,
        priority=3,
    )

    base_weights = {
        "chat": 8,
        "ask_for_help": 1,
        "share_rumor": 1,
    }

    adjusted = engine.adjust_action_weights_for_intent(
        weights=base_weights,
        intent=intent,
        listener_name="Ethan",
    )

    assert adjusted["chat"] == 9
    assert adjusted["ask_for_help"] == 4
    assert adjusted["share_rumor"] == 3

def test_choose_final_action_accepts_precomputed_inferred_action():
    engine = build_engine()

    action = engine.choose_final_action(
        conversation="Generic line without obvious markers.",
        parsed_action="chat",
        conversation_tags=[],
        allowed_actions=["chat", "offer_help"],
        inferred_action="offer_help",
    )

    assert action == "offer_help"

def test_log_conversation_event_includes_action_pipeline_fields():
    engine = build_engine()

    speaker = engine.agents[0]
    listener = engine.agents[1]

    engine.log_conversation_event(
        day=1,
        hour=8,
        location_id="cafe",
        speaker=speaker,
        listener=listener,
        conversation="I can help you with that.",
        relationship_change=1,
        new_score=1,
        relationship_label="neutral",
        action="offer_help",
        suggested_action="offer_help",
        parsed_action="offer_help",
        inferred_action="offer_help",
        base_action_weights={"chat": 8, "offer_help": 2},
        intent_adjusted_weights={"chat": 7, "offer_help": 5},
    )

    import json

    with open(engine.logger.conversations_file, "r", encoding="utf-8") as file:
        records = [
            json.loads(line)
            for line in file
            if line.strip()
        ]

    record = records[-1]

    assert record["suggested_action"] == "offer_help"
    assert record["parsed_action"] == "offer_help"
    assert record["inferred_action"] == "offer_help"
    assert record["base_action_weights"]["chat"] == 8
    assert record["intent_adjusted_weights"]["offer_help"] == 5

def test_choose_final_action_with_reason_trusts_parsed_non_chat():
    engine = build_engine()

    action, reason = engine.choose_final_action_with_reason(
        conversation="Have you noticed any unusual activity around the market lately?",
        parsed_action="ask_for_help",
        conversation_tags=[],
        allowed_actions=["chat", "ask_for_help"],
        inferred_action="chat",
    )

    assert action == "ask_for_help"
    assert reason == "trusted_parsed_non_chat"


def test_choose_final_action_with_reason_reports_disallowed_action():
    engine = build_engine()

    action, reason = engine.choose_final_action_with_reason(
        conversation="Can you help me figure this out?",
        parsed_action="ask_for_help",
        conversation_tags=[],
        allowed_actions=["chat"],
        inferred_action="chat",
    )

    assert action == "chat"
    assert reason == "fallback_chat_action_not_allowed"


def test_choose_final_action_with_reason_rejects_rumor_without_marker():
    engine = build_engine()

    action, reason = engine.choose_final_action_with_reason(
        conversation="The music was good today.",
        parsed_action="share_rumor",
        conversation_tags=[],
        allowed_actions=["chat", "share_rumor"],
        inferred_action="chat",
    )

    assert action == "chat"
    assert reason == "parsed_rumor_without_marker"

def test_relevant_town_arcs_for_context_filters_by_location():
    from src.town.town_arc import TownArc

    engine = build_engine()
    engine.town_arcs = [
        TownArc(
            id="arc_market_pressure_day_1",
            name="Market Pressure",
            description="Residents are watching market prices.",
            status="active",
            location_id="market",
            involved_agents=[],
            tags=["market", "business"],
            tension=2,
            progress=1,
            created_day=1,
            updated_day=1,
        ),
        TownArc(
            id="arc_library_questions_day_1",
            name="Public Questions",
            description="Residents are reviewing records.",
            status="active",
            location_id="library",
            involved_agents=[],
            tags=["knowledge"],
            tension=1,
            progress=0,
            created_day=1,
            updated_day=1,
        ),
    ]

    arcs = engine.get_relevant_town_arcs_for_context("market")

    assert len(arcs) == 1
    assert arcs[0]["id"] == "arc_market_pressure_day_1"

from src.town.town_arc import TownArc
from tests.simulation.test_suggested_actions import build_engine


def count_town_arc_memories(engine):
    return sum(
        1
        for agent in engine.agents
        for memory in agent.memory
        if memory.type == "town_arc"
    )


def test_town_arc_creation_creates_one_memory_per_agent():
    engine = build_engine()

    arc = TownArc(
        id="arc_market_pressure_day_1",
        name="Market Pressure",
        description="Residents are watching market prices.",
        status="active",
        location_id="market",
        involved_agents=[],
        tags=["market", "business"],
        tension=2,
        progress=0,
        created_day=1,
        updated_day=1,
    )

    engine.remember_town_arc_for_all_agents(
        day=1,
        arc=arc,
        reason="created",
    )

    assert count_town_arc_memories(engine) == len(engine.agents)


def test_active_town_arc_does_not_create_memory_without_update():
    engine = build_engine()

    engine.town_arcs = [
        TownArc(
            id="arc_market_pressure_day_1",
            name="Market Pressure",
            description="Residents are watching market prices.",
            status="active",
            location_id="market",
            involved_agents=[],
            tags=["market", "business"],
            tension=2,
            progress=0,
            created_day=1,
            updated_day=2,
        )
    ]

    before = count_town_arc_memories(engine)

    engine.update_town_arcs(day=2)

    after = count_town_arc_memories(engine)

    assert after == before

def test_town_arc_boosts_community_actions():
    from src.town.town_arc import TownArc

    engine = build_engine()

    engine.town_arcs = [
        TownArc(
            id="arc_community_project_day_1",
            name="Community Project",
            description="Residents are working together.",
            status="active",
            location_id="town_square",
            involved_agents=[],
            tags=["community", "volunteer", "social"],
            tension=1,
            progress=0,
            created_day=1,
            updated_day=1,
        )
    ]

    base_weights = {
        "chat": 8,
        "cooperate": 1,
        "offer_help": 1,
        "ask_for_help": 1,
    }

    adjusted = engine.adjust_action_weights_for_town_arcs(
        weights=base_weights,
        location_id="town_square",
    )

    assert adjusted["cooperate"] > base_weights["cooperate"]
    assert adjusted["offer_help"] > base_weights["offer_help"]
    assert adjusted["ask_for_help"] > base_weights["ask_for_help"]


def test_town_arc_does_not_boost_unrelated_location():
    from src.town.town_arc import TownArc

    engine = build_engine()

    engine.town_arcs = [
        TownArc(
            id="arc_community_project_day_1",
            name="Community Project",
            description="Residents are working together.",
            status="active",
            location_id="town_square",
            involved_agents=[],
            tags=["community", "volunteer", "social"],
            tension=1,
            progress=0,
            created_day=1,
            updated_day=1,
        )
    ]

    base_weights = {
        "chat": 8,
        "cooperate": 1,
        "offer_help": 1,
        "ask_for_help": 1,
    }

    adjusted = engine.adjust_action_weights_for_town_arcs(
        weights=base_weights,
        location_id="library",
    )

    assert adjusted == base_weights