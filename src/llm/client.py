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
        recent_topics = context.get("recent_topics", [])
        recent_topic_text = ", ".join(recent_topics[-5:]) if recent_topics else "None"
        primary_need = context.get("primary_need", "social")
        daily_event = context.get("daily_event") 
        allowed_actions = context.get("allowed_actions", ["chat"])
        allowed_action_text = ", ".join(allowed_actions)
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

Recently used topics:
{recent_topic_text}

Relevant memories:
{memory_text}

Today's town event:
{daily_event_text}

Speaker goals:
{goal_text}

Current needs:
{need_text}

Primary need:
{primary_need}

Allowed actions:
{allowed_action_text}

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

Most conversations should be "chat".

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

Choose "compliment" when praising the listener.

Choose "share_rumor" only when discussing uncertain, unverified, or suspicious information.

Choose "argue" only when hostile.

Choose "insult" only for direct personal attacks.

Choose exactly one action from the allowed actions.

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

{{"dialogue": "text here", "action": "chat"}}
""".strip()
