"""Deterministic-core evals for the confluence/RB machinery.

Pure-function truth tables — no DB, no network. Run:
    docker exec trading-system-python-worker pytest tests/ -q
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalyst_intelligence.engine import grade_direction, rating_action
from app.screener.rule_breakers import (
    _check_milestones, _gates, _milestone_metrics, _OPS)
from app.screener.analyst_tape import _firm_key, _grade_row
from app.screener.daily_edge import _catalyst_pts
from app.screener import daily_edge as de


# --- Rule Breaker gates ---------------------------------------------------

def _m(rev=None, streak=0, gm=None, mcap=None, **kw):
    return {"rev_growth": rev, "rev_streak": streak,
            "gross_margin": gm, "market_cap": mcap, **kw}


def test_gates_rev_is_fraction_not_percent():
    # the bug we fixed: 0.27 must pass the 25% gate
    g = _gates(_m(rev=0.27, streak=3, gm=0.5, mcap=6e9), prev_gm=0.48)
    assert g["rev>25%"] is True


def test_gates_full_table():
    g = _gates(_m(rev=0.10, streak=1, gm=0.4, mcap=50e9), prev_gm=0.45)
    assert g == {"rev>25%": False, "rev streak>=2": False,
                 "gm rising": False, "mcap $1-500B": True}
    g = _gates(_m(rev=0.30, streak=2, gm=0.5, mcap=2e9), prev_gm=0.45)
    assert all(g.values())


def test_gates_mcap_bounds():
    # 2x math: $0.5B fails the floor, $50B/$300B pass, $800B fails —
    # AMD ($330B) and PLTR ($400B) both doubled inside this band
    g = _gates(_m(rev=.5, streak=3, gm=.5, mcap=0.5e9), .4)
    assert g["mcap $1-500B"] is False
    for mc in (50e9, 300e9):
        assert _gates(_m(rev=.5, streak=3, gm=.5, mcap=mc), .4)[
            "mcap $1-500B"] is True
    assert _gates(_m(rev=.5, streak=3, gm=.5, mcap=800e9), .4)[
        "mcap $1-500B"] is False


# --- milestones ------------------------------------------------------------

def _cl(milestones=None, ai=None):
    return {"milestones": milestones or [], "ai_rev_pct": ai}


def test_milestones_typed_eval():
    cl = _cl(milestones=[
        {"metric": "gross_margin", "op": ">", "target": 0.52,
         "label": "GM mid-50s"},
        {"metric": "rev_growth", "op": ">", "target": 0.30,
         "label": "rev >30%"},
        "DC rev >25% of sales",                     # prose → skipped
    ], ai=17)
    metrics = _milestone_metrics(
        _m(rev=0.275, gm=0.485, fcf_margin=0.05), cl)
    res = _check_milestones(cl, metrics)
    assert res == {"GM mid-50s": False, "rev >30%": False}


def test_milestones_segment_and_ai_metrics():
    m = _m(rev=0.2, gm=0.5,
           segments={"Power ICs": {"share": 0.4, "yoy": 0.40},
                     "Sensors": {"share": 0.6, "yoy": 0.1}})
    cl = _cl(milestones=[
        {"metric": "segment_growth:power ics", "op": ">", "target": 0.25},
        {"metric": "segment_share:sensors", "op": ">", "target": 0.5},
        {"metric": "ai_rev_pct", "op": ">=", "target": 20},
    ], ai=17)
    res = _check_milestones(cl, _milestone_metrics(m, cl))
    assert list(res.values()) == [True, True, False]


def test_milestones_unknown_metric_is_none():
    cl = _cl(milestones=[{"metric": "bogus", "op": ">", "target": 1}])
    assert list(_check_milestones(cl, {}).values()) == [None]


# --- grade direction / rating action ---------------------------------------

def test_jefferies_case_upgrade_not_downgrade():
    # the real bug: FMP labeled Underperform→Hold as 'downgrade'
    assert grade_direction("Underperform", "Hold") == "upgrade"
    assert rating_action("", "analyst_action", "downgrade",
                         "NEGATIVE", "Underperform", "Hold") == "upgrade"


def test_genuine_downgrade_survives():
    assert rating_action("", "analyst_action", "downgrade",
                         "NEGATIVE", "Buy", "Reduce") == "downgrade"


def test_vague_action_ranked():
    # FMP 'initialise' on an Equal-Weight→Overweight transition
    assert rating_action("", "analyst_action", "initialise",
                         "NEUTRAL", "Equal-Weight", "Overweight") == "upgrade"


def test_headline_fallback():
    assert rating_action("Nebius gets BofA boost amid AI demand",
                         "catalyst") == "upgrade"
    assert rating_action("Stock gets a boost from earnings beat",
                         "catalyst") is None  # 'a boost' ≠ firm boost


# --- analyst tape ----------------------------------------------------------

def test_grade_row_corrects_feed_action():
    row = _grade_row({"action": "downgrade", "gradingCompany": "Jefferies",
                      "previousGrade": "Underperform", "newGrade": "Hold"})
    assert row["action"] == "upgrade"


def test_firm_key_normalizes_vendor_variants():
    assert _firm_key("Exane BNP Paribas") == _firm_key("BNP Paribas")
    assert _firm_key("JPMorgan Securities LLC") == _firm_key("JPMorgan")


# --- daily edge scoring ----------------------------------------------------

def _ev(kind="pt_repricing", direction="POSITIVE", hours=10, etype=None):
    return {"event_type": etype or kind,
            "direction": direction,
            "title": "", "detail": {"action": kind,
                                    "kind": kind},
            "created_at": datetime.now(timezone.utc)
            - timedelta(hours=hours)}


def test_catalyst_recency_decay():
    fresh = _catalyst_pts([_ev(hours=10)], {})[0]
    stale = _catalyst_pts([_ev(hours=36)], {})[0]
    assert fresh > stale > 0
    assert stale == pytest.approx(fresh * 0.6, abs=1)


def test_veto_fresh_downgrade_and_knife():
    assert de._vetoes("X", {}, [_ev("downgrade", "NEGATIVE", 5,
                                    etype="analyst_action")])
    assert de._vetoes("X", {"falling_knife": True}, [])
    # a downgrade older than the window doesn't veto
    assert not de._vetoes("X", {}, [_ev("downgrade", "NEGATIVE", 60,
                                        etype="analyst_action")])


def test_setup_pts_breakout_retest_best():
    assert de._setup_pts({"detected_patterns": ["breakout_retest"]})[0] == 35
    assert de._setup_pts({"detected_patterns": []})[0] == 0
    assert de._setup_pts({"bb_squeeze": True})[0] == 15


# --- ops table -------------------------------------------------------------

def test_ops_table():
    assert _OPS[">"](0.5, 0.4) and _OPS["<="](0.4, 0.5)
    assert _OPS["=="](1.0, 1.0)
