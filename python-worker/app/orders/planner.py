"""Validated order-plan creation without broker side effects."""
from __future__ import annotations

import uuid

from app.portfolio.models import AllocationResult
from app.risk.models import RiskAssessment
from app.trade_decision.models import DecisionAction, TradeDecision
from app.trading_intent.models import TradingIntent, TradingMode

from .models import OrderPlan, OrderSide, OrderType, TimeInForce


def create_order_plan(
    intent: TradingIntent,
    decision: TradeDecision,
    allocation: AllocationResult,
    risk: RiskAssessment,
) -> OrderPlan:
    blockers: list[str] = []
    if not allocation.allowed:
        blockers.append("portfolio allocation is not allowed")
    if decision.action not in {DecisionAction.BUY, DecisionAction.BUY_SMALL}:
        blockers.append(f"decision action is {decision.action.value}")
    if risk.entry is None or risk.stop is None or risk.target is None:
        blockers.append("entry, stop, and target are required")
    if allocation.allocated_shares <= 0:
        blockers.append("positive allocated quantity required")
    if blockers:
        raise ValueError("order plan rejected: " + "; ".join(blockers))

    entry = float(risk.entry)
    stop = float(risk.stop)
    target = float(risk.target)
    if not stop < entry:
        raise ValueError("long order stop must be below entry")
    if not target > entry:
        raise ValueError("long order target must be above entry")

    return OrderPlan(
        plan_id=str(uuid.uuid4()),
        symbol=decision.symbol,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=allocation.allocated_shares,
        limit_price=entry,
        stop_price=stop,
        target_price=target,
        time_in_force=TimeInForce.DAY if intent.horizon.value == "day_trading" else TimeInForce.GTC,
        approval_required=intent.approval_required or intent.mode != TradingMode.PAPER,
        reasons=["validated decision", "validated allocation", "validated risk levels"],
    )
