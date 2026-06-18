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
        self.print_need_summary(engine)
        self.print_memory_summary(engine)
        self.print_topic_summary(engine)
        self.print_repetition_summary(engine)
        self.print_daily_event_usage(engine)

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

        if not memory_counts:
            print("\nNo memories recorded.")
            return

        most_memories_agent = max(
            memory_counts.items(),
            key=lambda item: item[1],
        )

        total_memories = sum(memory_counts.values())
        average_memories = total_memories / len(memory_counts)

        print("\nMemory summary:")
        print(f"  Total memories: {total_memories}")
        print(f"  Average memories per agent: {average_memories:.1f}")
        print(
            "  Most memories: "
            f"{most_memories_agent[0]} ({most_memories_agent[1]})"
        )

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
            print("\nRepeated dialogue rate: 0.0%")
            return

        dialogue_counts = Counter(
            memory.description.strip().lower()
            for memory in conversations
        )

        repeated_dialogues = sum(
            count - 1
            for count in dialogue_counts.values()
            if count > 1
        )

        repetition_rate = repeated_dialogues / len(conversations)

        print("\nRepetition summary:")
        print(f"  Repeated dialogue rate: {repetition_rate:.1%}")

        repeated_examples = [
            (dialogue, count)
            for dialogue, count in dialogue_counts.most_common()
            if count > 1
        ]

        if repeated_examples:
            print("  Most repeated dialogue:")
            for dialogue, count in repeated_examples[:5]:
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