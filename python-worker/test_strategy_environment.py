from app.market_regime.models import DimensionFacts, MarketRegime, RegimeLabel
from app.strategy_environment import EnvironmentQuality, StrategyHorizon, derive_strategy_environments


def _case(label, direction, condition, trend_score, deterioration, **facts):
    regime = MarketRegime(
        regime=label,
        direction=direction,
        condition=condition,
        confidence=0.8,
        trend_score=trend_score,
        deterioration_score=deterioration,
    )
    dimensions = DimensionFacts(
        trend=facts.get("trend", "unknown"),
        breadth=facts.get("breadth", "unknown"),
        participation=facts.get("participation", "unknown"),
        volatility=facts.get("volatility", "unknown"),
        macro=facts.get("macro", "unknown"),
        trend_score=trend_score,
        deterioration_score=deterioration,
    )
    return derive_strategy_environments(regime, dimensions)


def test_daily_data_does_not_authorize_day_trading():
    environments = _case(
        RegimeLabel.BULL_LOW_VOL, "bullish", "trend", 0.8, 0.2,
        trend="bullish", breadth="strong")
    day = environments[StrategyHorizon.DAY_TRADING]
    assert day.quality == EnvironmentQuality.LOW
    assert not day.data_sufficient
    assert day.long_permission == "disabled"
    assert day.size_multiplier == 0


def test_distribution_risk_restricts_swing_breakouts():
    environments = _case(
        RegimeLabel.DISTRIBUTION_RISK, "bullish", "distribution_risk",
        0.25, -0.6, trend="bullish_weakening", breadth="weakening",
        participation="narrow", volatility="normal_rising",
        macro="mildly_risk_off")
    swing = environments[StrategyHorizon.SWING]
    assert swing.quality == EnvironmentQuality.LOW
    assert swing.breakout_permission == "restricted"
    assert swing.size_multiplier <= 0.5


def test_bearish_market_allows_selective_short_environment():
    environments = _case(
        RegimeLabel.BEAR, "bearish", "bear", -0.7, -0.7,
        trend="bearish", breadth="deteriorating", participation="narrow")
    swing = environments[StrategyHorizon.SWING]
    assert swing.long_permission == "restricted"
    assert swing.short_permission == "allowed"


def test_investing_requires_fundamentals():
    environments = _case(
        RegimeLabel.BULL_LOW_VOL, "bullish", "trend", 0.8, 0.2,
        trend="bullish")
    investing = environments[StrategyHorizon.INVESTING]
    assert investing.quality == EnvironmentQuality.UNAVAILABLE
    assert not investing.data_sufficient
    assert investing.long_permission == "restricted"
