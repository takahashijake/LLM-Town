import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

class FakeLLMClient:
    def generate_conversation(self, context: dict) -> str:
        return (
            f"{context['speaker']} talks with {context['listener']} "
            f"at {context['location']}."
        )

class TransformersLLMClient:
    def __init__(self, model_name: str = "Qwen/Qwen2.5-3B-Instruct"):
        self.model_name = model_name

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
            device_map="auto",
        )

    def generate_conversation(self, context: dict) -> str:
        prompt = self._build_prompt(context)

        messages = [
            {
                "role": "system",
                "content": (
                    "You generate short, natural dialogue for a town simulation. "
                    "Return only one sentence. No narration."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=40,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        generated_ids = outputs[0][inputs["input_ids"].shape[-1]:]
        response = self.tokenizer.decode(generated_ids, skip_special_tokens=True)

        return response.strip()

    def _build_prompt(self, context: dict) -> str:
        memories = context.get("relevant_memories", [])

        memory_text = "\n".join(
            f"- {memory}"
            for memory in memories
        )

        if not memory_text:
            memory_text = "- No important memories."

        return f"""
            Speaker: {context["speaker"]}
            Listener: {context["listener"]}
            Speaker personality: {context["speaker_personality"]}
            Location: {context["location"]}
            Relationship: {context["relationship_label"]} ({context["relationship_score"]:+d})
            
            Relevant memories:
            {memory_text}
            
            Generate one short sentence that {context["speaker"]} says to {context["listener"]}.
            """.strip()