
class FakeLLMClient:
    is_deterministic_fake = True

    def generate_conversation(self, context: dict) -> str:
        action = context.get("suggested_action", "chat")

        dialogue_by_action = {
            "chat": "The town feels busy today.",
            "compliment": "You handled that really well.",
            "apologize": "I'm sorry about earlier.",
            "offer_help": "I can help you with that.",
            "ask_for_help": "Could you give me advice on where to start?",
            "argue": "I disagree. That plan does not make sense.",
            "insult": "That was a foolish way to handle it.",
            "storm_off": "I'm done talking about this.",
            "confess_feelings": "I have feelings for you.",
            "share_rumor": "I heard something strange about the market.",
            "cooperate": "We could work together on this.",
        }

        dialogue = dialogue_by_action.get(action, dialogue_by_action["chat"])

        return f'{{"dialogue": "{dialogue}", "action": "{action}"}}'
class TransformersLLMClient:
    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-3B-Instruct",
        *,
        max_new_tokens: int = 150,
        temperature: float = 0.4,
        top_p: float = 0.9,
    ):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.model_name = model_name
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.generation_config = {
            "max_new_tokens": max_new_tokens,
            "do_sample": True,
            "temperature": temperature,
            "top_p": top_p,
        }

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        ).to(self.device)

    def generate_conversation(self, context: dict) -> str:
        prompt = self._build_prompt(context)

        messages = [
            {
                "role": "system",
                "content": (
                    "You generate dialogue for a town simulation. "
                    "Never invent facts outside the supplied speaker knowledge. "
                    "Return only valid JSON. "
                    "Use exactly this JSON format: "
                    '{"dialogue": "short line of dialogue", '
                    '"action": "one allowed action", '
                    '"tags": [], '
                    '"reason": "why this action fits"}. '
                    "The action must be the best semantic label for the dialogue, not always chat. "
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

        inputs = self.tokenizer([text], return_tensors="pt").to(self.device)

        with self.torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                **self.generation_config,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        generated_ids = outputs[0][inputs["input_ids"].shape[-1]:]
        response = self.tokenizer.decode(generated_ids, skip_special_tokens=True)

        return response.strip()

    def _build_prompt(self, context: dict) -> str:
        def lines(values, empty="None supplied"):
            return "\n".join(f"- {value}" for value in values) or f"- {empty}"

        allowed_actions = context.get("allowed_actions", ["chat"])
        suggested_action = context.get("suggested_action", "chat")
        if suggested_action not in allowed_actions:
            suggested_action = "chat"

        intent = context.get("speaker_intent")
        intent_text = "None"
        if intent:
            intent_text = intent.get("description") or intent.get("intent_type", "None")

        event = context.get("daily_event")
        event_text = "None"
        if event:
            relevance = (
                "directly relevant here"
                if context.get("daily_event_relevant")
                else "public background; probably not today's topic"
            )
            event_text = f"{event['name']}: {event['description']} ({relevance})"

        arcs = [
            f"{arc['name']}: {arc['description']}"
            for arc in context.get("town_arcs", [])
        ]
        recent_utterances = context.get("recent_utterances", [])
        activity = context.get(
            "speaker_activity_display", context.get("speaker_activity", "idle")
        )
        activity_reason = context.get("speaker_activity_reason", "")
        activity_text = activity
        if activity_reason:
            activity_text = f"{activity} — {activity_reason}"

        return f"""
Write one natural line that {context['speaker']} says to {context['listener']}.

Immediate situation
- Place: {context['location']}
- Speaker's occupation: {context.get('occupation') or 'None'}
- What the speaker is doing: {activity_text}
- Relationship: {context['relationship_label']} ({context['relationship_score']:+d})
- Voice cue: {context.get('speaker_personality') or 'None'}

What this speaker legitimately knows
Shared history:
{lines(context.get('relationship_history', []))}
Relevant memories:
{lines(context.get('relevant_memories', []))}
Latest journal reflection:
{lines(context.get('recent_journals', []))}
Public event today: {event_text}
Ongoing local situations:
{lines(arcs)}

Personal direction
- Current intent (a preference, not a script): {intent_text}
- Persistent goals: {', '.join(context.get('goals', [])) or 'None'}
- Primary unmet need: {context.get('primary_need') or 'None'}

Possible natural focus:
{lines(context.get('focus_options', []))}

Avoid unnecessary repetition
- Recent topics: {', '.join(context.get('recent_topics', [])) or 'None'}
- Recent lines by this speaker:
{lines(recent_utterances)}

Social move
- Allowed actions: {', '.join(allowed_actions)}
- Suggested action: {suggested_action}

Requirements:
- Use one focus, not every context item. The public event and ongoing situations are optional.
- Prefer a concrete, relationship-aware continuation over a greeting or generic town commentary.
- Express personality through word choice and judgment; never state traits, needs, goals, intent labels, scores, tags, or prompt metadata.
- Never repeat raw simulation wording such as "work on intent" or underscore-separated identifiers.
- Do not reuse a recent line or restart a settled topic unless something has changed.
- Assert facts only from the immediate situation or the supplied speaker knowledge. Do not invent named people, businesses, events, schedules, shortages, secrets, or rumors. Use hearsay wording only when a supplied source is itself uncertain.
- Do not default to "I heard" or "Have you heard." Without an explicitly uncertain supplied source, state an observation, opinion, request, or question instead.
- Keep past memories and journals in the past. Do not present them as happening today.
- Match the relationship tone. Tense or hostile speakers should not suddenly flatter, invite, or offer help.
- The suggested action is a soft direction. Follow it when context supports it; otherwise choose a better allowed action. The words and action must agree: requests for assistance are ask_for_help, direct offers are offer_help, shared-task proposals are cooperate, praise is compliment, regret is apologize, disagreement is argue, and uncertain secondhand claims are share_rumor. Invitations and ordinary questions are chat.
- One spoken line, normally under 35 words. No narration, stage directions, speaker name, or hidden reasoning.

Return only valid JSON:
{{"dialogue": "spoken line", "action": "one allowed action", "tags": ["conversation"], "reason": "brief grounding reason"}}
""".strip()
