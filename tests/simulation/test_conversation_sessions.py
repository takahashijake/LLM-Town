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
    assert rows[2]["response_outcome"] == "answered"
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
