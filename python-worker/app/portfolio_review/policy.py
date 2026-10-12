"""Manual portfolio-action lifecycle policy; no execution authority."""
from __future__ import annotations

from typing import Optional

from app.portfolio.contracts import PositionState
from app.risk.models import RiskAssessment
from app.swing_opportunity.models import SwingOpportunity
from app.trade_decision.models import DecisionAction, TradeDecision
from app.position_management import manage_position

from .models import PortfolioAction, PositionReview


def assign_position_action(
    opportunity: SwingOpportunity,
    decision: TradeDecision,
    risk: RiskAssessment,
    *,
    quantity: float,
    current_price: float | None,
    position: Optional[PositionState] = None,
    reconciliation_safe: bool = True,
    account_equity: float | None = None,
) -> PositionReview:
    """Assign an analysis action for an existing position.

    Precedence is intentionally fail-closed: reconciliation/data safety comes
    before thesis, risk, catalyst, profit, or technical policy.
    """
    reasons = list(decision.reasons)
    fundamentals = opportunity.fundamentals or {}
    momentum = fundamentals.get("momentum", {}) if isinstance(fundamentals, dict) else {}
    business_quality = opportunity.business_quality
    thesis_status = opportunity.thesis_status
    valuation_state = fundamentals.get("valuation", {}).get("valuation_label", "UNKNOWN")
    position_state = "HEALTHY" if quantity > 0 else "NO_POSITION"
    current_value = quantity * current_price if current_price is not None else None
    current_weight = current_value / account_equity if current_value is not None and account_equity else None
    base = dict(
        symbol=opportunity.symbol,
        quantity=quantity,
        current_price=current_price,
        setup_type=opportunity.setup.type.value,
        opportunity_quality=opportunity.opportunity_quality.value,
        fundamental_quality=decision.fundamental_quality,
        event_policy=opportunity.event_policy,
        risk_status=risk.status.value,
        thesis_status=thesis_status,
        business_quality=business_quality,
        fundamental_momentum=momentum.get("label", "UNKNOWN"),
        valuation_state=valuation_state,
        entry_state=decision.entry_state,
        current_position=quantity,
        current_weight=current_weight,
        risk_approval=risk.allowed,
    )

    if quantity > 0:
        if not reconciliation_safe or current_price is None:
            return PositionReview(
                **base,
                action=PortfolioAction.REVIEW,
                confidence=0.95,
                position_state="RECONCILIATION_UNSAFE",
                action_reason="portfolio data or reconciliation is not safe for position action",
                reasons=["position/account reconciliation is unresolved; no trim/exit action issued"],
                data_quality="insufficient",
            )
        management = manage_position(
            opportunity, decision, risk,
            current_position=quantity,
            current_weight=current_weight,
            target_weight=None,
            reconciliation_safe=reconciliation_safe,
        )
        if management.position_action.value == "HOLD" and decision.action in {DecisionAction.BUY, DecisionAction.BUY_SMALL}:
            return PositionReview(
                **base,
                action=PortfolioAction.ADD,
                confidence=decision.confidence,
                position_state=management.position_state,
                action_reason="confirmed entry setup supports adding to existing position",
                reasons=list(dict.fromkeys(reasons + management.reasons)),
                data_quality="good",
            )
        return PositionReview(
            **base,
            action=PortfolioAction(management.position_action.value),
            confidence=0.9 if management.position_action in {"EXIT", "TRIM", "TAKE_PROFIT"} else decision.confidence,
            position_state=management.position_state,
            action_reason=management.reason_code,
            trim_reason=management.reason_code if management.position_action.value == "TRIM" else None,
            take_profit_reason=management.reason_code if management.position_action.value == "TAKE_PROFIT" else None,
            exit_reason=management.reason_code if management.position_action.value == "EXIT" else None,
            reduce_quantity=management.reduce_quantity,
            target_position=management.target_position,
            reasons=list(dict.fromkeys(reasons + management.reasons)),
            data_quality="good" if reconciliation_safe and current_price is not None else "insufficient",
        )

    # 1. Data/reconciliation safety is the first hard gate.
    if not reconciliation_safe or current_price is None:
        return PositionReview(
            **base,
            action=PortfolioAction.REVIEW,
            confidence=0.95,
            position_state="RECONCILIATION_UNSAFE",
            action_reason="portfolio data or reconciliation is not safe for position action",
            reasons=["position/account reconciliation is unresolved; no trim/exit action issued"],
            data_quality="insufficient",
        )

    # 2. A broken thesis exits regardless of technical appearance.
    if thesis_status == "BROKEN":
        reasons.append("thesis is broken")
        return PositionReview(
            **base, action=PortfolioAction.EXIT, confidence=0.95,
            exit_reason="THESIS_BROKEN", action_reason="fundamental thesis invalidated",
            target_position=0, reduce_quantity=quantity, reasons=list(dict.fromkeys(reasons)),
        )

    # 3. Falling knife reduces existing exposure; it does not create an order.
    if opportunity.setup.falling_knife:
        reasons.append("falling-knife condition requires reducing existing exposure")
        return PositionReview(
            **base, action=PortfolioAction.TRIM, confidence=0.9,
            trim_reason="FALLING_KNIFE", action_reason="technical deterioration",
            reduce_quantity=max(1.0, quantity * 0.5),
            reasons=list(dict.fromkeys(reasons)),
        )

    # 4. Target/extension profit handling comes before ordinary HOLD.
    if risk.target is not None and current_price >= risk.target and thesis_status != "BROKEN":
        reasons.append("planned target reached while thesis remains intact")
        return PositionReview(
            **base, action=PortfolioAction.TAKE_PROFIT, confidence=0.85,
            take_profit_reason="TARGET_REACHED", action_reason="realize partial profit and retain thesis exposure",
            reduce_quantity=max(1.0, quantity * 0.25),
            target_position=max(0.0, quantity - max(1.0, quantity * 0.25)),
            reasons=list(dict.fromkeys(reasons)),
        )

    # 5. New-entry analysis is not automatically an existing-position action.
    if decision.action in {DecisionAction.BUY, DecisionAction.BUY_SMALL}:
        if risk.allowed and opportunity.event_new_entries_allowed:
            action = PortfolioAction.ADD
            confidence = decision.confidence
            reason = "confirmed setup and risk approval support adding exposure"
        else:
            action = PortfolioAction.HOLD
            confidence = 0.75
            reason = "new add is not approved; existing thesis remains held"
            reasons.append("new exposure is not approved")
    elif decision.action == DecisionAction.AVOID:
        action = PortfolioAction.HOLD
        confidence = decision.confidence
        reason = "avoid new exposure; no exit trigger established"
    elif decision.action == DecisionAction.WAIT:
        action = PortfolioAction.HOLD
        confidence = decision.confidence
        reason = "thesis remains valid but entry setup is not ready"
    else:
        action = PortfolioAction.REVIEW
        confidence = 0.5
        reason = "decision state requires review"

    return PositionReview(
        **base,
        action=action,
        confidence=confidence,
        action_reason=reason,
        reasons=list(dict.fromkeys(reasons)),
    )
