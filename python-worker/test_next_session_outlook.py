"""Deterministic next-session outlook tests — no LLM, no providers."""
from datetime import datetime, timezone

from app.market_regime.models import (
    BreadthState, DimensionFacts, MarketPermissions, MarketRegime,
    MarketSnapshot, MomentumState, RegimeLabel, StructureState,
    TrendState, VolatilityState,
)
from app.market_regime.outlook import derive_next_session_outlook
from app.market_events import MarketEvent, MarketEventType, EventSeverity, EventStatus


def _snapshot(**kwargs) -> MarketSnapshot:
    defaults = dict(
        as_of=datetime(2026, 9, 18, tzinfo=timezone.utc),
        trend=TrendState(spy_price=761.0, sma20=764.0, sma50=759.0,
                         sma200=716.0, above_sma20=False, above_sma50=True,
                         above_sma200=True),
        momentum=MomentumState(rsi14=52.0, ret1=0.001, ret5=-0.01),
        breadth=BreadthState(pct_above_sma50=45.0),
        volatility=VolatilityState(vix=15.0, vix_term_ratio=1.2),
        structure=StructureState(dist_from_20d_high=-0.02),
    )
    defaults.update(kwargs)
    return MarketSnapshot(**defaults)


def _regime(**kwargs) -> MarketRegime:
    defaults = dict(
        regime=RegimeLabel.BULLISH_CORRECTION,
        direction="neutral", condition="correction",
        confidence=0.6, trend_score=0.1, deterioration_score=-0.05,
        bullish_transition_score=45.0, transition_stage="WATCH",
        market_permissions=MarketPermissions(size_multiplier=0.3),
    )
    defaults.update(kwargs)
    return MarketRegime(**defaults)


def _facts(**kwargs) -> DimensionFacts:
    defaults = dict(trend="bullish_weakening", momentum="neutral",
                    breadth="weakening", volatility="low",
                    participation="narrow", macro="neutral", structure="recovering")
    defaults.update(kwargs)
    return DimensionFacts(**defaults)


def test_balanced_evidence_gives_choppy_base_case():
    outlook = derive_next_session_outlook(_snapshot(), _facts(), _regime())
    assert outlook.base_case.label == "choppy_consolidation"
    assert outlook.bias in {"neutral", "cautious"}
    assert outlook.confidence == "low"
    assert outlook.disclaimer
    assert outlook.drivers


def test_improving_transition_gives_recovery_base_case():
    snap = _snapshot()
    snap.trend.above_sma20 = True
    outlook = derive_next_session_outlook(
        snap, _facts(momentum="recovering", breadth="improving"),
        _regime(bullish_transition_score=62.0, transition_delta_1d=4.0,
                trend_score=0.3, deterioration_score=0.0))
    assert outlook.base_case.label == "recovery_continuation"
    assert outlook.bias in {"constructive", "neutral"}


def test_bear_regime_is_defensive():
    outlook = derive_next_session_outlook(
        _snapshot(), _facts(breadth="deteriorating", volatility="high_rising"),
        _regime(regime=RegimeLabel.BEAR, condition="bear",
                trend_score=-0.5, deterioration_score=-0.4))
    assert outlook.bias == "defensive"
    assert outlook.base_case.label == "defensive_positioning"
    assert outlook.confidence == "low"


def test_scheduled_high_severity_event_dominates():
    event = MarketEvent(
        event_id="fomc-1", event_type=MarketEventType.FOMC,
        event_name="FOMC Rate Decision", severity=EventSeverity.HIGH,
        status=EventStatus.SCHEDULED,
        scheduled_at=datetime(2026, 9, 19, 18, 0, tzinfo=timezone.utc),
    )
    outlook = derive_next_session_outlook(
        _snapshot(), _facts(), _regime(trend_score=0.4, deterioration_score=0.0),
        event=event)
    assert outlook.base_case.label == "event_driven"
    assert outlook.event_risks
    assert outlook.confidence == "low"


def test_stressed_term_structure_surfaces_tail_risk():
    snap = _snapshot(volatility=VolatilityState(vix=24.0, vix_term_ratio=0.9))
    outlook = derive_next_session_outlook(snap, _facts(), _regime())
    assert outlook.tail_risk is not None
    assert outlook.tail_risk.label == "volatility_shock"


def test_scenarios_always_carry_confirmation_and_invalidation():
    outlook = derive_next_session_outlook(_snapshot(), _facts(), _regime())
    for scenario in (outlook.base_case, outlook.alternative):
        assert scenario.confirmations
        assert scenario.invalidations
