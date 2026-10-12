"""Deterministic portfolio allocation policy."""
from __future__ import annotations

from app.risk.models import RiskAssessment
from app.trade_decision.models import DecisionAction, TradeDecision
from app.trading_intent.models import TradingIntent

from .models import AllocationResult, AllocationStatus, PortfolioSnapshot


def allocate_portfolio(
    intent: TradingIntent,
    portfolio: PortfolioSnapshot,
    decision: TradeDecision,
    risk: RiskAssessment,
    *,
    price: float,
    sector: str | None = None,
) -> AllocationResult:
    """Allocate capital after decision and risk validation; never creates a trade."""
    blockers: list[str] = []
    reasons: list[str] = []
    remaining_heat = max(0.0, intent.max_portfolio_heat - portfolio.portfolio_heat)

    if intent.horizon.value == "day_trading":
        blockers.append("day-trading allocator requires intraday strategy contract")
    if intent.mode.value == "live":
        blockers.append("live mode requires live execution approval")
    if decision.action not in {DecisionAction.BUY, DecisionAction.BUY_SMALL}:
        blockers.append(f"decision action is {decision.action.value}")
    if not risk.allowed:
        blockers.extend(risk.blocking_reasons or ["risk assessment did not allow trade"])
    if portfolio.open_positions >= intent.max_open_positions:
        blockers.append("maximum open positions reached")
    if price <= 0:
        blockers.append("positive price required")

    risk_budget = min(
        intent.account_equity * intent.max_risk_per_trade,
        intent.account_equity * remaining_heat,
    )
    requested_value = min(
        intent.account_equity * intent.max_position_pct,
        portfolio.cash,
    )
    if decision.action == DecisionAction.BUY_SMALL:
        requested_value *= 0.5
    market_multiplier = risk.position_size_pct / intent.max_position_pct if intent.max_position_pct else 0
    requested_value *= max(0.0, min(1.0, market_multiplier))

    if blockers:
        return AllocationResult(
            symbol=decision.symbol,
            status=AllocationStatus.BLOCKED,
            allowed=False,
            requested_value=max(0.0, requested_value),
            risk_budget=risk_budget,
            remaining_heat=remaining_heat,
            reasons=reasons,
            blocking_reasons=list(dict.fromkeys(blockers)),
            provenance={"rules_version": "portfolio-allocation-v1", "source": "deterministic"},
        )

    allocated_shares = int(requested_value / price)
    allocated_value = allocated_shares * price
    if allocated_shares <= 0:
        blockers.append("allocation rounds to zero shares")
    if allocated_value > portfolio.cash + 1e-9:
        blockers.append("allocation exceeds available cash")
    if blockers:
        return AllocationResult(
            symbol=decision.symbol,
            status=AllocationStatus.BLOCKED,
            allowed=False,
            requested_value=requested_value,
            risk_budget=risk_budget,
            remaining_heat=remaining_heat,
            blocking_reasons=blockers,
            provenance={"rules_version": "portfolio-allocation-v1", "source": "deterministic"},
        )

    status = AllocationStatus.REDUCED if decision.action == DecisionAction.BUY_SMALL else AllocationStatus.APPROVED
    return AllocationResult(
        symbol=decision.symbol,
        status=status,
        allowed=True,
        requested_value=requested_value,
        allocated_value=allocated_value,
        allocated_shares=allocated_shares,
        allocation_pct=allocated_value / intent.account_equity,
        risk_budget=risk_budget,
        remaining_heat=remaining_heat,
        reasons=["decision and risk gates passed", "cash and position limits applied"],
        provenance={"rules_version": "portfolio-allocation-v1", "source": "deterministic"},
    )
