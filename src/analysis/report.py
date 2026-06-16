from collections import Counter


class SimulationReporter:
    def summarize(self, engine) -> None:
        print("\n=== Town Summary ===")
        self.print_conversation_summary(engine)
        self.print_relationship_summary(engine)
        self.print_need_summary(engine)
        self.print_memory_summary(engine)

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

    def print_conversation_summary(self, engine) -> None:
        conversations = self.get_all_conversation_memories(engine)

        print(f"Total conversations: {len(conversations)}")

        action_counts = Counter()

        for memory in conversations:
            for tag in memory.tags:
                if tag in {
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
                }:
                    action_counts[tag] += 1

        if action_counts:
            most_common_action, count = action_counts.most_common(1)[0]
            print(f"Most common action: {most_common_action} ({count})")
        else:
            print("Most common action: none")

        if action_counts: 
            print("Action distribution:") 
            for action, count in action_counts.most_common(): 
                print(f" {action}: {count}")
                

    def print_relationship_summary(self, engine) -> None:
        if not engine.relationships.scores:
            print("No relationship changes recorded.")
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

        print(
            "Strongest relationship: "
            f"{strongest_agents[0]} <-> {strongest_agents[1]} "
            f"({strongest_score:+d}, {strongest_label})"
        )

        print(
            "Weakest relationship: "
            f"{weakest_agents[0]} <-> {weakest_agents[1]} "
            f"({weakest_score:+d}, {weakest_label})"
        )

    def print_need_summary(self, engine) -> None:
        need_totals = Counter()
        need_counts = Counter()

        for agent in engine.agents:
            for need, value in agent.needs.items():
                need_totals[need] += value
                need_counts[need] += 1

        if not need_totals:
            print("No need data available.")
            return

        print("Average needs:")

        for need in sorted(need_totals):
            average = need_totals[need] / need_counts[need]
            print(f"  {need}: {average:.1f}")

    def print_memory_summary(self, engine) -> None:
        memory_counts = {
            agent.name: len(agent.memory)
            for agent in engine.agents
        }

        if not memory_counts:
            print("No memories recorded.")
            return

        most_memories_agent = max(
            memory_counts.items(),
            key=lambda item: item[1],
        )

        print(
            "Most memories: "
            f"{most_memories_agent[0]} ({most_memories_agent[1]})"
        )