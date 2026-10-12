"""Focused tests for pulse_engine.rank — the continuous ordering
layer that ranks candidates INSIDE each use-case's ready set.

Contracts under test:
  - missing inputs drop the component and weights renormalize —
    never score zero
  - invalid FV drops the value leg (same contract as fv_unusable)
  - negative YAML weights are flat penalties, not components
  - first matching cap clamps the score
  - parts records raw/norm/w per component
  - rank never promotes a non-ready state — the gate stays
    sovereign (rank is order, not permission)
"""
from __future__ import annotations

from app.signals.pulse_engine import (_normalize, _stage0, rank,
                                       rules_version)


def _ctx(**kw):
    """Normalized rank ctx — a clean baseline row, override via kw."""
    base = {
        "mom_state": "pullback", "tape_dir": "flat",
        "fund_state": "growing", "revision_grade": "B",
        "priced_status": "partial", "fv_upside": 20.0,
        "emerging_growth": None, "earn_days": 40,
        "rsi": 52.0, "vs_sma50": 0.02, "px": 100.0,
        "is_etf": False, "sector": "technology",
        "gq_pct": 80.0, "beat_streak": 3,
        "est_revision_pct": 0.05, "sector_score": 70.0,
        "momentum_detail": {
            "rs_pct": 80.0, "vol_dip": 0.8, "atr_pct": 0.03,
            "dip_phase": "confirmed", "pct_b": 0.4,
            "swing": {"swing_low": 95.0, "hl_seq": True},
        },
    }
    det = kw.pop("momentum_detail", None)
    if det:
        base["momentum_detail"].update(det)
    base.update(kw)
    c = _normalize(base)
    c.update(_stage0(c))
    return c


# ---------- ordering -----------------------------------------------------

def test_higher_rs_outranks_swing():
    hi = rank("swing", _ctx(momentum_detail={"rs_pct": 90.0}))
    lo = rank("swing", _ctx(momentum_detail={"rs_pct": 40.0}))
    assert hi["rank"] > lo["rank"]


def test_confirmed_dip_beats_still_falling():
    conf = rank("swing", _ctx())
    fall = rank("swing", _ctx(momentum_detail={"dip_phase":
                                             "still_falling"}))
    assert conf["rank"] > fall["rank"]


def test_rank_bounded():
    for uc in ("swing", "invest", "leap_call"):
        r = rank(uc, _ctx())
        assert 0 <= r["rank"] <= 100


# ---------- missing-data contract ----------------------------------------

def test_missing_rs_drops_component_not_score():
    full = rank("swing", _ctx())
    no_rs = rank("swing", _ctx(
        momentum_detail={"rs_pct": None}))
    # rs_pct leaves parts entirely — it must not appear as a zero
    assert "rs_pct" not in no_rs["parts"]
    # score stays in range, renormalized over remaining weight
    assert 0 <= no_rs["rank"] <= 100


def test_all_missing_components_scores_zero_cleanly():
    r = rank("swing", _ctx(
        sector_score=None, earn_days=None, tape_dir=None,
        momentum_detail={"rs_pct": None, "vol_dip": None,
                         "atr_pct": None, "dip_phase": None,
                         "swing": {}}, px=None))
    assert r["rank"] == 0.0
    assert r["parts"] == {}


def test_invalid_fv_drops_value_leg():
    # |fv| > 75 → fv_valid false → component absent (not zero)
    r = rank("invest", _ctx(fv_upside=95.0))
    assert "fv_upside" not in r["parts"]
    good = rank("invest", _ctx(fv_upside=30.0))
    assert "fv_upside" in good["parts"]


# ---------- penalties and caps --------------------------------------------

def test_earnings_penalty_flat():
    far = rank("swing", _ctx(earn_days=40))
    near = rank("swing", _ctx(earn_days=3))
    assert abs(far["rank"] - near["rank"] - 15) < 0.5
    assert near["parts"]["earn_risk"]["penalty"] == 15


def test_hard_fund_bad_caps_swing():
    r = rank("swing", _ctx(fund_state="deteriorating"))
    assert r["rank"] <= 40
    assert "_cap" in r["parts"]


# ---------- parts journal --------------------------------------------------

def test_parts_records_raw_norm_weight():
    r = rank("swing", _ctx())
    p = r["parts"]["rs_pct"]
    assert p["raw"] == 80.0 and p["norm"] == 80.0 and p["w"] == 25


def test_rank_versioned_with_rules():
    # rank weights live in the same YAML — provenance travels with
    # the existing rules_version stamp on readiness_evals
    assert rules_version()


# ---------- leap_put stays score-driven -----------------------------------

def test_leap_put_not_ranked_by_this_engine():
    # leap_put has no rank_weights section — rank() returns a clean
    # zero instead of fabricating a composite; board() maps its
    # put_entry.score() into the rank slot instead
    r = rank("leap_put", _ctx())
    assert r["rank"] == 0.0


# ---------- use-case weighting differences --------------------------------

def test_invest_weights_quality_over_timing():
    # great tape, poor fundamentals → swing > invest for the same ctx
    c = _ctx(gq_pct=20.0, revision_grade="D",
             momentum_detail={"rs_pct": 95.0})
    sw, inv = rank("swing", c), rank("invest", c)
    assert sw["rank"] > inv["rank"]


def test_leap_call_requires_trend():
    strong = rank("leap_call", _ctx(vs_sma50=0.05))
    broken = rank("leap_call", _ctx(vs_sma50=-0.05))
    assert strong["rank"] > broken["rank"]
