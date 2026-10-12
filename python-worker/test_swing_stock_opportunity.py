from datetime import datetime, timedelta, timezone

from app.market_data.models import OHLCVBar
from app.market_regime.models import DimensionFacts, MarketPermissions, MarketRegime, RegimeLabel
from app.strategy_environment.models import EnvironmentQuality, StrategyEnvironment, StrategyHorizon
from app.swing_opportunity.engine import analyze_stock, detect_setup
from app.swing_opportunity.models import OpportunityQuality, SetupType


def _bars(symbol: str, values: list[float]) -> list[OHLCVBar]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [OHLCVBar(
        symbol=symbol,
        timestamp=start + timedelta(days=i),
        provider="test",
        open=value,
        high=value * 1.01,
        low=value * 0.99,
        close=value,
        volume=1_000_000,
    ) for i, value in enumerate(values)]


def _regime(label=RegimeLabel.BULL_LOW_VOL, breakout="allowed"):
    return MarketRegime(
        regime=label,
        direction="bullish",
        condition="trend",
        confidence=0.8,
        trend_score=0.7,
        deterioration_score=0.1,
        market_permissions=MarketPermissions(
            normal_long=True, dip_buying=True,
            breakout_buying=breakout, size_multiplier=0.75),
    )


def _environment():
    return StrategyEnvironment(
        horizon=StrategyHorizon.SWING,
        quality=EnvironmentQuality.MEDIUM,
        score=65,
        confidence=0.8,
        long_permission="limited",
        breakout_permission="allowed",
        pullback_permission="allowed",
        size_multiplier=0.5,
        data_sufficient=True,
    )


def test_insufficient_history_is_not_actionable():
    stock = analyze_stock("TEST", _bars("TEST", list(range(100, 180))), _bars("SPY", list(range(100, 180))))
    setup = detect_setup(stock, _regime(), _environment())
    assert not stock.data_quality.sufficient
    assert setup.quality == OpportunityQuality.UNAVAILABLE
    assert setup.type == SetupType.NO_SETUP


def test_falling_knife_is_rejected():
    values = [300 - i for i in range(220)]
    stock = analyze_stock("TEST", _bars("TEST", values), _bars("SPY", [100] * 220))
    setup = detect_setup(stock, _regime(), _environment())
    assert stock.data_quality.sufficient
    assert setup.falling_knife
    assert setup.quality == OpportunityQuality.LOW
    assert setup.type == SetupType.NO_SETUP


def test_relative_strength_uses_spy_and_sector():
    stock = analyze_stock(
        "TEST", _bars("TEST", [100 + i * 0.5 for i in range(220)]),
        _bars("SPY", [100 for _ in range(220)]),
        _bars("XLK", [100 + i * 0.3 for i in range(220)]),
        sector="Technology", sector_symbol="XLK",
    )
    assert stock.relative_strength.vs_spy20 is not None
    assert stock.relative_strength.vs_sector20 is not None
    assert stock.relative_strength.tier in {"outperformer", "strong_outperformer"}
    assert stock.sector_alignment == "aligned"


def test_breakout_permission_is_respected():
    stock = analyze_stock(
        "TEST", _bars("TEST", [100 + i * 0.5 for i in range(220)]),
        _bars("SPY", [100 + i * 0.1 for i in range(220)]),
    )
    restricted = _environment().model_copy(update={"breakout_permission": "restricted"})
    setup = detect_setup(stock, _regime(breakout="restricted"), restricted)
    assert setup.type != SetupType.BREAKOUT


def test_case_file_preserves_fundamental_namespace():
    from app.swing_opportunity import build_swing_opportunity_graph
    from app.swing_opportunity.models import SwingOpportunity

    assert type(build_swing_opportunity_graph()).__name__ == "CompiledStateGraph"
    opportunity = SwingOpportunity(
        symbol="COIN",
        fundamentals={
            "business_type": "financial",
            "data_quality": "partial",
            "competitive_advantage": {"label": "unavailable"},
        },
    )
    assert opportunity.fundamentals["business_type"] == "financial"
    assert opportunity.fundamentals["competitive_advantage"]["label"] == "unavailable"
