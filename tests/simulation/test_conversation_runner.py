from src.simulation.conversation_runner import ConversationRunner
from types import SimpleNamespace


class FakeEngineWithNoPairs:
    def group_agents_by_location(self):
        return {
            "library": ["Maya"],
            "market": [],
        }


def test_conversation_runner_prints_when_no_conversations_created(capsys):
    runner = ConversationRunner()
    engine = FakeEngineWithNoPairs()

    runner.generate_conversations(
        engine=engine,
        day=1,
        hour=8,
    )

    captured = capsys.readouterr()

    assert "No conversations this tick" in captured.out


class RaisingLLM:
    def generate_conversation(self, context):
        raise RuntimeError("temporary model failure")


class FakeEngineWithModelFailure:
    def __init__(self):
        self.speaker = SimpleNamespace(name="Maya")
        self.listener = SimpleNamespace(name="Ethan")
        self.llm = RaisingLLM()
        self.actions = SimpleNamespace(infer_action=lambda dialogue, tags: "chat")
        self.logged = None

    def group_agents_by_location(self):
        return {"library": [self.speaker, self.listener]}

    def choose_conversation_pair(self, agents):
        return self.speaker, self.listener

    def prepare_conversation_context(self, **kwargs):
        return {
            "old_score": 0,
            "old_relationship_label": "neutral",
            "allowed_actions": ["chat"],
            "speaker_intent": None,
            "listener_intent": None,
            "base_action_weights": {"chat": 1},
            "intent_adjusted_weights": {"chat": 1},
            "suggested_action": "chat",
            "context": {"context_evidence": {}},
        }

    def process_conversation_output(self, raw_output, **kwargs):
        assert raw_output == ""
        return {
            "parsed_output": {"action_source": "fallback_no_json", "reason": "", "tags": []},
            "conversation": "A safe fallback line.",
            "parsed_action": "chat",
            "dialogue_source": "agent_fallback_empty",
        }

    def get_initial_conversation_tags(self, **kwargs):
        return ["conversation"]

    def choose_final_action_with_reason(self, **kwargs):
        return "chat", "used_parsed_action"

    def finalize_conversation_tags(self, **kwargs):
        return ["conversation", "chat"]

    def apply_conversation_effects(self, **kwargs):
        return {"relationship_change": 0, "new_score": 0, "relationship_label": "neutral"}

    def update_intents_after_conversation(self, **kwargs):
        return None

    def log_conversation_event(self, *args, **kwargs):
        self.logged = kwargs

    def print_conversation_event(self, *args, **kwargs):
        return None


def test_conversation_runner_records_model_exception_and_continues():
    engine = FakeEngineWithModelFailure()

    ConversationRunner().generate_conversations(engine=engine, day=1, hour=8)

    assert engine.logged["generation_error"] == "RuntimeError: temporary model failure"
    assert engine.logged["raw_response"] == ""
    assert engine.logged["dialogue_source"] == "agent_fallback_empty"
