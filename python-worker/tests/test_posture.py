"""Posture rules — the 'can we initiate today' permission layer.
evaluate() is pure: (stance, payload) → permissions. Missing
breadth data must fail rules, not silently permit."""
from app.signals.posture import evaluate, _pcond


def _payload(**breadth):
    b = {"breadth_score": 50.0, "pct_hl_broken": 20.0,
         "pct_above_50": 50.0, "pct_20d_low": 5.0,
         "pct_up_5d": 55.0}
    b.update(breadth)
    return {"breadth": b, "forward": {"p_deeper_dip_20d": 30},
            "regime": "bull_low_vol", "hedge": {"tier": "calm"}}


def test_breadth_collapse_blocks_longs():
    r = evaluate("NEUTRAL", _payload(breadth_score=18.0))
    assert r["posture"] == "defensive"
    assert r["new_longs"] is False and r["shorts"] is True
    assert r["matched"] == "breadth_collapse"


def test_thin_tape_is_caution():
    r = evaluate("NEUTRAL", _payload(breadth_score=28.0,
                                     pct_hl_broken=40.0))
    assert r["posture"] == "caution"
    assert r["new_longs"] is False and r["shorts"] is False
    assert r["hedge_on"] is True


def test_deep_correction_permits_shorts():
    p = _payload()
    p["forward"]["p_deeper_dip_20d"] = 60
    r = evaluate("NEUTRAL", p)
    assert r["matched"] == "deep_correction"
    assert r["shorts"] is True


def test_defensive_stance_forces_defensive():
    r = evaluate("DEFENSIVE", _payload())
    assert r["posture"] == "defensive" and r["new_longs"] is False


def test_broad_strength_is_constructive():
    r = evaluate("NEUTRAL",
                 _payload(breadth_score=70.0, pct_above_50=60.0))
    assert r["posture"] == "constructive"
    assert r["new_longs"] is True


def test_missing_breadth_falls_to_default():
    # no breadth block at all → every breadth rule fails → default
    r = evaluate("NEUTRAL", {"forward": {}, "hedge": {}})
    assert r["posture"] == "neutral" and r["matched"] == "default"
    assert r["new_longs"] is True


def test_pcond_missing_value_fails():
    assert _pcond({"breadth_score": None}, {"breadth_score_lt": 30}) \
        is False
    assert _pcond({}, {"stance_in": ["DEFENSIVE"]}) is False
    assert _pcond({"stance": "DEFENSIVE"},
                  {"stance_in": ["DEFENSIVE"]}) is True


def test_rule_order_first_match_wins():
    # collapse (bs<22) must beat thin_tape (bs<32) — order matters
    r = evaluate("NEUTRAL", _payload(breadth_score=15.0,
                                     pct_hl_broken=50.0))
    assert r["matched"] == "breadth_collapse"
