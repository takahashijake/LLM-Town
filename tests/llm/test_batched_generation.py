import threading

import torch

from src.llm.client import TransformersLLMClient
from src.llm.generation import ConversationGenerationRequest


class TensorInputs(dict):
    def to(self, device):
        return TensorInputs({key: value.to(device) for key, value in self.items()})


class PaddingTokenizer:
    eos_token_id = 2
    padding_side = "right"

    def __init__(self):
        self.padding_sides = []

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        return messages[0]["content"]

    def __call__(self, texts, *, return_tensors, padding):
        self.padding_sides.append(self.padding_side)
        lengths = [max(2, len(text) // 40) for text in texts]
        width = max(lengths)
        rows = []
        masks = []
        for index, length in enumerate(lengths):
            pad = width - length
            rows.append(([0] * pad) + ([10 + index] * length))
            masks.append(([0] * pad) + ([1] * length))
        return TensorInputs({
            "input_ids": torch.tensor(rows),
            "attention_mask": torch.tensor(masks),
        })

    def decode(self, token_ids, *, skip_special_tokens):
        return " ".join(str(int(token)) for token in token_ids)


class RecordingModel:
    def __init__(self):
        self.calls = []

    def generate(self, *, input_ids, attention_mask, **kwargs):
        self.calls.append((input_ids.clone(), attention_mask.clone(), kwargs))
        generated = torch.tensor([[90, 91], [92, 93]])
        return torch.cat((input_ids, generated), dim=1)


def request(index, invalid_output):
    return ConversationGenerationRequest(
        request_id=f"request-{index}",
        session_id=f"session-{index}",
        schedule_index=index,
        turn_index=0,
        generation_attempt=1,
        seed=100 + index,
        request_kind="grounding_repair",
        context={
            "grounded_content_plan": {
                "required_polarity": "fulfilled",
                "permitted_fact": "A promise was fulfilled.",
            }
        },
        invalid_output=invalid_output,
        validation_error="history omitted",
    )


def test_transformers_batch_uses_one_padded_model_call_and_demultiplexes_rows():
    client = object.__new__(TransformersLLMClient)
    client.torch = torch
    client.model = RecordingModel()
    client.tokenizer = PaddingTokenizer()
    client.device = torch.device("cpu")
    client.generation_config = {"max_new_tokens": 2, "do_sample": True}
    client._generation_lock = threading.Lock()
    client.batch_metrics = []

    results = client.generate_conversation_batch([
        request(0, "short"),
        request(1, "a much longer invalid response " * 12),
    ])

    assert len(client.model.calls) == 1
    assert client.tokenizer.padding_sides == ["left"]
    assert client.tokenizer.padding_side == "right"
    assert [row.request_id for row in results] == ["request-0", "request-1"]
    assert [row.output for row in results] == ["90 91", "92 93"]
    assert client.batch_metrics[0]["batch_size"] == 2
    assert client.batch_metrics[0]["prompt_token_counts"][0] < (
        client.batch_metrics[0]["prompt_token_counts"][1]
    )
