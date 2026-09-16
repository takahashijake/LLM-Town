from src.actions.action_system import ActionSystem
from src.agents.agent import Agent
from src.agents.relationship_event import RelationshipEvent
from src.simulation.conversation_policy import ConversationPolicy
from src.simulation.conversation_recorder import ConversationRecorder
from src.simulation.relationship_updater import RelationshipUpdater
from src.simulation.town_arc_system import TownArcSystem
from src.systems.reputation import ReputationSystem


class ConversationEffectsApplier:
    def __init__(
        self,
        actions: ActionSystem,
        relationship_updater: RelationshipUpdater,
        town_arc_system: TownArcSystem,
        conversation_recorder: ConversationRecorder,
        conversation_policy: ConversationPolicy,
        reputation_system: ReputationSystem | None = None,
    ):
        self.actions = actions
        self.relationship_updater = relationship_updater
        self.town_arc_system = town_arc_system
        self.conversation_recorder = conversation_recorder
        self.conversation_policy = conversation_policy
        self.reputation_system = reputation_system or ReputationSystem(actions)

    def apply_conversation_effects(
        self,
        day: int,
        hour: int,
        location_id: str,
        speaker: Agent,
        listener: Agent,
        action: str,
        conversation: str,
        conversation_tags: list[str],
        old_relationship_label: str,
        old_score: int,
        relationship_events: list[RelationshipEvent],
        rumor_claim: dict | None = None,
        outcome: str = "completed",
        remember: bool = True,
    ) -> dict:
        responsive_actions = {"offer_help", "ask_for_help", "cooperate"}
        outcome_allows_completion = outcome in {
            "completed", "accepted", "answered", "acknowledged"
        }
        if action not in responsive_actions or outcome_allows_completion:
            self.town_arc_system.apply_conversation_to_town_arcs(
                day=day,
                location_id=location_id,
                speaker=speaker,
                listener=listener,
                action=action,
                conversation_tags=conversation_tags,
            )

        relationship_change = self.relationship_updater.calculate_relationship_change(
            action=action,
            old_relationship_label=old_relationship_label,
            old_relationship_score=old_score,
            relationship_drift=self.relationship_updater.get_relationship_change(
                relationship_label=old_relationship_label,
            ),
        )
        if action in responsive_actions and not outcome_allows_completion:
            relationship_change = 0

        new_score, relationship_label = self.relationship_updater.apply_relationship_change(
            speaker=speaker,
            listener=listener,
            relationship_change=relationship_change,
        )

        relationship_updates = (
            self.relationship_updater.apply_structured_relationship_update(
                day=day,
                hour=hour,
                speaker=speaker,
                listener=listener,
                action=action,
                outcome=outcome,
            )
        )

        relationship_event = None

        if self.relationship_updater.should_record_relationship_event(
            action=action,
            relationship_change=relationship_change,
        ):
            relationship_event = self.relationship_updater.create_relationship_event(
                day=day,
                hour=hour,
                location_id=location_id,
                speaker=speaker,
                listener=listener,
                action=action,
                relationship_change=relationship_change,
                new_score=new_score,
                relationship_label=relationship_label,
                conversation=conversation,
                tags=conversation_tags,
                outcome=outcome,
                directed_deltas={
                    name: update["delta"]
                    for name, update in relationship_updates.items()
                },
            )
            relationship_events.append(relationship_event)

        need_effects = (
            self.actions.get_need_effects(action)
            if action not in responsive_actions or outcome_allows_completion
            else {}
        )

        for need, amount in need_effects.items():
            speaker.satisfy_need(need, amount)

        direct_reputation_updates = []
        if action not in responsive_actions or outcome_allows_completion:
            direct_reputation_updates = self.reputation_system.record_direct_action(
                day=day, hour=hour, actor=speaker, observer=listener, action=action
            )
        rumor_update = None
        if action == "share_rumor":
            rumor_update = self.reputation_system.transmit_rumor(
                day=day,
                speaker=speaker,
                listener=listener,
                claim=rumor_claim,
            )

        memory = None
        if remember:
            memory = self.conversation_recorder.remember_conversation_for_agents(
                day=day, hour=hour, location_id=location_id,
                speaker=speaker, listener=listener, conversation=conversation,
                relationship_change=relationship_change, tags=conversation_tags,
            )

        self.conversation_policy.remember_dialogue(conversation)
        self.conversation_policy.remember_action(action)

        return {
            "relationship_change": relationship_change,
            "new_score": new_score,
            "relationship_label": relationship_label,
            "relationship_event": relationship_event,
            "relationship_updates": relationship_updates,
            "memory": memory,
            "reputation_updates": [
                *direct_reputation_updates,
                *([rumor_update] if rumor_update else []),
            ],
            "rumor_transmission": rumor_update,
        }
