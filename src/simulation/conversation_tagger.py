from src.town.daily_event import DailyEvent
from src.llm.parser import infer_conversation_tags


class ConversationTagger:
    ACTION_TAGS = {
        "chat",
        "compliment",
        "apologize",
        "offer_help",
        "ask_for_help",
        "argue",
        "insult",
        "storm_off",
        "confess_feelings",
        "share_rumor",
        "cooperate",
    }

    def get_initial_conversation_tags(
        self,
        conversation: str,
        parsed_tags: list[str] | None = None,
    ) -> list[str]:
        conversation_tags = infer_conversation_tags(conversation)
        conversation_tags.extend(parsed_tags or [])

        return conversation_tags

    def add_daily_event_tags(
        self,
        conversation: str,
        conversation_tags: list[str],
        current_daily_event: DailyEvent | None,
    ) -> list[str]:
        updated_tags = list(conversation_tags)

        if not current_daily_event:
            return updated_tags

        dialogue_lower = conversation.lower()

        event_name_words = [
            word
            for word in current_daily_event.name.lower().split()
            if len(word) >= 4
        ]

        mentions_event = any(
            word in dialogue_lower
            for word in event_name_words
        )

        if mentions_event or "event" in updated_tags:
            updated_tags.append("event")
            updated_tags.append(current_daily_event.id)

        return updated_tags

    def remove_action_tags(
        self,
        conversation_tags: list[str],
    ) -> list[str]:
        return [
            tag
            for tag in conversation_tags
            if tag not in self.ACTION_TAGS
        ]

    def finalize_conversation_tags(
        self,
        conversation: str,
        conversation_tags: list[str],
        current_daily_event: DailyEvent | None,
        relationship_label: str,
        action: str,
    ) -> list[str]:
        final_tags = self.add_daily_event_tags(
            conversation=conversation,
            conversation_tags=conversation_tags,
            current_daily_event=current_daily_event,
        )

        final_tags = self.remove_action_tags(final_tags)

        final_tags.append(relationship_label)
        final_tags.append(action)

        return list(dict.fromkeys(final_tags))