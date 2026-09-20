import json
import random

from src.agents.memory import Memory
from src.simulation.conversation_session import ResponseOutcomeResolver
from src.simulation.engine import SimulationEngine


class ScriptedLLM:
    is_deterministic_fake = True

    def __init__(self, responses):
        self.responses = list(responses)
        self.contexts = []

    def generate_conversation(self, context):
        self.contexts.append(context)
        response = self.responses[len(self.contexts) - 1]
        if isinstance(response, Exception):
            raise response
        return json.dumps(response)


class GroundingScriptedLLM(ScriptedLLM):
    is_deterministic_fake = False


def build_engine(tmp_path, llm, max_turns=4):
    engine = SimulationEngine(
        agents_path="data/agents.json",
        locations_path="data/locations.json",
        llm_client=llm,
        state_path=tmp_path / "state.json",
        logs_dir=tmp_path / "logs",
        max_conversation_turns=max_turns,
    )
    maya, ethan = engine.agents[:2]
    maya.location_id = ethan.location_id = "market"
    engine.group_agents_by_location = lambda: {"market": [maya, ethan]}
    engine.choose_conversation_pair = lambda agents: (maya, ethan)
    engine.relationship_updater.get_relationship_change = lambda relationship_label: 0
    return engine, maya, ethan


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_unsupported_grounding_regenerates_at_most_once(tmp_path):
    llm = GroundingScriptedLLM([
        {"dialogue": "Remember when we played cards?", "action": "chat"},
        {"dialogue": "What have you been working on?", "action": "chat"},
    ])
    engine, _, _ = build_engine(tmp_path, llm, max_turns=1)
    engine.generate_conversations(1, 8)
    row = read_jsonl(engine.logger.conversations_file)[0]
    assert len(llm.contexts) == 2
    assert llm.contexts[1]["grounding_correction"] == "unsupported_shared_history_candidate"
    assert row["regenerated_for_grounding"] is True
    assert row["generation_attempt_count"] == 2
    assert row["grounding_reason"] == "unsupported_shared_history_candidate"


def test_repeated_grounding_failure_uses_safe_fallback(tmp_path):
    llm = GroundingScriptedLLM([
        {"dialogue": "Remember when we played cards?", "action": "chat"},
        {"dialogue": "Remember when we opened the Willow Garden shop?", "action": "chat"},
    ])
    engine, _, _ = build_engine(tmp_path, llm, max_turns=1)
    engine.generate_conversations(1, 8)
    row = read_jsonl(engine.logger.conversations_file)[0]
    assert len(llm.contexts) == 2
    assert row["dialogue_source"] == "policy_fallback_unsupported_grounding"
    assert "memory:" not in row["conversation"]


def test_session_alternates_and_rebuilds_private_context(tmp_path):
    llm = ScriptedLLM([
        {"dialogue": "Would you like some help with the records?", "action": "offer_help"},
        {"dialogue": "Yes, I'd appreciate that.", "action": "chat"},
        {"dialogue": "Could you recommend where we should start?", "action": "ask_for_help"},
        {"dialogue": "Try the inventory ledger first.", "action": "chat"},
    ])
    engine, maya, ethan = build_engine(tmp_path, llm)
    maya.memory.append(Memory(1, 7, "observation", "Maya private secret", [maya.name], "market", 2, 0, []))
    ethan.memory.append(Memory(1, 7, "observation", "Ethan private clue", [ethan.name], "market", 2, 0, []))

    engine.generate_conversations(1, 8)

    rows = read_jsonl(engine.logger.conversations_file)
    assert [(row["speaker"], row["listener"]) for row in rows] == [
        (maya.name, ethan.name), (ethan.name, maya.name),
        (maya.name, ethan.name), (ethan.name, maya.name),
    ]
    assert llm.contexts[1]["most_recent_utterance"] == rows[0]["conversation"]
    assert llm.contexts[1]["session_transcript"][0]["speaker"] == maya.name
    assert "Maya private secret" not in json.dumps(llm.contexts[1])
    assert llm.contexts[1]["speaker"] == ethan.name
    assert rows[0]["response_outcome"] == "accepted"
    assert rows[2]["response_outcome"] == "accepted"
    assert rows[-1]["termination_reason"] == "max_turns"
    assert len([m for m in maya.memory if m.type == "conversation"]) == 1
    assert len([m for m in ethan.memory if m.type == "conversation"]) == 1
    assert rows[0]["relationship_change"] == 1


def test_storm_off_terminates_immediately(tmp_path):
    llm = ScriptedLLM([
        {"dialogue": "I'm done talking about this.", "action": "storm_off"},
    ])
    engine, maya, ethan = build_engine(tmp_path, llm)
    engine.relationships.change_score(maya.name, ethan.name, -4)

    engine.generate_conversations(1, 8)

    rows = read_jsonl(engine.logger.conversations_file)
    assert len(rows) == 1
    assert rows[0]["action"] == "storm_off"
    assert rows[0]["termination_reason"] == "storm_off"


def test_repetition_and_generation_failure_terminate_safely(tmp_path):
    repeated = {"dialogue": "The same exact line.", "action": "chat"}
    engine, _, _ = build_engine(tmp_path / "repeat", ScriptedLLM([repeated, repeated]))
    engine.generate_conversations(1, 8)
    rows = read_jsonl(engine.logger.conversations_file)
    assert len(rows) == 2
    assert rows[-1]["termination_reason"] == "repetition"

    failed_engine, _, _ = build_engine(
        tmp_path / "failure", ScriptedLLM([RuntimeError("temporary failure")])
    )
    failed_engine.generate_conversations(1, 8)
    failed_rows = read_jsonl(failed_engine.logger.conversations_file)
    assert failed_rows[0]["termination_reason"] == "generation_failure"
    assert "temporary failure" in failed_rows[0]["generation_error"]


def test_response_outcomes_are_conservative():
    resolver = ResponseOutcomeResolver()
    assert resolver.resolve("offer_help", "Yeah, I'd appreciate that.") == "accepted"
    assert resolver.resolve("offer_help", "No thanks, I've got it.") == "declined"
    assert resolver.resolve("offer_help", "Perhaps we can discuss the records.") == "unresolved"
    assert resolver.resolve("cooperate", "Thanks, the library looks welcoming.") == "unresolved"
    assert resolver.resolve("ask_for_help", "That sounds good to me.") == "unresolved"
    assert resolver.resolve("ask_for_help", "Sure thing, I'll check the printer.") == "accepted"
    assert resolver.resolve("offer_help", "Thanks, I appreciate your help.") == "accepted"
    assert resolver.resolve("cooperate", "Let's grab some trash bags first.") == "accepted"


def test_repeated_semantic_action_effect_is_applied_once(tmp_path):
    responses = [
        {"dialogue": "You did a great job on that.", "action": "compliment"},
        {"dialogue": "You were excellent with the records.", "action": "compliment"},
        {"dialogue": "I admire how organized you are.", "action": "compliment"},
        {"dialogue": "That was thoughtful work.", "action": "compliment"},
    ]
    engine, maya, ethan = build_engine(tmp_path, ScriptedLLM(responses))
    before = engine.relationships.get_score(maya.name, ethan.name)
    engine.generate_conversations(1, 8)
    assert engine.relationships.get_score(maya.name, ethan.name) == before + 1
    assert len(engine.relationship_events) == 1


def test_scripted_session_is_reproducible(tmp_path):
    responses = [
        {"dialogue": "Would you like some help?", "action": "offer_help"},
        {"dialogue": "No thanks, I've got it.", "action": "chat"},
    ]
    outputs = []
    for index in range(2):
        random.seed(42)
        engine, _, _ = build_engine(
            tmp_path / str(index), ScriptedLLM(responses), max_turns=2
        )
        engine.generate_conversations(1, 8)
        rows = read_jsonl(engine.logger.conversations_file)
        assert rows[0]["response_outcome"] == "declined"
        assert rows[0]["relationship_change"] == 0
        assert all(
            not update["delta"]
            for update in rows[0]["relationship_updates"].values()
        )
        outputs.append(rows)
    assert outputs[0] == outputs[1]


def test_rate_capped_offer_keeps_semantics_and_listener_can_decline(tmp_path):
    llm = ScriptedLLM([
        {"dialogue": "Would you like some help with those bins?", "action": "offer_help"},
        {"dialogue": "No thanks, I've got it.", "action": "chat"},
    ])
    engine, maya, ethan = build_engine(tmp_path, llm, max_turns=2)
    engine.recent_actions = ["offer_help", "offer_help", "offer_help", "chat", "chat"]
    before = engine.relationships.get_score(maya.name, ethan.name)

    engine.generate_conversations(1, 8)

    rows = read_jsonl(engine.logger.conversations_file)
    assert rows[0]["action"] == "offer_help"
    assert rows[0]["effect_applied"] is False
    assert rows[0]["effect_suppression_reason"] == "action_rate_cap"
    assert rows[0]["response_outcome"] == "declined"
    assert engine.relationships.get_score(maya.name, ethan.name) == before


def test_rate_capped_rumor_keeps_semantics_without_double_effects(tmp_path):
    llm = ScriptedLLM([
        {"dialogue": "Someone said the market account might be unreliable.", "action": "share_rumor"},
    ])
    engine, maya, ethan = build_engine(tmp_path, llm, max_turns=1)
    carlos = next(agent for agent in engine.agents if agent.name not in {maya.name, ethan.name})
    engine.reputation_system.record_observation(
        day=1,
        observer=maya,
        target_agent=carlos.name,
        dimension="trustworthiness",
        value=-1,
        evidence_id="test-observation",
    )
    engine.recent_actions = ["share_rumor", "chat", "chat", "chat", "chat"]
    before = engine.relationships.get_score(maya.name, ethan.name)

    engine.generate_conversations(1, 8)

    row = read_jsonl(engine.logger.conversations_file)[0]
    assert row["action"] == "share_rumor"
    assert row["effect_applied"] is False
    assert row["effect_suppression_reason"] == "action_rate_cap"
    assert engine.relationships.get_score(maya.name, ethan.name) == before


class RegeneratingLLM(ScriptedLLM):
    is_deterministic_fake = False


def test_exact_echo_regenerates_once_and_accepts_fresh_retry(tmp_path):
    llm = RegeneratingLLM([
        {"dialogue": "The gardening workshop starts here today.", "action": "chat"},
        {"dialogue": "The gardening workshop starts here today.", "action": "chat"},
        {"dialogue": "Yes, I noticed the seed table is already set up.", "action": "chat"},
    ])
    engine, _, _ = build_engine(tmp_path, llm, max_turns=2)

    engine.generate_conversations(1, 8)

    rows = read_jsonl(engine.logger.conversations_file)
    assert len(llm.contexts) == 3
    assert rows[1]["generation_attempt_count"] == 2
    assert rows[1]["regenerated_for_repetition"] is True
    assert rows[1]["conversation"].startswith("Yes, I noticed")
    assert llm.contexts[-1]["anti_echo_retry"] is True


def test_near_echo_regenerates_once(tmp_path):
    llm = RegeneratingLLM([
        {"dialogue": "The library has become a warm and welcoming place for everyone.", "action": "chat"},
        {"dialogue": "The library has become such a warm and welcoming place for everyone.", "action": "chat"},
        {"dialogue": "It has; the quieter reading corner seems especially useful.", "action": "chat"},
    ])
    engine, _, _ = build_engine(tmp_path, llm, max_turns=2)

    engine.generate_conversations(1, 8)

    rows = read_jsonl(engine.logger.conversations_file)
    assert rows[1]["generation_attempt_count"] == 2
    assert rows[1]["termination_reason"] == "max_turns"


def test_persistent_echo_gets_one_retry_then_terminates(tmp_path):
    repeated = {"dialogue": "The spice rack looks much better organized now.", "action": "chat"}
    llm = RegeneratingLLM([repeated, repeated, repeated])
    engine, _, _ = build_engine(tmp_path, llm, max_turns=4)

    engine.generate_conversations(1, 8)

    rows = read_jsonl(engine.logger.conversations_file)
    assert len(llm.contexts) == 3
    assert rows[-1]["generation_attempt_count"] == 2
    assert rows[-1]["termination_reason"] == "repetition"


def test_normal_real_model_dialogue_does_not_regenerate(tmp_path):
    llm = RegeneratingLLM([
        {"dialogue": "Have you checked the new arrivals?", "action": "chat"},
        {"dialogue": "Yes, the history shelf has two useful titles.", "action": "chat"},
    ])
    engine, _, _ = build_engine(tmp_path, llm, max_turns=2)

    engine.generate_conversations(1, 8)

    rows = read_jsonl(engine.logger.conversations_file)
    assert len(llm.contexts) == 2
    assert rows[1]["generation_attempt_count"] == 1
    assert rows[1]["regenerated_for_repetition"] is False
