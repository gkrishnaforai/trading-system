"""Deterministic staged accumulation planning."""
from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from app.risk.models import RiskAssessment
from app.trade_decision.models import TradeDecision

if TYPE_CHECKING:
    from app.swing_opportunity.models import SwingOpportunity

from .models import AccumulationPhase, AccumulationPlan


def build_accumulation_plan(
    opportunity: SwingOpportunity,
    decision: TradeDecision,
    risk: RiskAssessment,
    *,
    current_position: float = 0.0,
    current_weight: Optional[float] = None,
    target_weight: Optional[float] = None,
) -> AccumulationPlan:
    fundamentals = opportunity.fundamentals or {}
    momentum = fundamentals.get("momentum", {}) if isinstance(fundamentals, dict) else {}
    momentum_label = str(momentum.get("label", "UNKNOWN")).upper()
    thesis = opportunity.thesis_status
    market_multiplier = opportunity.swing_size_multiplier
    blockers = []
    reasons = []

    # Hard gates are evaluated before any phase assignment.
    if thesis == "BROKEN":
        blockers.append("thesis is broken")
    if momentum_label == "DETERIORATING":
        blockers.append("fundamental momentum is deteriorating")
    if opportunity.setup.falling_knife:
        blockers.append("falling-knife setup")
    if not opportunity.event_new_entries_allowed:
        blockers.append(f"event policy blocks new entries ({opportunity.event_policy})")
    if not risk.allowed:
        blockers.extend(risk.blocking_reasons or ["risk engine did not approve the setup"])
    if market_multiplier <= 0:
        blockers.append("market size multiplier is zero")

    next_confirmation = []
    if opportunity.setup_readiness != "CONFIRMED":
        next_confirmation.extend(["higher low", "EMA20 reclaim", "positive volume"])
    if momentum_label == "UNKNOWN":
        next_confirmation.append("fundamental estimate history")
    if not fundamentals.get("valuation", {}).get("valuation_label") or fundamentals.get("valuation", {}).get("valuation_label") == "unavailable":
        next_confirmation.append("valuation coverage")

    invalidation = ["thesis becomes BROKEN", "falling-knife condition", "risk or reconciliation failure"]
    if blockers:
        return AccumulationPlan(
            symbol=opportunity.symbol, current_position=current_position,
            current_weight=current_weight, target_weight=target_weight,
            market_size_multiplier=market_multiplier, thesis_status=thesis,
            fundamental_momentum=momentum_label, entry_state=opportunity.entry_state,
            phase=AccumulationPhase.BLOCKED, eligible=False,
            blockers=list(dict.fromkeys(blockers)), next_confirmation=list(dict.fromkeys(next_confirmation)),
            invalidation_conditions=invalidation,
            reasons=["accumulation is blocked by a hard gate"],
        )

    readiness = opportunity.setup_readiness
    if readiness != "CONFIRMED":
        phase = AccumulationPhase.WATCH if readiness == "NOT_READY" else AccumulationPhase.DEVELOPING
        reasons.append("wait for confirmed setup before accumulating")
        eligible = False
    elif current_position <= 0:
        phase = AccumulationPhase.STARTER if market_multiplier < 0.75 else AccumulationPhase.CONFIRMED
        reasons.append("confirmed setup and risk approval support staged accumulation")
        eligible = True
    else:
        phase = AccumulationPhase.CONFIRMED
        reasons.append("existing position has a confirmed accumulation setup")
        eligible = True

    planned_target = target_weight
    if planned_target is not None and phase == AccumulationPhase.STARTER:
        planned_target *= 0.25
    elif planned_target is not None and phase == AccumulationPhase.DEVELOPING:
        planned_target *= 0.50
    remaining = None
    if planned_target is not None and current_weight is not None:
        remaining = max(0.0, planned_target - current_weight)

    return AccumulationPlan(
        symbol=opportunity.symbol, eligible=eligible, phase=phase,
        current_position=current_position, target_position=None,
        remaining_position=remaining, current_weight=current_weight,
        target_weight=planned_target, market_size_multiplier=market_multiplier,
        thesis_status=thesis, fundamental_momentum=momentum_label,
        entry_state=opportunity.entry_state,
        next_confirmation=list(dict.fromkeys(next_confirmation)),
        invalidation_conditions=invalidation, blockers=[], reasons=reasons,
    )
