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
            dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
            device_map="auto",
        )

    def generate_conversation(self, context: dict) -> str:
        prompt = self._build_prompt(context)

        messages = [
            {
                "role": "system",
                "content": (
                    "You generate dialogue for a town simulation. "
                    "Return only valid JSON." 
                    "Use exactly this format: " 
                    '{"dialogue": "short line of dialogue", "action": "chat"}. '
                    "No narration. No markdown." 
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
        goals = context.get("goals", [])

        goal_text = "\n".join(f"- {goal}"
            f"- {goal}"
            for goal in goals
        )

        if not goal_text:
            goal_text = "- No specific goals."
            
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
    
    Write exactly one short line of dialogue that {context["speaker"]} says to {context["listener"]}.
    Do not include {context["speaker"]}'s name.
    Do not include narration or actions.

    Allowed actions:
    chat, compliment, apologize, offer_help, ask_for_help, argue, insult, storm_off, confess_feelings, share_rumor
    
    Choose exactly one action from the allowed actions.
    Prefer "chat" for ordinary conversation. 
    Use "argue" only when the dialogue is clearly hostile.
    Use "insult" only for direct personal attacks. 
    Do not choose "argue" for rumors, questions, or mild disagreement.
        Write exactly one short line of dialogue that {context["speaker"]} says to {context["listener"]}.
    Speaker goals: {goal_text}
Return only JSON.
""".strip()