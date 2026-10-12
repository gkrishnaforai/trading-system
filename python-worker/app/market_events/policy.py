"""Deterministic event overlays for horizon-specific environments."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.strategy_environment.models import StrategyEnvironment

from .models import (
    EventReaction, EventSeverity, EventAwareStrategyEnvironment,
    MarketEvent, ReactionState,
)


def apply_event_policy(
    environment: StrategyEnvironment,
    event: MarketEvent | None = None,
    reaction: EventReaction | None = None,
) -> EventAwareStrategyEnvironment:
    """Apply event restrictions without changing the base strategy rules."""
    reaction_state = reaction.state if reaction else ReactionState.NOT_AVAILABLE
    reasons = list(environment.reasons)
    severity = event.severity if event else EventSeverity.NONE
    policy = "NORMAL"
    new_entries = environment.long_permission != "disabled"
    size = environment.size_multiplier
    long_permission = environment.long_permission
    breakout = environment.breakout_permission
    pullback = environment.pullback_permission
    quality = environment.quality.value
    score = environment.score

    if event and severity in {EventSeverity.HIGH, EventSeverity.EXTREME}:
        policy = "PRE_EVENT_RESTRICTED" if event.status.value == "SCHEDULED" else "POST_EVENT_RESTRICTED"
        size *= 0.5 if severity == EventSeverity.EXTREME else 0.7
        new_entries = False if severity == EventSeverity.EXTREME else new_entries
        long_permission = "restricted" if long_permission == "allowed" else long_permission
        breakout = "avoid"
        reasons.append(f"{severity.value.lower()} {event.event_type.value} event policy")
        if event.policy_bias.value != "UNKNOWN":
            reasons.append(f"policy bias is {event.policy_bias.value.lower()}")

    if reaction:
        if reaction.state == ReactionState.RISK_OFF and reaction.confirmation:
            policy = "REACTION_RISK_OFF"
            size *= 0.5
            new_entries = False
            long_permission = "restricted"
            breakout = "avoid"
            score = min(score, 45.0)
            reasons.append("confirmed risk-off market reaction")
        elif reaction.state == ReactionState.RISK_ON and reaction.confirmation:
            policy = "REACTION_RISK_ON_CONFIRMED"
            # The confirmed post-event reaction can restore the base policy,
            # but never boost it beyond the pre-event environment.
            size = environment.size_multiplier
            new_entries = environment.long_permission != "disabled"
            long_permission = environment.long_permission
            breakout = environment.breakout_permission
            pullback = environment.pullback_permission
            score = environment.score
            reasons.append("risk-on reaction confirmed; base permissions restored")
        elif reaction.state in {ReactionState.MIXED, ReactionState.INCONCLUSIVE}:
            policy = "REACTION_UNCONFIRMED"
            new_entries = False
            size *= 0.5
            reasons.append("event reaction is not confirmed")

    return EventAwareStrategyEnvironment(
        horizon=environment.horizon.value,
        base_quality=environment.quality.value,
        quality=quality,
        score=round(max(0.0, min(100.0, score)), 1),
        confidence=environment.confidence,
        long_permission=long_permission,
        short_permission=environment.short_permission,
        breakout_permission=breakout,
        pullback_permission=pullback,
        size_multiplier=round(max(0.0, min(1.0, size)), 2),
        pacing="wait" if not new_entries else environment.pacing,
        event_severity=severity,
        event_policy=policy,
        reaction_state=reaction_state,
        new_entries_allowed=new_entries,
        data_sufficient=environment.data_sufficient,
        reasons=list(dict.fromkeys(reasons)),
        provenance={"rules_version": "event-policy-v1", "source": "deterministic"},
    )
