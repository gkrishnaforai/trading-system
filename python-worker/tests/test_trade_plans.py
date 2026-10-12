"""Golden cases for trade_plans — the YAML plan_status rules and the
ctx normalization that feeds them (direction, R math, days, trail)."""
from __future__ import annotations

from datetime import date, timedelta

from app.signals.trade_plans import _ctx, _match


def _plan(**kw):
    base = {"id": 1, "symbol": "CRM", "use_case": "swing",
            "direction": "long", "entry_px": 230.0,
            "entry_date": date.today() - timedelta(days=3),
            "stop_px": 220.0, "target1_px": 245.0,
            "target2_px": 250.0, "time_stop_days": 15}
    base.update(kw)
    return base


def _live(**kw):
    base = {"px": 232.0, "mom": "uptrend", "dip_phase": "turning_up",
            "pulse_action": "hold", "pulse_rule": "hold",
            "det": {"swing": {}}}
    base.update(kw)
    return base


def test_on_track():
    m = _match(_ctx(_plan(), _live()))
    assert m["status"] == "on_track" and m["action_hint"] == "hold"


def test_stop_hit_exits():
    m = _match(_ctx(_plan(), _live(px=219.0)))
    assert m["status"] == "stop_hit" and m["action_hint"] == "exit"


def test_thesis_invalidated_exits():
    # pulse reduce outranks price levels — thesis death is stronger
    # than "above stop for now"
    m = _match(_ctx(_plan(), _live(pulse_action="reduce",
                                  pulse_rule="broken_no_support")))
    assert m["status"] == "invalidated"


def test_target_ladder():
    assert _match(_ctx(_plan(), _live(px=246.0)))["status"] \
        == "target1_hit"
    assert _match(_ctx(_plan(), _live(px=251.0)))["status"] \
        == "target2_hit"
    # t2 outranks t1 and everything below it
    m = _match(_ctx(_plan(), _live(px=260.0)))
    assert m["status"] == "target2_hit"


def test_extended_scales_out():
    m = _match(_ctx(_plan(), _live(pulse_action="trim",
                                   pulse_rule="climax_corroborated")))
    assert m["status"] == "extended" and m["action_hint"] == "scale_out"


def test_stalled_time_stop():
    p = _plan(entry_date=date.today() - timedelta(days=20))
    m = _match(_ctx(p, _live(dip_phase="stabilizing")))
    assert m["status"] == "stalled"
    # confirmed repair is NOT stale — the setup resolved
    assert _match(_ctx(p, _live(dip_phase="confirmed")))["status"] \
        == "on_track"


def test_trail_opportunity():
    lv = _live(det={"swing": {"swing_low": 225.0}})
    m = _match(_ctx(_plan(), lv))
    assert m["status"] == "trail_up"
    c = _ctx(_plan(), lv)
    assert c["trail_to"] == 225.0
    # a swing low BELOW the plan stop is no ratchet
    lv2 = _live(det={"swing": {"swing_low": 210.0}})
    assert _ctx(_plan(), lv2)["trail_up"] is False


def test_short_direction_flips_levels():
    p = _plan(use_case="leap_put", direction="short",
              entry_px=100.0, stop_px=110.0,
              target1_px=85.0, target2_px=80.0)
    # rising through the stop = invalidation for a short
    assert _match(_ctx(p, _live(px=111.0)))["status"] == "stop_hit"
    # falling to target = profit for a short
    assert _match(_ctx(p, _live(px=79.0)))["status"] == "target2_hit"
    # R math is direction-aware: +8 the short way = +0.8R
    c = _ctx(p, _live(px=92.0))
    assert c["r"] == 0.8


def test_missing_px_never_fires_levels():
    m = _match(_ctx(_plan(), _live(px=None)))
    assert m["status"] == "on_track"  # missing ≠ stop, ≠ target


def test_r_progress():
    c = _ctx(_plan(), _live(px=235.0))
    assert c["r"] == 0.5     # +5 on $10 risk
    c2 = _ctx(_plan(), _live(px=224.0))
    assert c2["r"] == -0.6
