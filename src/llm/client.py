
import json

from src.systems.reputation import ReputationSystem


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
        if action == "share_rumor" and context.get("reputation_rumor"):
            dialogue = ReputationSystem.format_rumor_dialogue(
                context["reputation_rumor"]
            )

        return json.dumps({"dialogue": dialogue, "action": action})
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
                    '"tags": [], "grounding_refs": [], '
                    '"social_response": {"type": "accept_request|decline_request|counteroffer|acknowledge|unrelated|uncertain|none", "target": "help|meet|transfer|none", "confidence": "high|medium|low|none", "evidence": []}, '
                    '"commitment_relation": {"commitment_id": "", "relation": "planning_to_fulfill|fulfilling|references_fulfillment|acknowledges_failure|attempts_repair|unrelated|contradicts_state|none", "confidence": "high|medium|low|none"}, '
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
        session_transcript = context.get("session_transcript", [])
        transcript_lines = [
            f"{turn.get('speaker', 'Unknown')}: {turn.get('dialogue', '')}"
            for turn in session_transcript
        ]
        activity = context.get(
            "speaker_activity_display", context.get("speaker_activity", "idle")
        )
        activity_reason = context.get("speaker_activity_reason", "")
        activity_text = activity
        if activity_reason:
            activity_text = f"{activity} — {activity_reason}"

        goal = context.get("active_goal") or {}
        goal_text = goal.get("description", "None")
        if goal:
            goal_text += (
                f" (strategy: {goal.get('strategy') or 'unselected'}; "
                f"progress {goal.get('progress', 0)}/{goal.get('progress_target', 0)})"
            )
        relationship_snapshot = context.get("relationship_snapshot") or {}
        direct_experience = "Neutral; no direct history"
        if relationship_snapshot.get("interaction_count", 0):
            direct_experience = (
                f"trust {relationship_snapshot.get('trust', 0):+.2f}, "
                f"affinity {relationship_snapshot.get('affinity', 0):+.2f}, "
                f"cooperation {relationship_snapshot.get('cooperation', 0):+.2f}, "
                f"helpfulness {relationship_snapshot.get('helpfulness', 0):+.2f}, "
                f"hostility {relationship_snapshot.get('hostility', 0):+.2f}; "
                f"{relationship_snapshot.get('interaction_count', 0)} interactions"
            )
        anti_echo_instruction = ""
        if context.get("anti_echo_retry"):
            anti_echo_instruction = (
                "\n- Retry requirement: your previous attempt copied an earlier line. "
                "Answer with substantively new wording and content; do not paraphrase "
                "or restate any line in the current conversation."
            )
        grounding_correction = ""
        if context.get("grounding_correction"):
            grounding_correction = (
                "\n- Grounding retry: the prior line made an unsupported claim "
                f"({context['grounding_correction']}). Remove it, ask a question, or express "
                "uncertainty. Cite only a supplied grounding reference."
            )
        commitment_correction = ""
        if context.get("commitment_state_correction"):
            commitment_correction = (
                "\n- Commitment-state retry: the prior line contradicted the supplied "
                f"commitment status ({context['commitment_state_correction']}). State only "
                "what the supplied pair-private commitment record supports."
            )
        grounding_sources = context.get("grounding_sources", {})
        grounding_lines = [f"{ref} — {value}" for ref, value in grounding_sources.items()]
        commitment_records = context.get("commitment_records", [])
        commitment_lines = [
            f"[{row['commitment_id']}; {row['status']}] {row['text']}"
            for row in commitment_records
        ] or context.get("active_commitments", [])
        commitment_block = (
            "\nAuthoritative commitments involving this listener:\n"
            f"{lines(commitment_lines)}\nIDs are metadata: cite the matching ID in commitment_relation, never speak it. Make the commitment the line's "
            "primary focus and stay consistent with its status; never invent fulfillment."
            if commitment_lines else ""
        )
        repair_block = ""
        if context.get("repair_opportunities"):
            repair_block = (
                "\nA recent failed commitment creates bounded accountability pressure. "
                "You may acknowledge it, apologize, or make a concrete replacement proposal; "
                "do not claim it was fulfilled and do not assume a proposal is accepted."
            )

        return f"""
Write one natural line that {context['speaker']} says to {context['listener']}.

Immediate situation
- Place: {context['location']}
- Speaker's occupation: {context.get('occupation') or 'None'}
- What the speaker is doing: {activity_text}
- Relationship: {context['relationship_label']} ({context['relationship_score']:+d})
- Speaker's direct experience: {direct_experience}
- Voice cue: {context.get('speaker_personality') or 'None'}

What this speaker legitimately knows
Grounding references (metadata only; never speak IDs):
{lines(grounding_lines)}
Shared history:
{lines(context.get('relationship_history', []))}
Salient interpersonal episodes:
{lines(context.get('social_memories', []))}
Relevant memories:
{lines(context.get('relevant_memories', []))}
Speaker's beliefs about the listener's general conduct:
{lines(context.get('reputation_context', []))}
{commitment_block}{repair_block}{commitment_correction}
Supported third-party social claim available to share:
- {context.get('reputation_rumor_text') or 'None supplied'}
Latest journal reflection:
{lines(context.get('recent_journals', []))}
Long-term memory summary: {context.get('memory_summary') or 'None'}
Public event today: {event_text}
Ongoing local situations:
{lines(arcs)}

Personal direction
- Active durable goal: {goal_text}
- Current intent (a preference, not a script): {intent_text}
- Persistent goals: {', '.join(context.get('goals', [])) or 'None'}
- Primary unmet need: {context.get('primary_need') or 'None'}

Possible natural focus:
{lines(context.get('focus_options', []))}

Avoid unnecessary repetition
- Recent topics: {', '.join(context.get('recent_topics', [])) or 'None'}
- Recent lines by this speaker:
{lines(recent_utterances)}

Current conversation (shared spoken transcript):
{lines(transcript_lines)}
Your turn: respond as {context['speaker']}.

Social move
- Allowed actions: {', '.join(allowed_actions)}
- Suggested action: {suggested_action}

Requirements:
- On follow-up turns, the highest priority is responding meaningfully to the immediately preceding utterance. Answer or explicitly decline/express uncertainty about a direct question; do not replace the answer with a new question. Acknowledge a request; accept, decline, clarify, modify, or question an offer/proposal; react to a statement. Change topics only afterward.
- Use one focus; public events and ongoing situations are optional.
- Prefer a concrete, relationship-aware continuation.
- Let the voice cue shape wording/directness, occupation shape relevant perspective, and relationship shape tone. Never state traits, needs, goals, intents, scores, tags, or prompt metadata.
- Never repeat raw simulation wording such as "work on intent" or underscore-separated identifiers.
- Do not reuse a recent line or restart a settled topic unless something has changed.
- Assert facts only from the immediate situation or the supplied speaker knowledge. Do not invent named people, businesses, events, schedules, shortages, secrets, or rumors. Use hearsay wording only when a supplied source is itself uncertain.
- Use share_rumor only for the supported third-party social claim above. Keep its subject, dimension, and direction unchanged; present it cautiously rather than as certain fact.
- Do not default to "I heard" or "Have you heard." Without an explicitly uncertain supplied source, state an observation, opinion, request, or question instead.
- Treat memories and journals as past, not current events.
- Match the relationship tone. Tense or hostile speakers should not suddenly flatter, invite, or offer help.
- The suggested action is soft. The words and action must agree: assistance requests are ask_for_help, direct offers are offer_help, shared-task proposals are cooperate, praise is compliment, regret is apologize, disagreement is argue, and uncertain secondhand claims are share_rumor. Invitations and ordinary questions are chat.
- If using cooperate, explicitly propose doing a concrete task together with wording such as "let's" or "we can"; merely inviting the listener to look at or attend something is chat.
- Classify replies; positivity alone is not acceptance. Never invent fulfillment or IDs.
- One spoken line, normally under 35 words. No narration, stage directions, speaker name, or hidden reasoning.
{anti_echo_instruction}
{grounding_correction}

Return only valid JSON:
{{"dialogue":"spoken line","action":"allowed action","tags":[],"grounding_refs":[],"social_response":{{"type":"none","target":"none","confidence":"none"}},"commitment_relation":{{"commitment_id":"","relation":"none","confidence":"none"}},"reason":"brief reason"}}
""".strip()
