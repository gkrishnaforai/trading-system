"""Deterministic position-management policy separate from entry decisions."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from app.risk.models import RiskAssessment
from app.trade_decision.models import TradeDecision

from .models import PositionAction, PositionManagementAssessment

if TYPE_CHECKING:
    from app.swing_opportunity.models import SwingOpportunity


def manage_position(
    opportunity: SwingOpportunity,
    decision: TradeDecision,
    risk: RiskAssessment,
    *,
    current_position: float = 0.0,
    current_weight: Optional[float] = None,
    target_weight: Optional[float] = None,
    reconciliation_safe: bool = True,
) -> PositionManagementAssessment:
    thesis = opportunity.thesis_status
    position_state = "HEALTHY" if current_position > 0 else "NO_POSITION"
    if current_position <= 0:
        return PositionManagementAssessment(
            symbol=opportunity.symbol, position_action=PositionAction.REVIEW,
            thesis_status=thesis, position_state=position_state,
            current_position=current_position, current_weight=current_weight,
            target_weight=target_weight, risk_approval=risk.allowed,
            reason_code="NO_EXISTING_POSITION",
            reasons=["no existing position was supplied for position management"],
        )
    if not reconciliation_safe:
        return PositionManagementAssessment(
            symbol=opportunity.symbol, position_action=PositionAction.REVIEW,
            thesis_status=thesis, position_state="RECONCILIATION_UNSAFE",
            current_position=current_position, current_weight=current_weight,
            target_weight=target_weight, risk_approval=risk.allowed,
            reason_code="RECONCILIATION_UNSAFE",
            reasons=["position/account reconciliation is unresolved"],
        )
    if thesis == "BROKEN":
        return PositionManagementAssessment(
            symbol=opportunity.symbol, position_action=PositionAction.EXIT,
            thesis_status=thesis, position_state="THESIS_BROKEN",
            current_position=current_position, current_weight=current_weight,
            target_position=0, reduce_quantity=current_position,
            risk_approval=risk.allowed, reason_code="THESIS_BROKEN",
            reasons=["fundamental thesis is broken; technical strength cannot rescue it"],
        )
    if opportunity.setup.falling_knife:
        return PositionManagementAssessment(
            symbol=opportunity.symbol, position_action=PositionAction.TRIM,
            thesis_status=thesis, position_state="DETERIORATING",
            current_position=current_position, current_weight=current_weight,
            target_weight=target_weight, reduce_quantity=max(1.0, current_position * .5),
            risk_approval=risk.allowed, reason_code="FALLING_KNIFE",
            reasons=["falling-knife condition requires reducing existing exposure"],
        )
    if risk.target is not None and opportunity.stock.technicals.price is not None and opportunity.stock.technicals.price >= risk.target:
        reduction = max(1.0, current_position * .25)
        return PositionManagementAssessment(
            symbol=opportunity.symbol, position_action=PositionAction.TAKE_PROFIT,
            thesis_status=thesis, position_state="EXTENDED",
            current_position=current_position, current_weight=current_weight,
            target_weight=target_weight, reduce_quantity=reduction,
            risk_approval=risk.allowed, reason_code="TARGET_REACHED",
            reasons=["planned target reached while thesis remains intact"],
        )
    if current_weight is not None and target_weight is not None and current_weight > target_weight:
        reduction_weight = current_weight - target_weight
        reduction_qty = max(1.0, current_position * reduction_weight / current_weight)
        return PositionManagementAssessment(
            symbol=opportunity.symbol, position_action=PositionAction.TRIM,
            thesis_status=thesis, position_state="OVERSIZED",
            current_position=current_position, current_weight=current_weight,
            target_position=max(0.0, current_position - reduction_qty),
            target_weight=target_weight, reduce_quantity=reduction_qty,
            risk_approval=risk.allowed, reason_code="OVERWEIGHT",
            reasons=["position exceeds target portfolio weight"],
        )
    return PositionManagementAssessment(
        symbol=opportunity.symbol, position_action=PositionAction.HOLD,
        thesis_status=thesis, position_state="HEALTHY",
        current_position=current_position, current_weight=current_weight,
        target_weight=target_weight, risk_approval=risk.allowed,
        reason_code="THESIS_INTACT_POSITION_HEALTHY",
        reasons=["thesis remains intact and position is not known to be oversized"],
    )
