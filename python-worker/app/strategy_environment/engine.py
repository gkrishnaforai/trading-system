"""Deterministic strategy-environment suitability rules.

This phase evaluates the market for a horizon. It never evaluates a
specific stock and never emits a trade decision.
"""
from __future__ import annotations

from typing import Dict, Optional

from app.market_regime.models import DimensionFacts, MarketRegime, MarketSnapshot

from .models import EnvironmentQuality, StrategyEnvironment, StrategyHorizon


def _quality(score: float) -> EnvironmentQuality:
    if score >= 75:
        return EnvironmentQuality.HIGH
    if score >= 55:
        return EnvironmentQuality.MEDIUM
    return EnvironmentQuality.LOW


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def _daily_base(regime: MarketRegime, facts: DimensionFacts) -> float:
    score = 50.0
    trend = facts.trend_score if facts.trend_score is not None else 0.0
    deterioration = facts.deterioration_score if facts.deterioration_score is not None else 0.0
    score += trend * 25.0 + deterioration * 25.0
    if regime.direction == "bullish":
        score += 10
    elif regime.direction == "bearish":
        score -= 15
    if facts.breadth in {"strong", "improving"}:
        score += 8
    elif facts.breadth in {"weak", "deteriorating"}:
        score -= 8
    if facts.participation == "narrow":
        score -= 5
    if "rising" in facts.volatility or facts.volatility in {"elevated", "high"}:
        score -= 5
    return _clamp(score)


def derive_strategy_environments(
    regime: MarketRegime,
    facts: DimensionFacts,
    snapshot: Optional[MarketSnapshot] = None,
    *,
    intraday_data_available: bool = False,
    fundamental_data_available: bool = False,
) -> Dict[StrategyHorizon, StrategyEnvironment]:
    """Derive all horizon environments from canonical regime facts.

    Daily market data cannot establish a day-trading environment, so that
    horizon is explicitly unavailable until an intraday contract is supplied.
    """
    daily = _daily_base(regime, facts)
    permissions = regime.market_permissions
    size = permissions.size_multiplier if permissions else 0.5
    reasons = list(facts.drivers)

    if daily >= 70:
        swing_long, breakout, pullback = "allowed", "allowed", "allowed"
    elif daily >= 50:
        swing_long, breakout, pullback = "limited", "limited", "allowed"
    else:
        swing_long, breakout, pullback = "restricted", "restricted", "limited"

    swing = StrategyEnvironment(
        horizon=StrategyHorizon.SWING,
        quality=_quality(daily),
        score=daily,
        confidence=0.75 if snapshot and snapshot.coverage.get("index", 0) else 0.45,
        long_permission=swing_long,
        short_permission=("allowed" if regime.direction == "bearish" else "disabled"),
        breakout_permission=breakout,
        pullback_permission=pullback,
        size_multiplier=round(size, 2),
        pacing="staged" if daily < 70 else "normal",
        reasons=reasons,
        required_data=["daily OHLCV", "market breadth", "sector participation"],
        data_sufficient=bool(snapshot),
    )

    positional_score = _clamp(daily + (5 if facts.trend in {"bullish", "bullish_weakening"} else 0))
    positional = StrategyEnvironment(
        horizon=StrategyHorizon.POSITIONAL,
        quality=_quality(positional_score),
        score=positional_score,
        confidence=swing.confidence,
        long_permission="allowed" if positional_score >= 55 else "limited",
        short_permission="restricted" if regime.direction != "bearish" else "allowed",
        breakout_permission="limited" if positional_score < 75 else "allowed",
        pullback_permission="allowed" if positional_score >= 50 else "limited",
        size_multiplier=round(min(size, 0.75), 2),
        pacing="staged" if positional_score < 70 else "normal",
        reasons=reasons + ["positional decisions require weekly and fundamental confirmation"],
        required_data=["daily/weekly trend", "industry leadership", "fundamentals", "valuation"],
        data_sufficient=bool(snapshot),
    )

    investing_score = _clamp(60.0 + (10 if facts.trend in {"bullish", "bullish_weakening"} else 0))
    investing = StrategyEnvironment(
        horizon=StrategyHorizon.INVESTING,
        quality=_quality(investing_score) if fundamental_data_available else EnvironmentQuality.UNAVAILABLE,
        score=investing_score if fundamental_data_available else 0.0,
        confidence=0.65 if fundamental_data_available else 0.0,
        long_permission="allowed" if fundamental_data_available else "restricted",
        short_permission="disabled",
        breakout_permission="disabled",
        pullback_permission="allowed" if fundamental_data_available else "restricted",
        size_multiplier=round(min(size, 0.75), 2),
        pacing="staged" if daily < 75 else "normal",
        reasons=(reasons + ["market regime controls pacing, not business quality"]),
        required_data=["point-in-time fundamentals", "valuation", "balance sheet", "business quality"],
        data_sufficient=fundamental_data_available,
    )

    day_reasons = ["daily market data is insufficient for intraday suitability"]
    day = StrategyEnvironment(
        horizon=StrategyHorizon.DAY_TRADING,
        quality=EnvironmentQuality.LOW if not intraday_data_available else _quality(daily),
        score=0.0 if not intraday_data_available else daily,
        confidence=0.0 if not intraday_data_available else 0.5,
        long_permission="disabled" if not intraday_data_available else "limited",
        short_permission="disabled",
        breakout_permission="disabled" if not intraday_data_available else "limited",
        pullback_permission="disabled" if not intraday_data_available else "limited",
        size_multiplier=0.0 if not intraday_data_available else round(size, 2),
        pacing="wait",
        reasons=day_reasons if not intraday_data_available else ["intraday inputs require separate validation"],
        required_data=["1m/5m/15m OHLCV", "VWAP", "opening range", "intraday breadth", "relative volume", "spreads", "catalyst state"],
        data_sufficient=intraday_data_available,
    )

    return {
        StrategyHorizon.DAY_TRADING: day,
        StrategyHorizon.SWING: swing,
        StrategyHorizon.POSITIONAL: positional,
        StrategyHorizon.INVESTING: investing,
    }
