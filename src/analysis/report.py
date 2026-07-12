from collections import Counter

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

RELATIONSHIP_LABELS = {
    "close friends",
    "friendly",
    "neutral",
    "tense",
    "enemies",
}


class SimulationReporter:
    def summarize(self, engine) -> None:
        print("\n=== Town Summary ===")
        self.print_conversation_summary(engine)
        self.print_activity_summary(engine)
        self.print_relationship_summary(engine)
        self.print_relationship_distribution(engine)
        self.print_relationship_event_summary(engine)
        self.print_intent_summary(engine)
        self.print_town_arc_summary(engine)
        self.print_need_summary(engine)
        self.print_memory_summary(engine)
        self.print_topic_summary(engine)
        self.print_repetition_summary(engine)
        self.print_daily_event_usage(engine)
        self.print_journal_summary(engine)

    def print_journal_summary(self, engine) -> None:
        print("\nDaily journal summary:")
    
        for agent in engine.agents:
            print(
                f"  {agent.name}: "
                f"{len(agent.daily_journals)} journal entries, "
                f"{len(agent.memory)} active memories, "
                f"{len(agent.memory_archive)} archived memories"
            )
    
            if agent.daily_journals:
                latest = agent.daily_journals[-1]
                print(
                    f"    Latest day {latest.day}: "
                    f"{latest.summary}"
            )
            
    def print_town_arc_summary(self, engine) -> None:
        town_arcs = getattr(engine, "town_arcs", [])

        if not town_arcs:
            print("\nNo town arcs recorded.")
            return

        active_arcs = [
            arc
            for arc in town_arcs
            if arc.is_active()
        ]

        print("\nTown arc summary:")
        print(f"  Total arcs: {len(town_arcs)}")
        print(f"  Active arcs: {len(active_arcs)}")

        arc_name_counts = Counter(
            arc.name
            for arc in town_arcs
        )

        print("  Arcs by type:")
        for arc_name, count in arc_name_counts.most_common():
            print(f"    {arc_name}: {count}")
        for arc in town_arcs:
            print(
                f"  {arc.name}: {arc.status}, "
                f"location={arc.location_id or 'town'}, "
                f"tension={arc.tension}, progress={arc.progress}"
            )
            
    def print_intent_summary(self, engine) -> None:
        agent_intents = getattr(engine, "agent_intents", {})
        intent_history = getattr(engine, "intent_history", [])
    
        if not agent_intents and not intent_history:
            print("\nNo agent intents recorded.")
            return
    
        active_intents = {
            agent_name: intent
            for agent_name, intent in agent_intents.items()
            if intent.status == "active"
        }
    
        active_counts = Counter(
            intent.intent_type
            for intent in active_intents.values()
        )
    
        history_status_counts = Counter(
            intent.status
            for intent in intent_history
        )
    
        print("\nAgent intent summary:")
        print(f"  Active intents: {len(active_intents)}")
        print(f"  Completed/ended intents: {len(intent_history)}")
    
        if active_counts:
            print("  Active intents by type:")
            for intent_type, count in active_counts.most_common():
                print(f"    {intent_type}: {count}")
    
        if active_intents:
            print("  Current intents:")
            for agent_name, intent in sorted(active_intents.items()):
                target = intent.target_agent or intent.target_location or "general"
                print(
                    f"    {agent_name}: {intent.intent_type} -> {target} "
                    f"progress {intent.progress}/{intent.progress_goal} "
                    f"(expires day {intent.expires_day})"
                )
    
        if history_status_counts:
            print("  Intent outcomes:")
            for status, count in history_status_counts.most_common():
                print(f"    {status}: {count}")
    
        recent_history = intent_history[-5:]
    
        if recent_history:
            print("  Recent completed/ended intents:")
            for intent in recent_history:
                target = intent.target_agent or intent.target_location or "general"
                print(
                    f"    {intent.agent_name}: {intent.intent_type} -> {target} "
                    f"{intent.status} on day {intent.completed_day} "
                    f"({intent.completion_reason})"
                )
                
    def print_relationship_event_summary(self, engine) -> None:
        relationship_events = getattr(engine, "relationship_events", [])
    
        if not relationship_events:
            print("\nNo relationship events recorded.")
            return
    
        action_counts = Counter(
            event.action
            for event in relationship_events
        )
    
        positive_events = sum(
            1 for event in relationship_events
            if event.relationship_change > 0
        )
    
        negative_events = sum(
            1 for event in relationship_events
            if event.relationship_change < 0
        )
    
        neutral_events = sum(
            1 for event in relationship_events
            if event.relationship_change == 0
        )
    
        print("\nRelationship event summary:")
        print(f"  Total relationship events: {len(relationship_events)}")
        print(f"  Positive events: {positive_events}")
        print(f"  Negative events: {negative_events}")
        print(f"  Neutral events: {neutral_events}")
    
        print("  Events by action:")
        for action, count in action_counts.most_common():
            print(f"    {action}: {count}")

        positive_followup_actions = 0
        negative_followup_actions = 0
        
        for event in relationship_events:
            if event.relationship_change > 0 and event.action in {
                "compliment",
                "offer_help",
                "cooperate",
                "ask_for_help",
                "chat",
            }:
                positive_followup_actions += 1
        
            if event.relationship_change < 0 and event.action in {
                "apologize",
                "argue",
                "storm_off",
                "insult",
                "chat",
            }:
                negative_followup_actions += 1
        
        print(f"  Positive/repair social actions: {positive_followup_actions}")
        print(f"  Negative/guarded social actions: {negative_followup_actions}")
        
    def get_all_conversation_memories(self, engine):
        memories = []

        for agent in engine.agents:
            for memory in agent.memory:
                if memory.type == "conversation":
                    memories.append(memory)

        # Each conversation is stored for both speaker and listener,
        # so deduplicate using day/hour/location/description.
        unique = {}
        for memory in memories:
            key = (
                memory.day,
                memory.hour,
                memory.location,
                memory.description,
            )
            unique[key] = memory

        return list(unique.values())

    def print_activity_summary(self, engine) -> None:
        activity_records = getattr(engine, "activity_records", [])

        if not activity_records:
            print("No activity data available.")
            return

        activity_counts = Counter(
            record["activity_name"]
            for record in activity_records
        )

        location_counts = Counter(
            record["location"]
            for record in activity_records
        )

        print("\nActivity distribution:")
        for activity_name, count in activity_counts.most_common():
            print(f"  {activity_name}: {count}")

        print("\nLocation distribution:")
        for location, count in location_counts.most_common():
            print(f"  {location}: {count}")

    def print_conversation_summary(self, engine) -> None:
        conversations = self.get_all_conversation_memories(engine)

        print(f"\nTotal conversations: {len(conversations)}")

        action_counts = Counter()
        conversations_by_day = Counter()

        for memory in conversations:
            conversations_by_day[memory.day] += 1

            for tag in memory.tags:
                if tag in ACTION_TAGS:
                    action_counts[tag] += 1

        if action_counts:
            most_common_action, count = action_counts.most_common(1)[0]
            print(f"Most common action: {most_common_action} ({count})")
        else:
            print("Most common action: none")

        if action_counts:
            print("\nAction distribution:")
            total_actions = sum(action_counts.values())

            for action, count in action_counts.most_common():
                percentage = count / total_actions
                print(f"  {action}: {count} ({percentage:.1%})")

        if conversations_by_day:
            print("\nConversations by day:")
            for day in sorted(conversations_by_day):
                print(f"  Day {day}: {conversations_by_day[day]}")

    def print_relationship_summary(self, engine) -> None:
        if not engine.relationships.scores:
            print("\nNo relationship changes recorded.")
            return

        strongest_pair = max(
            engine.relationships.scores.items(),
            key=lambda item: item[1],
        )

        weakest_pair = min(
            engine.relationships.scores.items(),
            key=lambda item: item[1],
        )

        strongest_agents, strongest_score = strongest_pair
        weakest_agents, weakest_score = weakest_pair

        strongest_label = engine.relationships.describe_relationship(
            strongest_agents[0],
            strongest_agents[1],
        )

        weakest_label = engine.relationships.describe_relationship(
            weakest_agents[0],
            weakest_agents[1],
        )

        scores = list(engine.relationships.scores.values())
        average_score = sum(scores) / len(scores)

        print("\nRelationship summary:")
        print(f"  Average relationship score: {average_score:+.2f}")

        print(
            "  Strongest relationship: "
            f"{strongest_agents[0]} <-> {strongest_agents[1]} "
            f"({strongest_score:+d}, {strongest_label})"
        )

        print(
            "  Weakest relationship: "
            f"{weakest_agents[0]} <-> {weakest_agents[1]} "
            f"({weakest_score:+d}, {weakest_label})"
        )

    def print_relationship_distribution(self, engine) -> None:
        if not engine.relationships.scores:
            return

        label_counts = Counter()

        for (agent_a, agent_b) in engine.relationships.scores:
            label = engine.relationships.describe_relationship(
                agent_a,
                agent_b,
            )
            label_counts[label] += 1

        print("\nRelationship distribution:")

        for label in [
            "close friends",
            "friendly",
            "neutral",
            "tense",
            "enemies",
        ]:
            print(f"  {label}: {label_counts[label]}")

    def print_need_summary(self, engine) -> None:
        need_totals = Counter()
        need_counts = Counter()

        for agent in engine.agents:
            for need, value in agent.needs.items():
                need_totals[need] += value
                need_counts[need] += 1

        if not need_totals:
            print("\nNo need data available.")
            return

        print("\nAverage needs:")

        for need in sorted(need_totals):
            average = need_totals[need] / need_counts[need]
            print(f"  {need}: {average:.1f}")

    def print_memory_summary(self, engine) -> None:
        memory_counts = {
            agent.name: len(agent.memory)
            for agent in engine.agents
        }

        total_memories = sum(memory_counts.values())

        if not memory_counts:
            print("\nMemory summary:")
            print("  Total memories: 0")
            return

        average_memories = total_memories / len(memory_counts)

        most_memory_agent = max(
            memory_counts.items(),
            key=lambda item: item[1],
        )

        memory_type_counts = Counter()

        archived_memory_counts = {
            agent.name: len(getattr(agent, "memory_archive", []))
            for agent in engine.agents
        }

        total_archived_memories = sum(archived_memory_counts.values())

        for agent in engine.agents:
            for memory in agent.memory:
                memory_type_counts[memory.type] += 1

        print("\nMemory summary:")
        print(f"  Total memories: {total_memories}")
        print(f"  Average memories per agent: {average_memories:.1f}")
        print(f"  Most memories: {most_memory_agent[0]} ({most_memory_agent[1]})")
        print(f"  Archived memories: {total_archived_memories}")
        print("  Memories by type:")
        for memory_type, count in memory_type_counts.most_common():
            print(f"    {memory_type}: {count}")

    def print_topic_summary(self, engine) -> None:
        conversations = self.get_all_conversation_memories(engine)
        topic_counts = Counter()

        for memory in conversations:
            for tag in memory.tags:
                if tag not in ACTION_TAGS and tag not in RELATIONSHIP_LABELS:
                    topic_counts[tag] += 1

        if not topic_counts:
            print("\nNo topic data available.")
            return

        print("\nTopic summary:")
        print(f"  Unique topic tags: {len(topic_counts)}")

        print("  Most common topics:")
        for topic, count in topic_counts.most_common(10):
            print(f"    {topic}: {count}")

    def print_repetition_summary(self, engine) -> None:
        conversations = self.get_all_conversation_memories(engine)

        if not conversations:
            print("\nRepetition summary:")
            print("  Repeated dialogue rate: 0.0%")
            return

        dialogue_counts = Counter(
            memory.description.strip()
            for memory in conversations
        )

        repeated_dialogues = {
            dialogue: count
            for dialogue, count in dialogue_counts.items()
            if count > 1
        }

        repeated_total = sum(
            count - 1
            for count in repeated_dialogues.values()
        )

        repeated_rate = repeated_total / len(conversations)

        print("\nRepetition summary:")
        print(f"  Repeated dialogue rate: {repeated_rate:.1%}")

        if repeated_dialogues:
            print("  Most repeated dialogue lines:")
            for dialogue, count in Counter(repeated_dialogues).most_common(5):
                print(f"    {count}x: {dialogue}")

    def print_daily_event_usage(self, engine) -> None:
        conversations = self.get_all_conversation_memories(engine)

        if not conversations:
            print("\nDaily event mention rate: 0.0%")
            return

        event_related = 0

        for memory in conversations:
            if "event" in memory.tags:
                event_related += 1

        rate = event_related / len(conversations)

        print("\nDaily event usage:")
        print(f"  Event-related conversations: {event_related}")
        print(f"  Daily event mention rate: {rate:.1%}")