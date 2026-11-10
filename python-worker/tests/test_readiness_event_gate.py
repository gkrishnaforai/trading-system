"""Readiness event-window gate — a 'ready' swing inside ~2d of
earnings downgrades to 'close' (the institutional don't-open-into-
the-print rule). The gate read `earn_days` from a ctx that never
carried it — dead code until the caller passed it through. These
tests pin the wiring, not just the YAML."""
from app.signals import stock_health


def _all_pass_det():
    """momentum_detail that passes every swing checklist leg —
    constructive tape, above 50dma, not stretched, structure mapped
    and unbroken, sellers not accelerating."""
    return {
        "dip_phase": "turning_up",
        "vs_sma50": 0.05,
        "pct_b": 0.4,
        "rsi": 50.0,
        "hist_dir": 2.0,
        "vol_dip": 0.9,
        "swing": {"phase": "forming", "confirm_level": 100.0},
    }


def test_swing_ready_when_no_event_window():
    rd = stock_health._readiness("pullback", _all_pass_det(),
                                 "growing", {}, {}, {}, 10.0,
                                 earn_days=10)
    assert rd["swing"]["state"] == "ready"
    assert "event_window" not in rd["swing"]


def test_swing_ready_when_no_earnings_known():
    rd = stock_health._readiness("pullback", _all_pass_det(),
                                 "growing", {}, {}, {}, 10.0,
                                 earn_days=None)
    assert rd["swing"]["state"] == "ready"


def test_event_window_downgrades_ready_to_close():
    rd = stock_health._readiness("pullback", _all_pass_det(),
                                 "growing", {}, {}, {}, 10.0,
                                 earn_days=1)
    sw = rd["swing"]
    assert sw["state"] == "close"
    assert sw["event_window"] is True
    assert sw["earn_days"] == 1
    assert "earnings in 1d" in sw["event_note"]


def test_event_window_does_not_invent_ready():
    """A 'no' inside the window stays 'no' — the gate only caps,
    never promotes."""
    det = _all_pass_det()
    det["vs_sma50"] = -0.06           # below trend filter
    det["vol_dip"] = 1.6              # sellers still accelerating
    rd = stock_health._readiness("pullback", det, "growing",
                                 {}, {}, {}, 10.0, earn_days=1)
    assert rd["swing"]["state"] == "no"


def test_past_earnings_no_gate():
    """earn_days negative (already printed) must not gate."""
    rd = stock_health._readiness("pullback", _all_pass_det(),
                                 "growing", {}, {}, {}, 10.0,
                                 earn_days=-1)
    assert rd["swing"]["state"] == "ready"
