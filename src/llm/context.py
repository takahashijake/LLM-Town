def build_conversation_context(
    speaker,
    listener,
    location_id,
    relationship_label,
    relationship_score,
    current_day: int,
    daily_event=None,
    allowed_actions=None,
):
    return {
        "speaker": speaker.name,
        "listener": listener.name,
        "speaker_personality": speaker.personality,
        "location": location_id,
        "relationship_label": relationship_label,
        "recent_topics" : speaker.recent_topics,
        "relationship_score": relationship_score,
        "relevant_memories": [
            memory.description
            for memory in speaker.get_relevant_memories(
                listener.name,
                current_day=current_day,
                limit=3,
                max_age_days=5,
            )
        ],
        "goals" : speaker.goals,
        "needs" : speaker.needs, 
        "occupation" : speaker.occupation,
        "primary_need" : speaker.get_primary_need(),
        "allowed_actions" : allowed_actions or ["chat"],
        "daily_event": {
            "id" : daily_event.id,
            "name": daily_event.name,
            "description": daily_event.description,
            "location_id": daily_event.location_id,
            "tags": daily_event.tags,
        } if daily_event else None,
    }