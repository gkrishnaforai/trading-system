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


def test_leap_call_cyclical_accelerating_qualifies():
    """A cyclical label is the business model, not a health verdict —
    when the leading-legs lean is accelerating the LEAP-call fund gate
    passes (system rule: judge cyclicals by leading legs)."""
    rd = stock_health._readiness("pullback", _all_pass_det(),
                                 "cyclical", {}, {}, {}, 10.0,
                                 cyclical_lean="accelerating")
    assert rd["leap_call"]["state"] == "ready"
    fails = [x["line"] for x in rd["leap_call"]["rules"] if not x["ok"]]
    assert not any("fundamentals gate" in f for f in fails)


def test_leap_call_cyclical_downturn_blocked():
    """cyclical + downturn lean fails the same gate — the exception is
    the lean, not the label."""
    rd = stock_health._readiness("pullback", _all_pass_det(),
                                 "cyclical", {}, {}, {}, 10.0,
                                 cyclical_lean="downturn")
    assert rd["leap_call"]["state"] == "close"
    assert not rd["leap_call"]["rules"][1]["ok"]


def test_leap_call_cyclical_no_lean_blocked():
    """Unknown lean must not pass — missing data fails closed."""
    rd = stock_health._readiness("pullback", _all_pass_det(),
                                 "cyclical", {}, {}, {}, 10.0)
    assert rd["leap_call"]["state"] == "close"
    assert not rd["leap_call"]["rules"][1]["ok"]


def test_invest_gate_stays_strict():
    """Invest is the fundamental lane — cyclical+accelerating lean does
    NOT relax its fund gate; structural growers only."""
    rd = stock_health._readiness("pullback", _all_pass_det(),
                                 "cyclical", {}, {}, {}, 10.0,
                                 cyclical_lean="accelerating")
    assert rd["invest"]["rules"][0]["ok"] is False
