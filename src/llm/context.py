def build_conversation_context(speaker, listener, location_id, relationship_label, relationship_score):
    return {
        "speaker": speaker.name,
        "listener": listener.name,
        "speaker_personality": speaker.personality,
        "location": location_id,
        "relationship_label": relationship_label,
        "relationship_score": relationship_score,
        "recent_memories": [
            memory.description
            for memory in speaker.get_relevant_memories(listener.name, limit=5)
        ],
        "goals" : speaker.goals,
    }