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
                max_new_tokens=150,
                do_sample=True,
                temperature=0.4,
                top_p=0.9,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        generated_ids = outputs[0][inputs["input_ids"].shape[-1]:]
        response = self.tokenizer.decode(generated_ids, skip_special_tokens=True)

        return response.strip()

    def _build_prompt(self, context: dict) -> str:
        memories = context.get("relevant_memories", [])
        goals = context.get("goals", [])
        needs = context.get("needs", {})
        primary_need = context.get("primary_need", "social")
        daily_event = context.get("daily_event") 
        if daily_event:
            daily_event_text = (
                f"{daily_event['name']}: {daily_event['description']} "
                f"Location: {daily_event['location_id']}"
            )
        else:
            daily_event_text = "No major town event today."
        need_text = "\n".join(
            f"- {need}: {value}"
            for need, value in needs.items()
        )
        
        if not need_text:
            need_text = "- No needs available."
            
        goal_text = "\n".join(
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
    Speaker occupation: {context["occupation"]}
    Relationship: {context["relationship_label"]} ({context["relationship_score"]:+d})
    
    Relevant memories:
    {memory_text}
    Today's town event:
    {daily_event_text}

    If the daily event is relevant to the speaker, listener, or location, naturally mention it. Do not force the daily event into every conversation.
    Relevant memories are rcent context, not mandatory topics. 
    Do not repeat the same topic unless it naturally follows 
    from the current conversation. Prefer today's event, current location, occupation, and primary need over old memories.
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
    Do not overuse rumors, secres, haunted places, shady dealings, or hidden treasure. Most conversations should be ordinary daily life, work, friendship, errands, or mild curiosity. Only use rumors occassionally. Use the speaker's occupation to create ordinary, grounded conversation.
Prefer topics about work, errands, relationships, local events, hobbies, or daily life. 
Avoid making every conversation about mysteries, secrets, haunted places, clocks, hidden treasures, or shady dealings.
        Write exactly one short line of dialogue that {context["speaker"]} says to {context["listener"]}.
    Speaker goals: {goal_text}
    Current needs: {need_text} 
    Primary need: {primary_need}
Return only JSON.
""".strip()