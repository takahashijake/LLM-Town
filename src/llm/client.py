
class FakeLLMClient:
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
    def __init__(self, model_name: str = "Qwen/Qwen2.5-3B-Instruct"):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
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

        inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)

        with self.torch.no_grad():
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
        recent_topics = context.get("recent_topics", [])
        speaker_activity = context.get("speaker_activity", "idle")
        speaker_activity_reason = context.get("speaker_activity_reason", "")
        speaker_activity_tags = context.get("speaker_activity_tags", [])
        speaker_activity_tag_text = ", ".join(speaker_activity_tags) if speaker_activity_tags else "None"
        recent_topic_text = ", ".join(recent_topics[-5:]) if recent_topics else "None"
        primary_need = context.get("primary_need", "social")
        daily_event = context.get("daily_event") 
        town_arcs = context.get("town_arcs", [])
        allowed_actions = context.get("allowed_actions", ["chat"])
        allowed_action_text = ", ".join(allowed_actions)

        suggested_action = context.get("suggested_action", "chat") 
        memory_summary = context.get("memory_summary", "")
        if town_arcs:
            town_arc_text = "\n".join(
                (
                    f"- {arc['name']} ({arc['status']}): "
                    f"{arc['description']} "
                    f"Location: {arc.get('location_id') or 'town'}. "
                    f"Tension: {arc.get('tension', 0)}. "
                    f"Progress: {arc.get('progress', 0)}."
                )
                for arc in town_arcs
            )
        else:
            town_arc_text = "- No active town arcs relevant to this location."
        if suggested_action not in allowed_actions: 
            suggested_action = "chat"
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

        relationship_history = context.get("relationship_history", [])
        speaker_intent = context.get("speaker_intent")
        listener_intent = context.get("listener_intent")
        
        if speaker_intent:
            speaker_intent_text = (
                f"{speaker_intent['intent_type']}: "
                f"{speaker_intent['description']}"
            )
        else:
            speaker_intent_text = "No active intent."
        
        if listener_intent:
            listener_intent_text = (
                f"{listener_intent['intent_type']}: "
                f"{listener_intent['description']}"
            )
        else:
            listener_intent_text = "No active intent."
    
        relationship_history_text = "\n".join(
            f"- {event}"
            for event in relationship_history
        )
        
        if not relationship_history_text:
            relationship_history_text = "- No major relationship history between these two yet."
        return f"""
Speaker: {context["speaker"]}
Listener: {context["listener"]}
Speaker personality: {context["speaker_personality"]}
Location: {context["location"]}
Speaker occupation: {context["occupation"]}
Current activity: {speaker_activity}
Activity reason: {speaker_activity_reason}
Activity tags: {speaker_activity_tag_text}
Relationship: {context["relationship_label"]} ({context["relationship_score"]:+d})

Recent relationship history:
{relationship_history_text}

Speaker current intent:
{speaker_intent_text}

Listener current intent:
{listener_intent_text}

Recently used topics:
{recent_topic_text}

Relevant memories:
{memory_text}

Long-term memory summary:
{memory_summary if memory_summary else "No long-term summary yet."}

Today's town event:
{daily_event_text}

Relevant town arcs:
{town_arc_text}

Speaker goals:
{goal_text}

Current needs:
{need_text}

Primary need:
{primary_need}

Allowed actions:
{allowed_action_text}

Suggested action:
{suggested_action}

Intent rules:
- The speaker's intent is a soft goal, not a command.
- If the intent naturally fits the location, listener, relationship, and current activity, reflect it in the dialogue.
- Do not force the intent if it would feel unnatural.
- If the speaker has a target agent intent and the listener is that target, the dialogue may more directly support that intent.

Town arc rules:
- Town arcs are ongoing multi-day situations.
- Mention a town arc only when it naturally fits the location, activity, intent, or relationship.
- Do not force town arcs into every conversation.
- If a town arc is relevant, treat it as background context that residents may gradually discuss across days.

The suggested action controls the intended social move for this line.

If the suggested action is not "chat", you should usually use it.
Only ignore a non-chat suggested action if it clearly violates the relationship rules or allowed actions.

When using a non-chat suggested action, the dialogue must contain clear wording that matches that action:
- ask_for_help: ask the listener for advice, information, or assistance.
- offer_help: offer to help the listener directly.
- cooperate: suggest working together on a shared task.
- share_rumor: mention uncertain, secondhand, or suspicious information.
- compliment: clearly praise the listener.
- argue: clearly disagree or challenge the listener.
- apologize: clearly express regret.

Do not label generic observations as non-chat.
Do not use "chat" when the dialogue clearly asks for help, offers help, suggests cooperation, shares a rumor, apologizes, compliments, or argues.

The speaker's current activity is the most important context.
The dialogue should usually relate to the current activity or the listener's presence at the same location.
Avoid generic filler dialogue.
Do not say vague lines like:
- "There is a lot happening around town today."
- "This place has had a lot going on today."
- "I have been trying to keep up with everything going on."
- "This place feels more active than usual."
- "The town has changed lately."

Instead, mention one concrete detail from the current activity, location, daily event, relationship history, town arc, or memory.

Do not ignore the current activity unless another context item is clearly more relevant.

Avoid starting with "Have you heard" unless the speaker is investigating, reporting news, or sharing a rumor.
Prefer concrete activity-grounded lines.

IMPORTANT CONVERSATION RULES

Recently used topics are context only.
Avoid repeating recently used topics unless they are highly relevant.

The daily event is only ONE possible topic.
The conversation may also be about:

* work
* hobbies
* family
* friendships
* local town life
* recent experiences
* errands
* goals
* current needs
* personal interests
* occupations
* observations about the location

Do not force the daily event into every conversation.
The daily event should be mentioned in fewer than half of conversations. Many conversations should ignore the daily event completely. 

A small percentage of conversations should naturally:
- offer assistance
- compliment someone
- ask for advice
- share concerns
- discuss cooperation on a task

Not every conversation should be ordinary chat.
Today's event is happening today.
Memory timing rules:

* Relevant memories may be from previous days.
* If a memory says it happened days ago, treat it as a past event.
* Do not describe old memories as happening today.
* Only today's town event is happening today.
* If mentioning a past event, use wording like "recently", "earlier this week", or "the other day".

Do not refer to today's event as:

* tomorrow
* next week
* last night
* yesterday

Relationship behavior rules:

close friends:

* warm
* trusting
* cooperative
* comfortable sharing personal thoughts

friendly:

* positive
* kind
* casually helpful

neutral:

* polite
* ordinary
* casual

tense:

* guarded
* skeptical
* cautious
* reluctant

enemies:

* cold
* dismissive
* distrustful
* avoidant

If relationship is tense or enemies:

* do not invite the listener to activities
* do not offer help
* do not compliment
* do not suggest working together

Avoid phrases like:

* "want to check it out together"
* "join me"
* "grab coffee together"
* "team up"

The dialogue tone must match the relationship.

TOPIC DIVERSITY RULES

Many conversations should be simple statements.

Examples:

* observations
* opinions
* reactions
* comments about work
* comments about the current location
* sharing news
* discussing goals
* discussing needs

Do not end every conversation with a question.

Questions should appear in less than half of conversations.

Many conversations should simply share information or make an observation.

ACTION SELECTION RULES

Most conversations should be "chat", but the simulation may suggest a non-chat action to create social variety.

When the suggested action is non-chat, try to write dialogue that clearly matches that action.

Examples:
- If suggested action is "compliment", the dialogue should clearly praise the listener.
- If suggested action is "offer_help", the dialogue should clearly offer assistance.
- If suggested action is "ask_for_help", the dialogue should clearly ask for advice, information, or assistance.
- If suggested action is "apologize", the dialogue should clearly express regret.
- If suggested action is "share_rumor", the dialogue should clearly mention uncertain or secondhand information.
- If suggested action is "argue", the dialogue should clearly disagree or challenge the listener.
- If suggested action is "cooperate", the dialogue should clearly suggest working together on a shared task.
Across many conversations, around 20-30% should use a non-chat action when context supports it.

Prefer a non-chat action when the speaker is clearly:
- praising the listener
- offering help
- asking for help or advice
- apologizing
- sharing uncertain information or a rumor
- challenging or arguing with the listener

Choose "chat" for:

* observations
* opinions
* invitations
* greetings
* casual discussion
* sharing information
* discussing events
* asking someone if they want to attend something
* asking what they think about something

Choose "ask_for_help" ONLY when the speaker genuinely needs:

* assistance
* advice
* directions
* expertise
* information required to solve a problem

Do NOT use "ask_for_help" for:

* invitations
* casual questions
* social conversation
* asking if someone wants to join an activity

Choose "offer_help" when the speaker offers assistance or useful help.
Examples:
- "I can help you with that."
- "Let me lend a hand."
- "I could help organize that."
- "I can show you where to start."

Choose "compliment" when praising the listener's skill, work, effort, personality, or judgment.
Examples:
- "You did a good job organizing that."
- "You always know how to bring people together."
- "That was impressive work."
- "You're good at this."

Choose "ask_for_help" when the speaker genuinely asks the listener for assistance, advice, expertise, directions, or information needed to solve a problem.
Examples:
- "Can you help me figure this out?"
- "Do you know where I should start?"
- "Could you give me advice?"
- "Can you show me how to do that?"

Choose "apologize" when the speaker expresses regret or says sorry.
Examples:
- "I'm sorry about earlier."
- "I should have handled that better."
- "I apologize for what I said."

Choose "cooperate" when the speaker suggests working together on a shared task.
Examples:
- "Want to team up for the cleanup?"
- "We could work together on this."
- "Let's coordinate with the volunteers."
- "Want to pitch in together?"

Choose "share_rumor" ONLY when the speaker is sharing information that is uncertain, unverified, suspicious, secretive, or potentially reputation-damaging.

Use "share_rumor" for:
- "I heard something strange about the market."
- "Someone said the supplier might be unreliable."
- "There is a rumor going around, but I do not know if it is true."
- "People are saying the new vendor may be hiding something."

Do NOT use "share_rumor" for ordinary public information, event announcements, observations, or local news.

Use "chat" instead for:
- "Did you hear about the bakery opening?"
- "The samples are popular today."
- "There are extra trash bins around town."
- "A lot of people came to the cleanup."
- "The book club is meeting at the library."

Examples:
- "I heard something strange about the market."
- "There is a rumor going around."
- "Someone said the supplier might be unreliable."
- "I am not sure it is true, but people are talking."

Choose "argue" when the speaker disagrees sharply, challenges, criticizes, or confronts the listener.
Examples:
- "I do not think you handled that well."
- "Why are you making this harder?"
- "That plan does not make sense."
- "You are wrong about this."

Choose "insult" only for direct personal attacks.
Also, you must only choose exactly one action from the allowed actions. 
CONTENT RULES

Do not overuse:

* rumors
* secrets
* haunted places
* hidden treasure
* conspiracies
* shady dealings

Most conversations should focus on:

* daily life
* work
* occupations
* hobbies
* errands
* friendships
* local events

Conversation style:

Randomly choose ONE style:

- observation
- opinion
- personal experience
- work discussion
- local news
- recommendation
- complaint
- joke
- question

Do not use the same style every conversation.

Examples of good chat:

Observation:
"The market seems busier than usual today."

Opinion:
"I think the new bakery will do well."

Personal experience:
"I tried that recipe yesterday and it turned out surprisingly good."

Work discussion:
"I've had three customers ask about that today."

Recommendation:
"The gardening workshop was actually more useful than I expected."

Complaint:
"The rain has made deliveries a nightmare this week."
Use the speaker's occupation when appropriate.

Do not include the speaker's name.

Do not include narration.

Do not include stage directions.

Write exactly one short line of dialogue that {context["speaker"]} says to {context["listener"]}.

Return ONLY valid JSON in this format:

{{"dialogue": "text here", "action": "one of the allowed actions", "tags": ["conversation"], "reason": "short explanation"}}

The "action" must describe the intent of the dialogue.
If the dialogue praises the listener, use "compliment".
If the dialogue offers assistance, use "offer_help".
If the dialogue asks for assistance, advice, expertise, or information needed to solve a problem, use "ask_for_help".
If the dialogue shares uncertain or secondhand information, use "share_rumor".
If the dialogue suggests working together on a shared task, use "cooperate".
Use "chat" only when none of the more specific allowed actions fit."
""".strip()
