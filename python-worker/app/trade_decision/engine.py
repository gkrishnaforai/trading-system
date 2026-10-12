"""Deterministic final trade-decision policy."""
from __future__ import annotations

from typing import List, TYPE_CHECKING

from app.risk.models import RiskAssessment, RiskStatus

if TYPE_CHECKING:
    from app.swing_opportunity.models import SwingOpportunity

from .models import DecisionAction, TradeDecision


# Setups that mean "watch, not enter" — trend_continuation is literally
# "trend intact but setup incomplete"; it must not produce BUY actions.
_NON_ENTRY_SETUPS = {"no_setup", "trend_continuation"}


def decide_trade(opportunity: SwingOpportunity, risk: RiskAssessment) -> TradeDecision:
    """Convert validated opportunity/risk state into one bounded action."""
    reasons: List[str] = []
    vetoes: List[str] = []
    fundamentals = opportunity.fundamentals
    fundamental_quality = "unavailable"
    valuation_label = "unavailable"
    growth_value_class = "UNCLASSIFIED"
    if fundamentals:
        quality_score = fundamentals.get("quality_score")
        if quality_score is not None:
            fundamental_quality = (
                "exceptional" if quality_score >= 85 else
                "high" if quality_score >= 70 else
                "medium" if quality_score >= 50 else "low")
        valuation_label = fundamentals.get("valuation", {}).get("valuation_label", "unavailable")
        growth_value_class = fundamentals.get("growth_value_class") or "UNCLASSIFIED"
        if fundamentals.get("data_quality") in {"insufficient", "partial"}:
            reasons.append("fundamental coverage is incomplete")

    if opportunity.stock.data_quality.sufficient is False:
        vetoes.append("technical data is insufficient")
    if opportunity.setup.falling_knife:
        vetoes.append("falling-knife setup")
    if opportunity.setup.type.value in _NON_ENTRY_SETUPS:
        vetoes.append(f"{opportunity.setup.type.value} is not an entry setup")
    if risk.status == RiskStatus.INSUFFICIENT_DATA:
        vetoes.extend(risk.blocking_reasons)
    elif not risk.allowed:
        vetoes.extend(risk.blocking_reasons)

    # Hard safety decisions precede positive scoring.
    if opportunity.setup.falling_knife:
        action = DecisionAction.AVOID
    elif not opportunity.stock.data_quality.sufficient or risk.status == RiskStatus.INSUFFICIENT_DATA:
        action = DecisionAction.WAIT
    elif opportunity.setup.type.value in _NON_ENTRY_SETUPS:
        action = DecisionAction.WAIT
    elif not risk.allowed:
        action = DecisionAction.WAIT
    elif opportunity.opportunity_quality.value == "high":
        # Incomplete fundamentals permit only a reduced recommendation.
        action = DecisionAction.BUY_SMALL if fundamentals.get("data_quality") != "good" else DecisionAction.BUY
    elif opportunity.opportunity_quality.value == "medium":
        action = DecisionAction.BUY_SMALL
    else:
        action = DecisionAction.WAIT

    # Valuation modulation — fair value never creates or vetoes entries (setup
    # and regime own those), but it modulates conviction on buy actions.
    if action in {DecisionAction.BUY, DecisionAction.BUY_SMALL}:
        valuation = fundamentals.get("valuation") or {}
        price = valuation.get("current_price")
        bull_fv = valuation.get("fair_value_bull")
        if growth_value_class == "VALUE_TRAP":
            if action == DecisionAction.BUY:
                action = DecisionAction.BUY_SMALL
            reasons.append(
                "valuation classification VALUE_TRAP — cheap but weak quality; reduced size")
        elif bull_fv and price and float(price) > float(bull_fv):
            if action == DecisionAction.BUY:
                action = DecisionAction.BUY_SMALL
            pct = (float(price) / float(bull_fv) - 1) * 100
            reasons.append(
                f"price {pct:.0f}% above bull-case fair value — reduced size")
        if growth_value_class in {"SPECULATIVE_GROWTH", "EXPENSIVE_GROWTH"}:
            reasons.append(
                f"valuation classification {growth_value_class} — review before sizing")
        if valuation.get("fair_value_source") == "user_override":
            reasons.append("fair value is a user override — verify before acting")

    reasons.extend(opportunity.reasons)
    if risk.allowed:
        reasons.append("risk constraints passed")
    else:
        reasons.extend(risk.blocking_reasons)

    confidence = 0.0
    if action in {DecisionAction.BUY, DecisionAction.BUY_SMALL}:
        confidence = min(0.9, max(0.5, opportunity.opportunity_score / 100))
        if fundamentals.get("data_quality") != "good":
            confidence = min(confidence, 0.65)
        if growth_value_class in {"SPECULATIVE_GROWTH", "EXPENSIVE_GROWTH", "VALUE_TRAP"}:
            confidence = min(confidence, 0.65)
    elif action == DecisionAction.AVOID:
        confidence = 0.9 if opportunity.setup.falling_knife else 0.7
    else:
        confidence = 0.75 if vetoes else 0.45

    return TradeDecision(
        symbol=opportunity.symbol,
        action=action,
        entry_action=action,
        confidence=confidence,
        reasons=list(dict.fromkeys(reasons)),
        vetoes=list(dict.fromkeys(vetoes)),
        requires_approval=action in {DecisionAction.BUY, DecisionAction.BUY_SMALL},
        opportunity_quality=opportunity.opportunity_quality.value,
        fundamental_quality=fundamental_quality,
        thesis_status=opportunity.thesis_status,
        setup_readiness=opportunity.setup_readiness,
        entry_state=opportunity.entry_state,
        valuation_label=valuation_label,
        growth_value_class=growth_value_class,
        risk_status=risk.status.value,
        position_size_pct=risk.position_size_pct if risk.allowed else 0.0,
        provenance={"rules_version": "trade-decision-v1", "source": "deterministic"},
    )
