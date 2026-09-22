"""Bounded, deterministic interpretation of social language.

These functions classify evidence only.  They never mutate simulation state.
"""

from __future__ import annotations

import re


TARGET_ACTIONS = {
    "help": {"ask_for_help", "offer_help", "cooperate"},
    "meet": {"cooperate", "chat"},
    "transfer": {"ask_for_help", "offer_help"},
}


def normalize(text: str) -> str:
    return " ".join(str(text).lower().replace("’", "'").split())


def proposal_target(proposal: dict | None, previous_action: str = "") -> str:
    if proposal and proposal.get("commitment_type") in TARGET_ACTIONS:
        return proposal["commitment_type"]
    return {"offer_help": "help", "ask_for_help": "help", "cooperate": "meet"}.get(
        previous_action, "none"
    )


def resolve_response(
    previous_action: str,
    reply: str,
    *,
    proposal: dict | None = None,
    parsed_action: str = "",
    social_response: dict | None = None,
) -> tuple[str, str]:
    """Return (outcome, inspectable reason) from multiple bounded signals."""
    text = normalize(reply)
    target = proposal_target(proposal, previous_action)
    semantic = social_response or {}
    semantic_type = semantic.get("type", "none")
    semantic_target = semantic.get("target", "none")
    confidence = semantic.get("confidence", "none")

    refusal = bool(re.search(
        r"\b(no(?: thanks| thank you)?|absolutely not|can't|cannot|won't|will not|rather not|"
        r"not able|don't want|do not want|must decline|have to decline)\b", text
    ))
    if refusal or semantic_type == "decline_request":
        if semantic_type == "accept_request":
            return "unresolved", "contradictory_accept_and_refusal"
        return "declined", "explicit_refusal"

    counter = semantic_type == "counteroffer" or bool(re.search(
        r"\b(?:instead|rather than|different day|another day|next week|not tomorrow|"
        r"somewhere else)\b", text
    ))
    if counter:
        return "unresolved", "counteroffer_changes_essential_terms"

    if target == "meet" and proposal:
        proposed_location = normalize(proposal.get("metadata", {}).get("location", ""))
        mentioned_other_location = re.search(r"\b(?:at|in|over to|in the) (?:the )?(market|library|town square|cafe)\b", text)
        if mentioned_other_location and proposed_location and mentioned_other_location.group(1) not in proposed_location:
            return "unresolved", "reply_changes_proposed_meeting_location"

    compatible_semantic = (
        semantic_type == "accept_request"
        and confidence in {"high", "medium"}
        and semantic_target in {target, "none"}
        and target != "none"
    )
    compatible_action = not parsed_action or parsed_action in TARGET_ACTIONS.get(target, set())

    explicit = False
    if target == "help":
        explicit = bool(re.search(
            r"\b(?:i(?: can| will|'ll)(?: definitely)? help(?: you)?(?: with that| do that)?|"
            r"count on me|i'll be there to help|let's (?:repair|fix|work on|do) it)\b", text
        ))
        explicit = explicit or bool(re.search(r"\blet's (?:repair|fix|clean|sort|paint|work on)\b.+\btogether\b", text))
    elif target == "meet":
        explicit = bool(re.search(
            r"\b(?:i(?:'ll| will) (?:meet|be there)|let's meet|see you (?:there|tomorrow)|"
            r"that (?:time and place|time|place) work(?:s)?|i'd like that|i would like that)\b", text
        ))
    elif target == "transfer":
        explicit = bool(re.search(
            r"\b(?:i(?:'ll| will) (?:make sure to )?(?:bring|give|deliver|lend)(?: you)?|"
            r"you can count on me to (?:bring|give|deliver|lend))\b", text
        ))

    # A question that merely discusses the object/task is not agreement. A
    # scheduling question after an explicit promise is a compatible detail.
    only_question = text.endswith("?") and not explicit
    generic_positive = bool(re.match(r"^(?:yes|yeah|sure|okay|ok|sounds good)\b", text))
    unrelated_turn = generic_positive and bool(re.search(
        r"\b(?:swap stories|over coffee|sales strategies|new goods|orders are|"
        r"how have you been|what brings you|heard your)\b", text
    )) and not explicit

    if previous_action == "offer_help" and re.search(
        r"\b(?:i'd appreciate that|i would appreciate that|i appreciate your help|"
        r"thanks for offering|thank you for offering|that would help|please do)\b", text
    ):
        return "accepted", "explicit_acceptance_of_help_offer"
    if previous_action == "ask_for_help" and proposal is None and not text.endswith("?") and re.search(
        r"\b(?:try|use|ask|go|look|start|check|recommend|suggest|you should|"
        r"i(?:'ll| will| can) (?:check|help|handle|bring|give|do))\b", text
    ):
        return "accepted", "direct_answer_to_noncommitment_help_request"
    if previous_action == "cooperate" and proposal is None and re.search(
        r"\blet(?:'s| us) (?:grab|start|split|divide|sort|organize|repair|handle|clean|check|work)\b", text
    ):
        return "accepted", "explicit_participation_in_proposed_shared_task"
    if unrelated_turn:
        return "unresolved", "positive_preface_but_topic_changed"
    if explicit and compatible_action:
        return "accepted", "explicit_compatible_commitment_language"
    if explicit and not compatible_action:
        return "unresolved", "explicit_words_conflict_with_parsed_action"
    metadata = (proposal or {}).get("metadata", {})
    target_terms = normalize(
        metadata.get("task", "") or metadata.get("good_id", "").replace("_", " ")
        or metadata.get("location", "")
    )
    content_terms = [word for word in re.findall(r"[a-z]+", target_terms) if len(word) > 3]
    target_mentioned = any(word in text for word in content_terms)
    semantic_text_support = target_mentioned and bool(re.search(
        r"\b(?:agreed|i agree|absolutely|definitely|count on me|consider it done|i can do that)\b", text
    ))
    if compatible_semantic and compatible_action and semantic_text_support and not only_question:
        return "accepted", "structured_agreement_with_compatible_action"
    if semantic_type == "accept_request" and not compatible_semantic:
        return "unresolved", "structured_agreement_is_low_confidence_or_wrong_target"
    if generic_positive:
        return "unresolved", "generic_positive_without_commitment_language"
    return "unresolved", "no_clear_agreement_or_refusal"


ACTION_PATTERNS = {
    "offer_help": r"\b(?:i can help|i'll help|let me help|want me to|i can handle)\b",
    "ask_for_help": r"\b(?:can you help|could you help|would you help|i need your help|lend me a hand)\b",
    "cooperate": r"\b(?:team up|work together|collaborat|join forces|let's .+ together|we could .+ together)\b",
    "compliment": r"\b(?:great|excellent|wonderful|impressive|admire|well done|good job|beautiful|talented)\b",
    "apologize": r"\b(?:sorry|apologi[sz]e|my fault|forgive me)\b",
    "chat": r".+",
}


def semantic_action_compatibility(action: str, dialogue: str, social_response: dict | None = None) -> tuple[bool, str]:
    """Judge whether the declared action expresses its bounded social act."""
    action = str(action)
    text = normalize(dialogue)
    if action in {"argue", "insult", "storm_off", "confess_feelings", "share_rumor"}:
        return True, "legacy_action_not_scored_by_literal_label"
    pattern = ACTION_PATTERNS.get(action)
    if pattern and re.search(pattern, text):
        return True, "dialogue_expresses_action_semantics"
    semantic_type = (social_response or {}).get("type", "none")
    if action in {"offer_help", "cooperate"} and semantic_type in {"accept_request", "counteroffer"}:
        return True, "structured_social_act_is_action_compatible"
    return False, "dialogue_does_not_express_declared_action"


def classify_commitment_relation(
    commitment: dict,
    dialogue: str,
    annotation: dict | None = None,
    grounding_refs: list[str] | None = None,
) -> dict:
    """Classify a claim relative to authoritative state without changing it."""
    text = normalize(dialogue)
    status = commitment.get("status", "")
    commitment_id = commitment.get("id", "")
    annotation = annotation or {}
    annotated = annotation.get("relation", "none") if annotation.get("commitment_id") in {"", commitment_id} else "none"
    metadata = commitment.get("metadata", {})
    grounding_text = normalize(
        metadata.get("task", "") or metadata.get("good_id", "").replace("_", " ")
        or metadata.get("location", "")
    )
    grounding_terms = [word for word in re.findall(r"[a-z]+", grounding_text) if len(word) > 3]
    refers_to_object = any(word.rstrip("s") in text for word in grounding_terms)
    future = bool(re.search(r"\b(?:i'll|i will|going to|plan to|still need to|today|tomorrow)\b", text))
    completed = bool(re.search(
        r"\b(?:already|i have|i've|we have|we've|last)\b.{0,35}\b(?:brought|given|delivered|helped|repaired|fixed|met|meeting)\b|"
        r"\b(?:the material|the book) i (?:brought|delivered)\b", text
    ))
    failure = bool(re.search(r"\b(?:couldn't|could not|failed|missed|didn't|did not|sorry)\b", text))
    repair = failure and bool(re.search(r"\b(?:try again|make it up|can try|i'll try|i will try|reschedule)\b", text))

    # The ID is only available when the record was supplied in this pair-private
    # prompt.  Treat an exact ID plus a bounded relation as grounded even when
    # the utterance naturally uses a pronoun ("I still need to bring it").
    annotated_grounded = (
        annotation.get("commitment_id") == commitment_id
        and annotated != "none"
    ) or (annotated != "none" and refers_to_object)
    if repair or (annotated == "attempts_repair" and annotated_grounded):
        relation = "attempts_repair"
    elif failure or (annotated == "acknowledges_failure" and annotated_grounded):
        relation = "acknowledges_failure"
    elif completed or (annotated in {"fulfilling", "references_fulfillment"} and annotated_grounded):
        relation = "references_fulfillment"
    elif (future and (refers_to_object or not grounding_terms)) or (annotated == "planning_to_fulfill" and annotated_grounded):
        relation = "planning_to_fulfill"
    else:
        relation = "unrelated"

    contradiction = False
    reason = "consistent_with_authoritative_state"
    if relation == "references_fulfillment" and status in {"accepted", "expired", "failed", "cancelled"}:
        contradiction = True
        reason = "claims_fulfillment_without_authoritative_fulfillment"
    elif relation in {"planning_to_fulfill", "fulfilling"} and status in {"fulfilled", "cancelled"}:
        contradiction = True
        reason = "plans_terminal_commitment_as_if_active"
    elif relation == "acknowledges_failure" and status == "fulfilled":
        contradiction = True
        reason = "claims_failure_of_fulfilled_commitment"
    return {
        "commitment_id": commitment_id,
        "relation": relation,
        "classification": "contradiction" if contradiction else "state_consistent",
        "reason": reason,
        "grounding_refs": list(grounding_refs or []),
    }


def classify_explicit_cancellation(commitment: dict, dialogue: str) -> dict:
    """Recognize only explicit inability/refusal tied to supplied commitment terms."""
    text = normalize(dialogue)
    metadata = commitment.get("metadata", {})
    terms = normalize(
        metadata.get("task", "") or metadata.get("good_id", "").replace("_", " ")
        or metadata.get("location", "")
    )
    content = [word.rstrip("s") for word in re.findall(r"[a-z]+", terms) if len(word) > 3]
    refers = any(word in text for word in content)
    if commitment.get("commitment_type") == "meet":
        refers = refers or bool(re.search(r"\b(?:meet|meeting|make it|be there)\b", text))
    elif commitment.get("commitment_type") == "transfer":
        refers = refers or bool(re.search(r"\b(?:bring|give|deliver|lend)\b", text))
    elif commitment.get("commitment_type") == "help":
        refers = refers or bool(re.search(r"\b(?:help|assist)\b", text))
    inability = (
        r"(?:can't|cannot|won't|will not|am not able to|am unable to|"
        r"won't be able to|will not be able to)"
    )
    commitment_verb = r"(?:bring|give|deliver|lend|meet|make|attend|help|assist|repair|fix)"
    explicit = bool(re.search(
        rf"\bi (?:{inability})\s+(?:continue (?:with )?|still )?{commitment_verb}\b",
        text,
    ))
    vague = text in {"i'm busy.", "i am busy.", "maybe later.", "that sounds difficult.",
                     "i don't know.", "i do not know."}
    cancel = bool(explicit and refers and not vague)
    return {"cancel": cancel,
            "reason": "explicit_inability_for_commitment" if cancel
            else "no_explicit_grounded_cancellation",
            "refers_to_commitment": refers, "explicit_inability": explicit}
