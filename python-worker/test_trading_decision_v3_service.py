import pytest

from app.services.trading_decision_v3_service import TradingDecisionV3Service


@pytest.fixture()
def svc() -> TradingDecisionV3Service:
    return TradingDecisionV3Service()


def f(
    svc: TradingDecisionV3Service,
    *,
    close: float = 100.0,
    prev_close: float | None = 100.0,
    ema20: float | None = 100.0,
    sma50: float | None = 95.0,
    sma50_trend_up: bool = False,
    rsi: float | None = 60.0,
    vol_ratio: float | None = 1.0,
    days_below_sma50: int = 0,
    low_20_prev: float | None = None,
):
    ind = {
        "close": close,
        "prev_close": prev_close,
        "ema_20": ema20,
        "sma_50": sma50,
        "sma50_trend_up": sma50_trend_up,
        "rsi_14": rsi,
        "vol_ratio": vol_ratio,
        "days_below_sma50": days_below_sma50,
        "low_20_prev": low_20_prev,
    }
    return svc._compute_features(ind)


@pytest.mark.parametrize(
    "features, expected",
    [
        (dict(close=130.0, ema20=100.0, sma50=95.0, rsi=80.0, vol_ratio=2.0), "climax"),
        (dict(close=90.0, ema20=100.0, sma50=95.0, rsi=40.0, vol_ratio=2.0), "breakdown"),
        (dict(close=99.0, ema20=100.0, sma50=95.0, rsi=50.0, vol_ratio=1.0), "pullback"),
        (dict(close=101.0, ema20=100.0, sma50=95.0, rsi=60.0, vol_ratio=1.0), "trend"),
        (dict(close=100.0, ema20=None, sma50=95.0, rsi=60.0, vol_ratio=1.0), "base"),
    ],
)
def test_detect_state_priority(svc: TradingDecisionV3Service, features: dict, expected: str) -> None:
    snap = f(svc, **features)
    state, reasons = svc._detect_state(snap)
    assert state == expected
    assert any(r.startswith("state:") for r in reasons)


@pytest.mark.parametrize(
    "features, expected",
    [
        (dict(close=130.0, ema20=100.0, sma50=95.0, rsi=80.0, vol_ratio=2.0), "climax_exhaustion"),
        (dict(close=130.0, ema20=100.0, sma50=95.0, rsi=80.0, vol_ratio=1.2), "extended_trend"),
        (dict(close=120.0, ema20=100.0, sma50=95.0, rsi=70.0, vol_ratio=1.5), "momentum_trend"),
        (dict(close=120.0, ema20=100.0, sma50=95.0, rsi=70.0, vol_ratio=1.2), "late_trend"),
        (dict(close=105.0, ema20=100.0, sma50=95.0, rsi=60.0, vol_ratio=0.7), "low_volume_uptrend"),
        (dict(close=95.0, ema20=100.0, sma50=95.0, rsi=45.0, vol_ratio=2.0), "distribution"),
        (dict(close=95.0, ema20=100.0, sma50=95.0, rsi=45.0, vol_ratio=1.0), "pullback"),
    ],
)
def test_classify_phase(svc: TradingDecisionV3Service, features: dict, expected: str) -> None:
    snap = f(svc, **features)
    assert svc._classify_phase(snap) == expected


@pytest.mark.parametrize(
    "features, expected",
    [
        (dict(close=100.0, ema20=None, sma50=95.0, rsi=60.0, vol_ratio=1.0), "controlled"),
        (dict(close=113.0, ema20=100.0, sma50=95.0, rsi=60.0, vol_ratio=1.0), "extended"),
        (dict(close=126.0, ema20=100.0, sma50=95.0, rsi=60.0, vol_ratio=1.0), "extreme"),
    ],
)
def test_classify_extension(svc: TradingDecisionV3Service, features: dict, expected: str) -> None:
    snap = f(svc, **features)
    assert svc._classify_extension(snap) == expected


def test_map_action_trend_extreme_with_volume_trims(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=126.0, ema20=100.0, sma50=95.0, rsi=70.0, vol_ratio=2.0)
    action, reasons = svc._map_action("trend", "climax_exhaustion", "extreme", snap)
    assert action == "trim"
    assert reasons


def test_map_action_trend_red_day_filter_holds(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=99.0, prev_close=101.0, ema20=95.0, sma50=90.0, rsi=60.0, vol_ratio=1.0)
    action, reasons = svc._map_action("trend", "healthy_trend", "controlled", snap)
    assert action == "hold"
    assert "pullback_inside_trend" in reasons


def test_map_action_trend_no_chase_zone_holds(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=109.0, prev_close=110.0, ema20=100.0, sma50=95.0, rsi=65.0, vol_ratio=1.0)
    assert snap.no_chase_zone is True
    action, reasons = svc._map_action("trend", "healthy_trend", "controlled", snap)
    assert action == "hold"
    assert "mid_extension_no_chase" in reasons


def test_map_action_trend_extreme_red_day_trims_light(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=126.0, prev_close=130.0, ema20=100.0, sma50=95.0, rsi=70.0, vol_ratio=1.0)
    assert svc._classify_extension(snap) == "extreme"
    action, reasons = svc._map_action("trend", "extended_trend", "extreme", snap)
    assert action == "trim_light"
    assert "extreme_but_weakening" in reasons


def test_map_action_breakdown_high_volume_exits(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=90.0, ema20=100.0, sma50=95.0, rsi=35.0, vol_ratio=2.0)
    action, reasons = svc._map_action("breakdown", "distribution", "controlled", snap)
    assert action == "exit"
    assert reasons


def test_map_action_pullback_below_sma50_with_volume_reduces(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=90.0, ema20=100.0, sma50=95.0, rsi=50.0, vol_ratio=2.0, days_below_sma50=2)
    action, reasons = svc._map_action("pullback", "distribution", "controlled", snap)
    assert action == "reduce"
    assert "below_sma50_distribution" in reasons


def test_map_action_pullback_below_sma50_reduce_without_volume(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=94.0, ema20=100.0, sma50=95.0, rsi=50.0, vol_ratio=1.0)
    action, reasons = svc._map_action("pullback", "pullback", "controlled", snap)
    assert action == "hold"
    assert "below_sma50_wait" in reasons


def test_map_action_pullback_below_sma50_low_volume_accumulation_adds_light(svc: TradingDecisionV3Service) -> None:
    snap = f(
        svc,
        close=94.0,
        ema20=100.0,
        sma50=95.0,
        sma50_trend_up=True,
        rsi=55.0,
        vol_ratio=0.7,
        days_below_sma50=2,
        low_20_prev=90.0,
    )
    assert snap.vol_low is True
    assert snap.support_holding is True
    action, reasons = svc._map_action("pullback", "pullback", "controlled", snap)
    assert action == "add_light"
    assert "below_sma50_low_volume_accumulation" in reasons


def test_map_action_pullback_reclaim_sma50_adds_light(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=101.0, prev_close=99.0, ema20=100.0, sma50=100.0, rsi=60.0, vol_ratio=1.0)
    assert snap.reclaim_sma50 is True
    action, reasons = svc._map_action("pullback", "healthy_trend", "controlled", snap)
    assert action == "add_light"
    assert "reclaim_sma50" in reasons


def test_safety_override_no_reduce_above_ema20(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=105.0, ema20=100.0, sma50=95.0, rsi=60.0, vol_ratio=1.0)
    action, reasons, phase = svc._apply_safety_overrides("trend", "healthy_trend", "controlled", "reduce", snap)
    assert action == "hold"
    assert "override_no_reduce_above_ema20" in reasons
    assert phase == "healthy_trend"


def test_safety_override_reduce_allowed_above_ema20_on_high_volume(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=105.0, ema20=100.0, sma50=95.0, rsi=60.0, vol_ratio=2.0)
    action, reasons, phase = svc._apply_safety_overrides("trend", "high_volume_trend", "controlled", "reduce", snap)
    assert action == "reduce"
    assert "override_reduce_on_high_volume" in reasons
    assert phase == "high_volume_trend"


def test_safety_override_no_add_in_breakdown(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=90.0, ema20=100.0, sma50=95.0, rsi=40.0, vol_ratio=2.0)
    action, reasons, _ = svc._apply_safety_overrides("breakdown", "distribution", "controlled", "add_light", snap)
    assert action == "reduce"
    assert "override_no_add_in_breakdown" in reasons


def test_safety_override_climax_must_trim(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=130.0, ema20=100.0, sma50=95.0, rsi=85.0, vol_ratio=2.0)
    action, reasons, _ = svc._apply_safety_overrides("climax", "climax_exhaustion", "extreme", "hold", snap)
    assert action == "trim_light"
    assert "override_climax_must_trim" in reasons


def test_safety_override_pullback_phase_forced_to_pullback(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=99.0, ema20=100.0, sma50=95.0, rsi=55.0, vol_ratio=1.0)
    action, reasons, phase = svc._apply_safety_overrides("pullback", "momentum_trend", "controlled", "add_light", snap)
    assert action == "add_light"
    assert "override_pullback_phase" in reasons
    assert phase == "pullback"


@pytest.mark.parametrize(
    "features, expected",
    [
        (dict(close=131.0, ema20=100.0, sma50=95.0, rsi=60.0, vol_ratio=2.0), "extreme"),
        (dict(close=131.0, ema20=100.0, sma50=95.0, rsi=60.0, vol_ratio=1.0), "high"),
        (dict(close=100.0, ema20=100.0, sma50=95.0, rsi=86.0, vol_ratio=1.0), "extreme"),
        (dict(close=121.0, ema20=100.0, sma50=95.0, rsi=60.0, vol_ratio=1.0), "high"),
        (dict(close=100.0, ema20=100.0, sma50=95.0, rsi=76.0, vol_ratio=1.0), "high"),
        (dict(close=95.0, ema20=100.0, sma50=95.0, rsi=50.0, vol_ratio=2.0), "high"),
        (dict(close=104.0, ema20=100.0, sma50=95.0, rsi=60.0, vol_ratio=1.0), "low"),
        (dict(close=110.0, ema20=100.0, sma50=95.0, rsi=60.0, vol_ratio=1.0), "medium"),
    ],
)
def test_classify_risk(svc: TradingDecisionV3Service, features: dict, expected: str) -> None:
    snap = f(svc, **features)
    assert svc._classify_risk(snap) == expected


def test_confidence_bump_for_trend_rsi_zone(svc: TradingDecisionV3Service) -> None:
    snap = f(svc, close=105.0, ema20=100.0, sma50=95.0, rsi=60.0, vol_ratio=1.0)
    c = svc._score_confidence("trend", snap)
    assert c == pytest.approx(0.67)
