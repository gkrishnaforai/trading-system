"""Pattern detection + learning-loop tests."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.market_data.models import OHLCVBar
from app.market_regime.models import DimensionFacts, MarketPermissions, MarketRegime, RegimeLabel
from app.strategy_environment.models import EnvironmentQuality, StrategyEnvironment, StrategyHorizon
from app.swing_opportunity.engine import analyze_stock, detect_setup
from app.swing_opportunity.models import SetupType


def _bars(symbol: str, values: list[float]) -> list[OHLCVBar]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [OHLCVBar(
        symbol=symbol, timestamp=start + timedelta(days=i), provider="test",
        open=v, high=v * 1.01, low=v * 0.99, close=v, volume=1_000_000,
    ) for i, v in enumerate(values)]


def _regime():
    return MarketRegime(
        regime=RegimeLabel.BULL_LOW_VOL, direction="bullish", condition="trend",
        confidence=0.8, trend_score=0.7, deterioration_score=0.1,
        market_permissions=MarketPermissions(
            normal_long=True, dip_buying=True,
            breakout_buying="allowed", size_multiplier=0.75),
    )


def _environment():
    return StrategyEnvironment(
        horizon=StrategyHorizon.SWING, quality=EnvironmentQuality.MEDIUM,
        score=65, confidence=0.8, long_permission="limited",
        breakout_permission="allowed", pullback_permission="allowed",
        size_multiplier=0.5, data_sufficient=True,
    )


def _spy():
    return _bars("SPY", [100 + i * 0.05 for i in range(220)])


def _first_pullback_bars():
    # Long base below SMA50, sharp rally crossing above it ~12 bars ago,
    # then a shallow 5-day pullback into the EMA20 zone. (200+ bars required.)
    values = ([80.0] * 185 + [85, 90, 95, 100, 103, 105, 106, 107]
              + [106, 105, 106, 105] + [104, 103, 102, 101, 100])
    return _bars("TEST", values)


def test_first_pullback_detected_after_fresh_trend_turn():
    stock = analyze_stock("TEST", _first_pullback_bars(), _spy())
    t = stock.technicals
    assert t.trend_turn_bars is not None and t.trend_turn_bars <= 30
    setup = detect_setup(stock, _regime(), _environment())
    assert setup.type == SetupType.FIRST_PULLBACK
    assert "first_pullback" in setup.detected_patterns


def test_stale_trend_turn_is_not_first_pullback():
    # Steady uptrend for 220 bars — the SMA50 cross is ancient history.
    stock = analyze_stock("TEST", _bars("TEST", [50 + i * 0.4 for i in range(220)]), _spy())
    assert stock.technicals.trend_turn_bars is None
    setup = detect_setup(stock, _regime(), _environment())
    assert setup.type != SetupType.FIRST_PULLBACK
    assert "first_pullback" not in setup.detected_patterns


def test_rsi2_extreme_detects_mean_reversion():
    # Long-term uptrend, then a violent 3-day flush → RSI(2) collapses.
    values = [100 + i * 0.5 for i in range(217)] + [200, 190, 181]
    stock = analyze_stock("TEST", _bars("TEST", values), _spy())
    t = stock.technicals
    assert t.rsi2 is not None and t.rsi2 < 10
    assert t.price > t.sma200
    setup = detect_setup(stock, _regime(), _environment())
    assert setup.type == SetupType.MEAN_REVERSION
    assert "rsi2_extreme" in setup.detected_patterns


def test_no_pattern_tags_when_no_setup():
    stock = analyze_stock("TEST", _bars("TEST", [100.0] * 220), _spy())
    setup = detect_setup(stock, _regime(), _environment())
    assert setup.type == SetupType.NO_SETUP
    assert setup.detected_patterns == []


def _swing_result(setup_type="first_pullback", falling_knife=False):
    return {
        "symbol": "TEST",
        "setup": {"type": setup_type, "score": 62,
                  "falling_knife": falling_knife,
                  "detected_patterns": ["first_pullback"]},
        "stock": {"technicals": {"price": 100.0, "rsi": 52, "rsi2": 8,
                                 "atr_pct": 0.03, "volume_ratio": 1.1,
                                 "trend_turn_bars": 9},
                  "relative_strength": {"vs_spy20": 0.04}},
        "risk": {"entry": 100.0, "stop": 94.0, "target": 112.0,
                 "reward_risk": 2.0, "status": "allowed"},
        "decision": {"action": "WAIT", "risk_status": "allowed"},
        "market_regime": {"regime": "bull_low_vol"},
        "swing_environment": {"long_permission": "limited",
                              "size_multiplier": 0.5},
    }


def test_record_signal_persists_setup():
    from app.pattern_learning import service as pl
    with patch.object(pl.db, "execute_update") as mock_write:
        pl.record_signal(_swing_result(), source="alert_review", run_id="r1")
    assert mock_write.called
    params = mock_write.call_args[0][1]
    assert params["symbol"] == "TEST"
    assert params["setup_type"] == "first_pullback"
    assert params["fingerprint"].startswith("sig:TEST:first_pullback:")
    assert params["stop"] == 94.0


def test_record_signal_derives_stop_from_atr_when_missing():
    from app.pattern_learning import service as pl
    result = _swing_result()
    result["risk"] = {"status": "blocked"}  # risk gate blocked → no plan
    with patch.object(pl.db, "execute_update") as mock_write:
        pl.record_signal(result, source="alert_review", run_id="r1")
    params = mock_write.call_args[0][1]
    assert params["entry"] == 100.0
    assert params["stop"] == 100.0 - 2 * 0.03 * 100.0  # 94.0
    assert params["target"] == 112.0


def test_record_signal_skips_no_setup_and_falling_knife():
    from app.pattern_learning import service as pl
    with patch.object(pl.db, "execute_update") as mock_write:
        pl.record_signal(_swing_result("no_setup"), source="x", run_id=None)
        pl.record_signal(_swing_result("pullback", falling_knife=True),
                         source="x", run_id=None)
    assert not mock_write.called


def test_score_adjustment_requires_min_sample():
    from app.pattern_learning import service as pl
    with patch.object(pl, "_stats_rows", return_value=[
            {"setup_type": "first_pullback", "horizon_bars": 10, "n": 5,
             "win_rate": 0.9, "avg_r": 2.0}]):
        adj, note = pl.score_adjustment("first_pullback")
    assert adj == 0.0 and note is None


def test_stock_permission_levels():
    from app.swing_opportunity.engine import _stock_permission
    from app.swing_opportunity.models import StockTechnicals
    base = dict(price=100.0, sma50=90.0, sma200=80.0, ret20=0.05, drawdown20=-0.02)
    assert _stock_permission(StockTechnicals(**base)) == "allowed"
    assert _stock_permission(StockTechnicals(**{**base, "ret20": -0.02})) == "limited"
    assert _stock_permission(StockTechnicals(
        **{**base, "price": 85.0, "ret20": -0.01})) == "restricted"
    assert _stock_permission(StockTechnicals(
        **{**base, "price": 70.0, "ret20": -0.10})) == "disabled"
    assert _stock_permission(StockTechnicals(price=None)) == "unknown"


def test_kill_zone_penalizes_trend_setup():
    # Stock above SMA50 (trend intact) but in a shallow pullback —
    # ret20 < 0 and dd20 < -5% → stock "limited"; with a limited index env
    # that's the kill zone → -20 score + reason.
    values = ([90.0] * 170 + [100, 110, 120, 125, 128, 130]
              + [129, 128, 128, 127, 127, 126, 126, 125, 125, 124,
                 124, 123, 123, 122, 122, 121, 121, 121, 120, 120,
                 120, 120, 120, 120, 120])
    stock = analyze_stock("TEST", _bars("TEST", values), _spy())
    t = stock.technicals
    assert t.price > t.sma50 and (t.ret20 or 0) < 0  # weak stock, trend intact
    limited_env = _environment().model_copy(update={"long_permission": "limited"})
    setup = detect_setup(stock, _regime(), limited_env)
    assert setup.stock_permission == "limited"
    if setup.type != SetupType.MEAN_REVERSION and setup.type != SetupType.NO_SETUP:
        assert any("kill zone" in r for r in setup.reasons)
        open_env = _environment().model_copy(update={"long_permission": "allowed"})
        open_setup = detect_setup(stock, _regime(), open_env)
        assert setup.score < open_setup.score  # kill zone cut the score


def test_mean_reversion_exempt_from_stock_regime_penalty():
    values = [100 + i * 0.5 for i in range(217)] + [200, 190, 181]
    stock = analyze_stock("TEST", _bars("TEST", values), _spy())
    limited_env = _environment().model_copy(update={"long_permission": "limited"})
    setup = detect_setup(stock, _regime(), limited_env)
    assert setup.type == SetupType.MEAN_REVERSION
    assert setup.stock_permission in {"limited", "restricted", "disabled"}
    assert not any("kill zone" in r or "stock's own regime" in r
                   for r in setup.reasons)


def test_score_adjustment_bounded_both_directions():
    from app.pattern_learning import service as pl
    strong = [{"setup_type": "first_pullback", "horizon_bars": 10, "n": 40,
               "win_rate": 0.9, "avg_r": 3.0}]
    weak = [{"setup_type": "breakout", "horizon_bars": 10, "n": 40,
             "win_rate": 0.1, "avg_r": -0.9}]
    with patch.object(pl, "_stats_rows", return_value=strong):
        adj, note = pl.score_adjustment("first_pullback")
    assert 0 < adj <= 8.0 and "empirical" in note
    with patch.object(pl, "_stats_rows", return_value=weak):
        adj, _ = pl.score_adjustment("breakout")
    assert -8.0 <= adj < 0
