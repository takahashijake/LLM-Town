from types import SimpleNamespace

from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.simulation.persistence import SimulationPersistence
from src.simulation.state import SimulationState
from src.systems.reputation import MAX_REPUTATION_SCORE, ReputationSystem


def agent(name: str) -> Agent:
    return Agent(
        id=name.lower(),
        name=name,
        personality="careful",
        location_id="town_square",
        needs={"social": 50, "wealth": 50, "knowledge": 50},
    )


def test_direct_behavior_updates_only_the_participant_observer():
    maya, carlos, lena = agent("Maya"), agent("Carlos"), agent("Lena")
    system = ReputationSystem(ActionSystem())

    updates = system.record_direct_action(
        day=1, hour=8, actor=maya, observer=carlos, action="offer_help"
    )

    belief = carlos.get_reputation_belief("Maya", "helpfulness")
    assert belief is not None
    assert belief.score > 0
    assert belief.confidence == 0.9
    assert belief.source_type == "direct_interaction"
    assert len(updates) == 1
    assert lena.reputation_beliefs == {}
    assert maya.reputation_beliefs == {}


def test_ordinary_chat_and_rumor_speech_do_not_rewrite_tellers_reputation():
    maya, carlos = agent("Maya"), agent("Carlos")
    system = ReputationSystem(ActionSystem())

    assert system.record_direct_action(
        day=1, hour=8, actor=maya, observer=carlos, action="chat"
    ) == []
    assert system.record_direct_action(
        day=1, hour=12, actor=maya, observer=carlos, action="share_rumor"
    ) == []
    assert carlos.reputation_beliefs == {}


def test_apology_partially_repairs_trust_and_hostility_dimensions():
    maya, carlos = agent("Maya"), agent("Carlos")
    system = ReputationSystem(ActionSystem())
    system.record_direct_action(
        day=1, hour=8, actor=maya, observer=carlos, action="insult"
    )
    hostile_before = carlos.get_reputation_belief("Maya", "hostility").score
    trust_before = carlos.get_reputation_belief("Maya", "trustworthiness").score

    system.record_direct_action(
        day=2, hour=8, actor=maya, observer=carlos, action="apologize"
    )

    assert carlos.get_reputation_belief(
        "Maya", "hostility"
    ).score < hostile_before
    assert carlos.get_reputation_belief(
        "Maya", "trustworthiness"
    ).score > trust_before


def test_hearsay_is_weaker_duplicate_safe_and_cannot_loop_to_prior_recipient():
    maya, carlos, lena = agent("Maya"), agent("Carlos"), agent("Lena")
    system = ReputationSystem(ActionSystem())
    system.record_direct_action(
        day=1, hour=8, actor=maya, observer=carlos, action="cooperate"
    )
    claim = system.select_shareable_claim(carlos, lena)

    update = system.transmit_rumor(
        day=2, speaker=carlos, listener=lena, claim=claim
    )
    duplicate = system.transmit_rumor(
        day=2, speaker=carlos, listener=lena, claim=claim
    )

    direct = carlos.get_reputation_belief("Maya", "cooperativeness")
    hearsay = lena.get_reputation_belief("Maya", "cooperativeness")
    assert update is not None
    assert update["third_party"] is True
    assert hearsay.source_type == "hearsay"
    assert hearsay.confidence < direct.confidence
    assert 0 < hearsay.score < direct.score
    assert duplicate is None
    assert len(hearsay.evidence) == 1
    assert system.select_shareable_claim(lena, carlos) is None


def test_forged_claim_without_speakers_owned_evidence_is_rejected():
    carlos, lena = agent("Carlos"), agent("Lena")
    system = ReputationSystem(ActionSystem())
    forged = {
        "subject_agent": "Maya",
        "dimension": "trustworthiness",
        "value": -1,
        "confidence": 1,
        "evidence_id": "invented",
        "transmission_depth": 0,
        "transmission_chain": [],
    }

    assert system.transmit_rumor(
        day=1, speaker=carlos, listener=lena, claim=forged
    ) is None
    assert lena.reputation_beliefs == {}


def test_trusted_hearsay_has_more_weight_but_never_direct_confidence():
    maya, carlos = agent("Maya"), agent("Carlos")
    trusted_listener, wary_listener = agent("Lena"), agent("Ethan")
    system = ReputationSystem(ActionSystem())
    system.record_direct_action(
        day=1, hour=8, actor=maya, observer=carlos, action="offer_help"
    )
    for index in range(3):
        system.record_observation(
            day=1,
            observer=trusted_listener,
            target_agent="Carlos",
            dimension="trustworthiness",
            value=1,
            evidence_id=f"trusted-{index}",
        )
        system.record_observation(
            day=1,
            observer=wary_listener,
            target_agent="Carlos",
            dimension="trustworthiness",
            value=-1,
            evidence_id=f"wary-{index}",
        )
    claim = system.select_shareable_claim(carlos, trusted_listener)
    system.transmit_rumor(
        day=2, speaker=carlos, listener=trusted_listener, claim=claim
    )
    system.transmit_rumor(
        day=2, speaker=carlos, listener=wary_listener, claim=claim
    )

    trusted = trusted_listener.get_reputation_belief("Maya", "helpfulness")
    wary = wary_listener.get_reputation_belief("Maya", "helpfulness")
    direct = carlos.get_reputation_belief("Maya", "helpfulness")
    assert trusted.confidence > wary.confidence
    assert trusted.confidence < direct.confidence


def test_distinct_incidents_change_beliefs_gradually_and_remain_bounded():
    maya, carlos = agent("Maya"), agent("Carlos")
    system = ReputationSystem(ActionSystem())
    for index in range(30):
        system.record_observation(
            day=index + 1,
            observer=carlos,
            target_agent="Maya",
            dimension="hostility",
            value=1,
            evidence_id=f"incident-{index}",
        )

    belief = carlos.get_reputation_belief("Maya", "hostility")
    assert 0 < belief.score <= MAX_REPUTATION_SCORE
    assert belief.score < MAX_REPUTATION_SCORE


def test_causal_third_party_propagation_round_trips_and_uninformed_agent_stays_unaware(
    tmp_path,
):
    maya, carlos, lena, ethan = (
        agent("Maya"), agent("Carlos"), agent("Lena"), agent("Ethan")
    )
    records = []
    system = ReputationSystem(ActionSystem(), records)

    system.record_direct_action(
        day=1, hour=8, actor=maya, observer=carlos, action="offer_help"
    )
    assert lena.get_reputation_belief("Maya", "helpfulness") is None
    claim = system.select_shareable_claim(carlos, lena)
    system.transmit_rumor(day=2, speaker=carlos, listener=lena, claim=claim)

    direct = carlos.get_reputation_belief("Maya", "helpfulness")
    hearsay = lena.get_reputation_belief("Maya", "helpfulness")
    assert 0 < hearsay.score < direct.score
    assert ethan.reputation_beliefs == {}

    state = SimulationState(tmp_path / "state.json")
    state.save(
        SimpleNamespace(
            agents=[maya, carlos, lena, ethan],
            relationships=SimpleNamespace(scores={}),
            reputation_updates=records,
        ),
        current_day=2,
        current_hour=12,
    )
    saved = state.load()
    loaded = {
        item.name: item
        for item in SimulationPersistence().load_agents_from_state(saved)
    }
    assert loaded["Carlos"].get_reputation_belief(
        "Maya", "helpfulness"
    ).to_dict() == direct.to_dict()
    assert loaded["Lena"].get_reputation_belief(
        "Maya", "helpfulness"
    ).to_dict() == hearsay.to_dict()
    assert loaded["Ethan"].reputation_beliefs == {}
    assert saved["reputation_updates"] == records
