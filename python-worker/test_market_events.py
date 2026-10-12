from datetime import datetime, timezone

from app.market_events import (
    EventReaction, EventSeverity, EventStatus, MarketEvent, MarketEventType,
    PolicyBias, ReactionState, apply_event_policy, resolve_current_market_event,
)
from app.strategy_environment.models import EnvironmentQuality, StrategyEnvironment, StrategyHorizon


def _environment():
    return StrategyEnvironment(
        horizon=StrategyHorizon.SWING,
        quality=EnvironmentQuality.HIGH,
        score=80,
        confidence=0.8,
        long_permission="allowed",
        short_permission="disabled",
        breakout_permission="allowed",
        pullback_permission="allowed",
        size_multiplier=1.0,
        pacing="normal",
        data_sufficient=True,
    )


def _fomc(status=EventStatus.SCHEDULED):
    return MarketEvent(
        event_id="fomc-2026-09-16",
        event_type=MarketEventType.FOMC,
        event_name="FOMC rate decision",
        severity=EventSeverity.EXTREME,
        status=status,
        policy_bias=PolicyBias.HAWKISH,
        future_policy={"additional_hike_risk": "HIGH"},
    )


def test_extreme_scheduled_event_restricts_entries():
    result = apply_event_policy(_environment(), _fomc())
    assert result.event_policy == "PRE_EVENT_RESTRICTED"
    assert not result.new_entries_allowed
    assert result.breakout_permission == "avoid"
    assert result.size_multiplier == 0.5


def test_confirmed_risk_off_reaction_tightens_policy():
    reaction = EventReaction(
        event_id="fomc-2026-09-16",
        state=ReactionState.RISK_OFF,
        confirmation=True,
        window_minutes=45,
    )
    result = apply_event_policy(_environment(), _fomc(EventStatus.RELEASED), reaction)
    assert result.event_policy == "REACTION_RISK_OFF"
    assert not result.new_entries_allowed
    assert result.size_multiplier == 0.25
    assert result.score == 45


def test_risk_on_reaction_does_not_boost_base_permissions():
    reaction = EventReaction(
        event_id="fomc-2026-09-16",
        state=ReactionState.RISK_ON,
        confirmation=True,
        window_minutes=45,
    )
    result = apply_event_policy(_environment(), _fomc(EventStatus.RELEASED), reaction)
    assert result.event_policy == "REACTION_RISK_ON_CONFIRMED"
    assert result.size_multiplier == 1.0
    assert result.score == 80


def test_no_event_preserves_environment():
    result = apply_event_policy(_environment())
    assert result.event_policy == "NORMAL"
    assert result.new_entries_allowed
    assert result.size_multiplier == 1.0


def test_fomc_calendar_resolver_detects_pre_event_window():
    now = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)
    event = resolve_current_market_event(now)
    assert event is not None
    assert event.event_type == MarketEventType.FOMC
    assert event.status == EventStatus.SCHEDULED
    assert event.severity == EventSeverity.EXTREME
    assert event.policy_bias == PolicyBias.UNKNOWN


def test_fomc_calendar_resolver_detects_released_event():
    now = datetime(2026, 9, 16, 19, 0, tzinfo=timezone.utc)
    event = resolve_current_market_event(now)
    assert event is not None
    assert event.status == EventStatus.RELEASED


def test_calendar_resolver_returns_none_on_normal_day():
    now = datetime(2026, 9, 20, 15, 0, tzinfo=timezone.utc)
    assert resolve_current_market_event(now) is None
