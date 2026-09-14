from src.agents.agent import Agent
from src.agents.intent import AgentIntent
import random 

class IntentPlanner:
    def create_intent_from_goal(self, goal, strategy, current_day: int) -> AgentIntent:
        description = (
            f"{goal.agent_name} is pursuing '{goal.description}' through "
            f"{strategy.name.replace('_', ' ')}."
        )
        return AgentIntent(
            id=f"intent-{goal.id}-{current_day}-{goal.adaptation_count}-{strategy.name}",
            agent_name=goal.agent_name,
            intent_type=strategy.intent_type,
            description=description,
            created_day=current_day,
            expires_day=current_day + 2,
            priority=goal.priority,
            target_agent=strategy.target_agent,
            target_location=strategy.target_location,
            progress_goal=2,
            parent_goal_id=goal.id,
            strategy=strategy.name,
            strategy_score=strategy.score,
            relationship_influenced=strategy.relationship_influenced,
            relationship_reason=strategy.relationship_reason,
            relationship_snapshot=dict(strategy.relationship_snapshot),
            relevant_social_memories=list(strategy.relevant_social_memories),
        )

    def create_occupation_intent(
    self,
    agent: Agent,
    current_day: int,
    ) -> AgentIntent | None:
        occupation = agent.occupation.lower()
        text = " ".join(
            [
                agent.occupation,
                agent.personality,
                " ".join(agent.goal_descriptions()),
            ]
        ).lower()
    
        if "journalist" in occupation or "secrets" in text:
            return self.create_investigate_intent(
                agent_name=agent.name,
                current_day=current_day,
            )
    
        if "community organizer" in occupation or "help the town" in text:
            return self.create_socialize_intent(
                agent_name=agent.name,
                current_day=current_day,
            )
    
        if "merchant" in occupation or "business opportunities" in text:
            return self.create_work_intent(
                agent_name=agent.name,
                current_day=current_day,
            )
    
        if "accountant" in occupation or "reliable allies" in text:
            return self.create_investigate_intent(
                agent_name=agent.name,
                current_day=current_day,
            )
    
        return None
    
    def create_intent_for_agent(
        self,
        agent: Agent,
        engine,
        current_day: int,
    ) -> AgentIntent | None:
        weakest = self.get_weakest_relationship(agent, engine)
        strongest = self.get_strongest_relationship(agent, engine)

        if weakest and weakest[1] <= -2:
            return self.create_repair_relationship_intent(
                agent_name=agent.name,
                target_agent=weakest[0],
                current_day=current_day,
            )

        if strongest and strongest[1] >= 3:
            return self.create_build_friendship_intent(
                agent_name=agent.name,
                target_agent=strongest[0],
                current_day=current_day,
            )

        occupation_intent = self.create_occupation_intent(
            agent=agent,
            current_day=current_day,
        )
        
        if occupation_intent and random.random() < 0.45:
            return occupation_intent
        
        primary_need = agent.get_primary_need()
        
        if primary_need == "knowledge":
            return self.create_investigate_intent(
                agent_name=agent.name,
                current_day=current_day,
            )
        
        if primary_need == "social":
            return self.create_socialize_intent(
                agent_name=agent.name,
                current_day=current_day,
            )
        
        if primary_need == "wealth":
            return self.create_work_intent(
                agent_name=agent.name,
                current_day=current_day,
            )
        
        return occupation_intent

        

    def get_weakest_relationship(
        self,
        agent: Agent,
        engine,
    ) -> tuple[str, int] | None:
        relationships = []

        for other_agent in engine.agents:
            if other_agent.name == agent.name:
                continue

            score = engine.relationships.get_score(
                agent.name,
                other_agent.name,
            )

            relationships.append((other_agent.name, score))

        if not relationships:
            return None

        return min(relationships, key=lambda item: item[1])

    def get_strongest_relationship(
        self,
        agent: Agent,
        engine,
    ) -> tuple[str, int] | None:
        relationships = []

        for other_agent in engine.agents:
            if other_agent.name == agent.name:
                continue

            score = engine.relationships.get_score(
                agent.name,
                other_agent.name,
            )

            relationships.append((other_agent.name, score))

        if not relationships:
            return None

        return max(relationships, key=lambda item: item[1])

    def create_repair_relationship_intent(
        self,
        agent_name: str,
        target_agent: str,
        current_day: int,
    ) -> AgentIntent:
        return AgentIntent(
            agent_name=agent_name,
            intent_type="repair_relationship",
            target_agent=target_agent,
            target_location=None,
            description=(
                f"{agent_name} wants to repair their relationship "
                f"with {target_agent}."
            ),
            created_day=current_day,
            expires_day=current_day + 2,
            priority=5,
            progress_goal=2,
        )

    def create_build_friendship_intent(
        self,
        agent_name: str,
        target_agent: str,
        current_day: int,
    ) -> AgentIntent:
        return AgentIntent(
            agent_name=agent_name,
            intent_type="build_friendship",
            target_agent=target_agent,
            target_location=None,
            description=(
                f"{agent_name} wants to strengthen their bond "
                f"with {target_agent}."
            ),
            created_day=current_day,
            expires_day=current_day + 2,
            priority=4,
            progress_goal=2,
        )

    def create_investigate_intent(
        self,
        agent_name: str,
        current_day: int,
    ) -> AgentIntent:
        return AgentIntent(
            agent_name=agent_name,
            intent_type="investigate",
            target_agent=None,
            target_location="library",
            description=(
                f"{agent_name} wants to gather information "
                "about recent town activity."
            ),
            created_day=current_day,
            expires_day=current_day + 1,
            priority=3,
            progress_goal=2,
        )

    def create_socialize_intent(
        self,
        agent_name: str,
        current_day: int,
    ) -> AgentIntent:
        return AgentIntent(
            agent_name=agent_name,
            intent_type="socialize",
            target_agent=None,
            target_location="cafe",
            description=f"{agent_name} wants to spend time with other residents.",
            created_day=current_day,
            expires_day=current_day + 1,
            priority=2,
            progress_goal=2,
        )

    def create_work_intent(
        self,
        agent_name: str,
        current_day: int,
    ) -> AgentIntent:
        return AgentIntent(
            agent_name=agent_name,
            intent_type="seek_work",
            target_agent=None,
            target_location="market",
            description=f"{agent_name} wants to find work or business opportunities.",
            created_day=current_day,
            expires_day=current_day + 1,
            priority=2,
            progress_goal=2,
        )
