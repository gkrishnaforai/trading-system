from app.market_regime.models import (
    BreadthState, MarketSnapshot, MomentumState, ParticipationState,
    TrendState, VolatilityState, MacroState, StructureState, DimensionFacts,
)
from app.market_regime.transition import derive_bullish_transition


def _snapshot():
    return MarketSnapshot(
        trend=TrendState(spy_price=100, above_sma20=True, above_sma50=True, above_sma200=True),
        momentum=MomentumState(rsi14=54, rsi_5d_change=5, macd_hist=1, roc5=0.02),
        breadth=BreadthState(pct_above_sma50=58, breadth_chg_5d=8, breadth_chg_20d=12),
        volatility=VolatilityState(vix=16, vix_chg_5d=-2),
        participation=ParticipationState(pct_sectors_above_sma50=65, rel_strength_5d={"QQQ": 0.02, "SOXX": 0.03, "IWM": 0.01}),
        macro=MacroState(),
        structure=StructureState(spy_higher_low=True, spy_higher_high=True),
        coverage={"index": 2, "breadth": 100},
    )


def test_improving_facts_create_selective_or_better_transition():
    facts = DimensionFacts(
        trend="bullish", momentum="recovering", breadth="improving",
        volatility="normal", participation="broad", macro="neutral",
        structure="recovering",
        scores={
            "trend": 0.8, "momentum": 0.5, "breadth": 0.5,
            "volatility": 0.3, "participation": 0.5, "macro": 0.0,
            "structure": 0.6,
        },
        trend_score=0.8, deterioration_score=0.4,
    )
    result = derive_bullish_transition(_snapshot(), facts)
    assert result.score >= 55
    assert result.stage in {"SELECTIVE", "ACTIVE", "CONFIRMED", "NORMAL"}
    assert result.dip_buying_environment != "DISABLED"
    assert result.data_sufficient


def test_missing_coverage_caps_transition():
    snapshot = _snapshot().model_copy(update={"coverage": {}})
    facts = DimensionFacts(scores={"trend": 0.5}, trend_score=0.5)
    result = derive_bullish_transition(snapshot, facts)
    assert result.stage == "WATCH"
    assert result.size_multiplier == 0.25
    assert not result.data_sufficient
