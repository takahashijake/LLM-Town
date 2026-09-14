from pathlib import Path

from src.llm.client import FakeLLMClient
from src.simulation.engine import SimulationEngine


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_engine_causal_reputation_propagation_and_checkpoint_resume(tmp_path):
    state_path = tmp_path / "state.json"
    engine = SimulationEngine(
        agents_path=str(PROJECT_ROOT / "data" / "agents.json"),
        locations_path=str(PROJECT_ROOT / "data" / "locations.json"),
        llm_client=FakeLLMClient(),
        state_path=state_path,
        logs_dir=tmp_path / "logs",
    )
    engine.relationship_updater.get_relationship_change = (
        lambda relationship_label: 0
    )
    agents = {item.name: item for item in engine.agents}

    # Maya helps Carlos. Carlos alone acquires direct evidence.
    engine.apply_conversation_effects(
        day=1,
        hour=8,
        location_id="market",
        speaker=agents["Maya"],
        listener=agents["Carlos"],
        action="offer_help",
        conversation="I can help you arrange those supplies.",
        conversation_tags=["conversation", "offer_help"],
        old_relationship_label="neutral",
        old_score=0,
    )
    direct = agents["Carlos"].get_reputation_belief("Maya", "helpfulness")
    assert direct is not None
    assert agents["Lena"].get_reputation_belief("Maya", "helpfulness") is None
    assert agents["Ethan"].reputation_beliefs == {}

    # Carlos's own state supplies the only claim offered to his next context.
    setup = engine.prepare_conversation_context(
        location_id="market",
        speaker=agents["Carlos"],
        listener=agents["Lena"],
        current_day=2,
    )
    assert setup["rumor_claim"]["subject_agent"] == "Maya"
    assert "share_rumor" in setup["allowed_actions"]
    engine.apply_conversation_effects(
        day=2,
        hour=12,
        location_id="market",
        speaker=agents["Carlos"],
        listener=agents["Lena"],
        action="share_rumor",
        conversation="From what I saw, Maya seemed helpful.",
        conversation_tags=["conversation", "share_rumor"],
        old_relationship_label="neutral",
        old_score=0,
        rumor_claim=setup["rumor_claim"],
    )
    hearsay = agents["Lena"].get_reputation_belief("Maya", "helpfulness")
    assert 0 < hearsay.score < direct.score
    assert agents["Ethan"].reputation_beliefs == {}

    engine.state.save(engine, current_day=2, current_hour=12)
    resumed = SimulationEngine(
        agents_path=str(PROJECT_ROOT / "data" / "agents.json"),
        locations_path=str(PROJECT_ROOT / "data" / "locations.json"),
        load_state=True,
        llm_client=FakeLLMClient(),
        state_path=state_path,
        logs_dir=tmp_path / "resumed-logs",
    )
    resumed_agents = {item.name: item for item in resumed.agents}
    assert resumed_agents["Carlos"].get_reputation_belief(
        "Maya", "helpfulness"
    ).to_dict() == direct.to_dict()
    assert resumed_agents["Lena"].get_reputation_belief(
        "Maya", "helpfulness"
    ).to_dict() == hearsay.to_dict()
    assert resumed_agents["Ethan"].reputation_beliefs == {}
    assert resumed.reputation_updates == engine.reputation_updates
