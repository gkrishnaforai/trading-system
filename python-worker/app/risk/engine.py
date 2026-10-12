"""Pure deterministic risk rules for a swing opportunity."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from app.market_regime.models import MarketRegime

if TYPE_CHECKING:
    from app.swing_opportunity.models import SwingOpportunity

from .models import PortfolioConstraints, RiskAssessment, RiskStatus


def assess_risk(
    opportunity: SwingOpportunity,
    regime: MarketRegime,
    constraints: PortfolioConstraints,
    *,
    entry: Optional[float] = None,
    stop: Optional[float] = None,
    target: Optional[float] = None,
    event_blocked: bool = False,
) -> RiskAssessment:
    """Validate a setup and calculate bounded fixed-fractional risk.

    This function does not create a setup and does not emit a trade action.
    """
    reasons = []
    blockers = []
    technicals = opportunity.stock.technicals
    entry = entry if entry is not None else technicals.price

    if opportunity.setup.type.value == "no_setup":
        blockers.append("no qualifying setup")
    if opportunity.setup.falling_knife:
        blockers.append("falling-knife setup rejected")
    if opportunity.opportunity_quality.value in {"unavailable", "low"}:
        blockers.append(f"opportunity quality is {opportunity.opportunity_quality.value}")
    if opportunity.swing_size_multiplier <= 0:
        blockers.append("market size multiplier is zero")
    if not opportunity.event_new_entries_allowed:
        blockers.append(f"event policy blocks new entries ({opportunity.event_policy})")
    if event_blocked:
        blockers.append("event policy blocks new entries")
    if regime.market_permissions and not regime.market_permissions.normal_long:
        if regime.market_permissions.selective_long:
            reasons.append("selective long policy: stock setup must be confirmed")
        else:
            blockers.append("market permissions do not allow long entries")

    if entry is None or entry <= 0:
        blockers.append("positive entry price unavailable")
    atr_pct = technicals.atr_pct
    if stop is None and entry and atr_pct and atr_pct > 0:
        stop = entry * (1 - 2.0 * atr_pct)
    if target is None and entry and stop and entry > stop:
        target = entry + 2.0 * (entry - stop)

    if stop is None or stop <= 0 or entry is None or stop >= entry:
        blockers.append("valid long stop is unavailable")
    if target is None or entry is None or target <= entry:
        blockers.append("valid target is unavailable")

    risk_per_share = (entry - stop) if entry is not None and stop is not None else None
    reward_risk = (
        (target - entry) / risk_per_share
        if target is not None and entry is not None and risk_per_share and risk_per_share > 0
        else None
    )
    if reward_risk is not None and reward_risk < 2.0:
        blockers.append(f"reward/risk below 2.0 ({reward_risk:.2f})")

    heat_before = constraints.current_portfolio_risk
    if constraints.open_trades >= constraints.max_open_trades:
        blockers.append("maximum open-trade count reached")

    if blockers:
        return RiskAssessment(
            symbol=opportunity.symbol,
            status=RiskStatus.BLOCKED if entry else RiskStatus.INSUFFICIENT_DATA,
            allowed=False,
            entry=entry, stop=stop, target=target,
            risk_per_share=risk_per_share, reward_risk=reward_risk,
            portfolio_heat_before=heat_before,
            reasons=reasons, blocking_reasons=blockers,
            provenance={"rules_version": "risk-v1", "source": "deterministic"},
        )

    if constraints.account_equity is None or constraints.account_equity <= 0:
        return RiskAssessment(
            symbol=opportunity.symbol,
            status=RiskStatus.INSUFFICIENT_DATA,
            allowed=False,
            entry=entry, stop=stop, target=target,
            risk_per_share=risk_per_share, reward_risk=reward_risk,
            portfolio_heat_before=heat_before,
            reasons=["setup passed risk-shape checks"],
            blocking_reasons=["account equity required for position sizing"],
            provenance={"rules_version": "risk-v1", "source": "deterministic"},
        )

    risk_budget = constraints.account_equity * constraints.max_risk_per_trade
    max_heat_remaining = max(0.0, constraints.max_portfolio_risk - heat_before)
    risk_budget = min(risk_budget, constraints.account_equity * max_heat_remaining)
    raw_shares = int(risk_budget / risk_per_share) if risk_per_share else 0
    max_value = constraints.account_equity * constraints.max_position_pct * opportunity.swing_size_multiplier
    shares = min(raw_shares, int(max_value / entry)) if entry else 0
    position_value = shares * entry
    risk_amount = shares * risk_per_share
    position_pct = position_value / constraints.account_equity
    heat_after = heat_before + risk_amount / constraints.account_equity

    if shares <= 0:
        blockers.append("position size rounds to zero")
    if heat_after > constraints.max_portfolio_risk + 1e-9:
        blockers.append("portfolio heat limit exceeded")

    status = RiskStatus.ALLOWED if not blockers and opportunity.swing_size_multiplier >= 0.75 else RiskStatus.REDUCED
    return RiskAssessment(
        symbol=opportunity.symbol,
        status=status if not blockers else RiskStatus.BLOCKED,
        allowed=not blockers,
        entry=entry, stop=stop, target=target,
        risk_per_share=risk_per_share, reward_risk=reward_risk,
        risk_amount=risk_amount, position_size_pct=position_pct,
        position_value=position_value, shares=shares,
        portfolio_heat_before=heat_before, portfolio_heat_after=heat_after,
        reasons=["fixed-fractional risk applied", "market size multiplier applied"],
        blocking_reasons=blockers,
        provenance={"rules_version": "risk-v1", "source": "deterministic"},
    )
