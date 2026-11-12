"""AI cycle rotation tracker — component scoring, three-peak
detection, rev-peak-risk and decision rules. Synthetic ctx dicts
only; no DB, no network."""
from datetime import date

from app.signals import cycle_tracker as ct


def _strong_ctx(**over):
    """A late-buildout leader: fast growth, rising estimates, clean
    financing, peak window years away."""
    c = {
        "rev_growth": 0.55, "rev_accel": 0.08, "ai_tailwind": 80,
        "rpo_yoy": 0.35, "crpo_share": 0.5, "def_rev_yoy": 0.3,
        "est_revision_pct": 0.12, "beat_streak": 6,
        "om_slope": 0.06, "om_now": 0.35, "fcf_margin": 0.3,
        "fcf_ttm": 5e9, "margin_trend": 2,
        "utilization_rank": 3, "durability_rank": 4,
        "top1_pct": 0.10, "design_wins_n": 4, "monetization_rank": 3,
        "funding_rank": 3, "nde": 0.5, "dilution_pct": 0.01,
        "runway_quarters": None, "vo_score": 70, "fwd_pe": 30,
        "thesis_status": "on_track", "structural_break": False,
        "capex_score": 30, "rev_qoq": 0.12, "q_rev_accel": 0.05,
        "order_peak": False, "estimate_peak": False,
        "revenue_peak": False,
        "quarters_to_peak": 10, "sourced_qtp": None,
        "peak_source": "cohort_seed", "valuation_blocked": False,
        "rev_peak_risk": 0, "coverage_pct": 1.0,
    }
    c.update(over)
    return c


# ---------------- component scoring ---------------------------------

def test_score_full_coverage():
    s = ct._score(_strong_ctx())
    assert s["composite"] is not None and s["composite"] >= 75
    assert s["coverage_pct"] == 1.0
    assert all(not c.get("unknown")
               for c in s["components"].values())


def test_score_missing_evidence_is_unknown_not_zero():
    s = ct._score(_strong_ctx(rpo_yoy=None, def_rev_yoy=None,
                              crpo_share=None))
    bl = s["components"]["backlog_quality"]
    assert bl["unknown"] is True and bl["score"] is None
    # composite renormalizes over the remaining 85 pts — still high
    assert s["composite"] is not None and s["composite"] > 60
    assert s["coverage_pct"] == 0.85


def test_score_empty_ctx_unknown_everything():
    s = ct._score({})
    assert s["composite"] is None
    assert all(c.get("unknown") for c in s["components"].values())


def test_score_shrinking_revenue_capped():
    s = ct._score(_strong_ctx(rev_growth=-0.05))
    assert s["composite"] is not None and s["composite"] <= 45
    assert s["capped"]


# ---------------- three-peak detection ------------------------------

def test_order_peak_on_rpo_decline():
    p = ct._detect_peaks(_strong_ctx(rpo_yoy=-0.10), None)
    assert p["order_peak"] is True


def test_order_peak_false_when_backlog_healthy():
    p = ct._detect_peaks(_strong_ctx(), None)
    assert p["order_peak"] is False
    assert p["estimate_peak"] is False
    assert p["revenue_peak"] is False


def test_order_peak_none_without_evidence():
    ctx = _strong_ctx(rpo_yoy=None, def_rev_yoy=None, rev_accel=None)
    p = ct._detect_peaks(ctx, None)
    assert p["order_peak"] is None


def test_order_peak_prior_leg_collapse():
    prior = {"components": {"backlog_quality": {"score": 80}}}
    ctx = _strong_ctx(rpo_yoy=None, def_rev_yoy=None, rev_accel=None,
                      _leg_backlog_quality=50)
    p = ct._detect_peaks(ctx, prior)
    assert p["order_peak"] is True


def test_estimate_peak_on_revision_cuts():
    p = ct._detect_peaks(_strong_ctx(est_revision_pct=-0.06), None)
    assert p["estimate_peak"] is True


def test_revenue_peak_on_negative_qoq():
    p = ct._detect_peaks(_strong_ctx(rev_qoq=-0.02), None)
    assert p["revenue_peak"] is True


# ---------------- rev peak risk --------------------------------------

def test_rev_peak_risk_clean():
    ctx = _strong_ctx()
    risk, basis = ct._rev_peak_risk(ctx)
    assert risk == 0 and not basis


def test_rev_peak_risk_stacks_leading_legs():
    ctx = _strong_ctx(est_revision_pct=-0.10, rev_accel=-0.08,
                      order_peak=True, capex_score=60,
                      thesis_status="deteriorating")
    risk, basis = ct._rev_peak_risk(ctx)
    assert risk == 30 + 25 + 20 + 15 + 10   # legs stack to 100
    assert "estimates being cut" in basis


# ---------------- peak window + movement ----------------------------

def test_qtp_midpoint_convention():
    peak = {"lo": 2028, "hi": 2029}
    # 2026Q4 -> midpoint 2028.5: 6 quarters
    assert ct._qtp(peak, date(2026, 11, 12)) == 6
    assert ct._qtp({"lo": None}, date(2026, 11, 12)) is None


def test_movement_range_semantics():
    prior = {"demand_peak_lo": 2029, "demand_peak_hi": 2030}
    assert ct._movement({"lo": 2027, "hi": 2028}, prior) == "pulled_forward"
    assert ct._movement({"lo": 2031, "hi": 2032}, prior) == "pushed_out"
    assert ct._movement({"lo": 2029, "hi": 2031}, prior) == "unchanged"
    assert ct._movement({"lo": 2028, "hi": 2029}, None) == "new"


# ---------------- decisions ------------------------------------------

def _decide_ctx(**over):
    base = {"composite": 80}
    base.update(over)
    return _strong_ctx(**base)


def test_decide_accumulate():
    ctx = _decide_ctx()
    ctx["rev_peak_risk"], _ = ct._rev_peak_risk(ctx)
    action, detail, flags = ct._decide(ctx)
    assert action == "accumulate"
    assert "peak_window_unsourced" in flags      # seed is flagged
    assert detail["note"]


def test_decide_accumulate_blocked_by_order_peak():
    ctx = _decide_ctx(order_peak=True)
    ctx["rev_peak_risk"], _ = ct._rev_peak_risk(ctx)
    action, _d, flags = ct._decide(ctx)
    assert action == "add_on_pullback"
    assert "order_peak_warning" in flags


def test_decide_trim_on_rev_peak_risk():
    ctx = _decide_ctx(rev_peak_risk=75)
    action, _d, _f = ct._decide(ctx)
    assert action == "trim"


def test_decide_trim_both_peaks_rolled():
    ctx = _decide_ctx(order_peak=True, estimate_peak=True,
                      rev_peak_risk=20)
    action, _d, _f = ct._decide(ctx)
    assert action == "trim"


def test_decide_exit_on_break():
    ctx = _decide_ctx(structural_break=True)
    action, _d, _f = ct._decide(ctx)
    assert action == "exit"


def test_decide_seed_peak_cannot_trim():
    """A cohort-seed window inside 4q must not trigger the
    proximity trim — only sourced_qtp can."""
    ctx = _decide_ctx(composite=50, quarters_to_peak=2,
                      sourced_qtp=None)
    action, _d, _f = ct._decide(ctx)
    assert action == "hold"


def test_decide_sourced_peak_trims():
    ctx = _decide_ctx(composite=50, quarters_to_peak=2,
                      sourced_qtp=2)
    action, _d, _f = ct._decide(ctx)
    assert action == "trim"


def test_decide_hold_mid_band():
    ctx = _decide_ctx(composite=55)
    action, _d, _f = ct._decide(ctx)
    assert action == "hold"


def test_decide_research_incomplete_thin():
    ctx = _decide_ctx(composite=30)
    action, _d, flags = ct._decide(ctx)
    assert action == "trim"        # composite <45 is a trim rule
    ctx2 = _decide_ctx(composite=None)
    action2, _d2, _f2 = ct._decide(ctx2)
    assert action2 == "research_incomplete"


def test_quarter_label():
    assert ct._quarter_label(date(2026, 11, 12)) == "2026Q4"
    assert ct._quarter_label(date(2027, 2, 1)) == "2027Q1"
