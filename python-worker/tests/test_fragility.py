from app.market_regime.fragility import (
    _assemble, _resolution, _trigger_probs, score_bottom_structure,
    score_credit_funding, score_discharge, score_market_structure,
    score_positioning, score_trigger_proximity,
    score_vol_compression, score_vol_control_pressure)


def test_trigger_proximity_sitting_on_sma50_is_fragile():
    out = score_trigger_proximity(
        {"SPY": {"d20": -0.5, "d50": 0.4, "d200": 4.0,
                 "days_below_50": 0}})
    assert out["score"] >= 70
    assert out["status"] == "observed"


def test_trigger_proximity_far_from_triggers_is_calm():
    out = score_trigger_proximity(
        {"SPY": {"d20": 2.0, "d50": 6.0, "d200": 12.0,
                 "days_below_50": 0}})
    assert out["score"] <= 15


def test_trigger_proximity_broken_50_fires():
    out = score_trigger_proximity(
        {"SPY": {"d20": -1.0, "d50": -0.8, "d200": 2.0,
                 "days_below_50": 3}})
    assert out["score"] >= 85


def test_trigger_proximity_missing_is_missing_not_zero():
    out = score_trigger_proximity({})
    assert out["score"] is None
    assert out["status"] == "missing"


def test_vol_compression_low_vol_near_highs_scores_high():
    out = score_vol_compression(
        rvol20=8.0, rvol_pctile=10.0, vix=13.0,
        vix_pctile=15.0, dd52=-1.5)
    assert out["score"] >= 75


def test_vol_compression_low_vol_off_highs_dampened():
    near = score_vol_compression(8.0, 10.0, 13.0, 15.0, -1.5)
    deep = score_vol_compression(8.0, 10.0, 13.0, 15.0, -15.0)
    assert deep["score"] < near["score"]


def test_vol_control_low_rvol_means_over_allocated():
    out = score_vol_control_pressure(rvol20=6.0, rvol5=None)
    assert out["status"] == "estimated"
    assert out["signals"]["est_exposure_multiple"] > 1.5
    assert out["score"] >= 60


def test_vol_control_spike_trips_deleveraging():
    out = score_vol_control_pressure(rvol20=14.0, rvol5=25.0)
    assert out["signals"]["deleveraging_firing"] is True
    assert out["score"] >= 85


def test_market_structure_backwardation_plus_vvix_scores():
    out = score_market_structure(
        vix=22.0, vix_term_ratio=0.94, vvix=125.0,
        skew=150.0, skew_pctile=92.0, pc={})
    assert out["status"] == "estimated"
    assert out["score"] >= 80


def test_market_structure_calm_surface_scores_low():
    out = score_market_structure(
        vix=14.0, vix_term_ratio=1.25, vvix=90.0,
        skew=115.0, skew_pctile=30.0, pc={})
    assert out["score"] <= 10


def test_market_structure_no_data_is_missing():
    out = score_market_structure(None, None, None, None, None, {})
    assert out["status"] == "missing"


def test_positioning_crowded_lev_plus_cot_scores_high():
    lev = {"lev_vol_share": 0.30, "lev_vol_share_trend": 0.05,
           "lev_aum_chg_pct": 12.0, "aum_days": 25}
    cot = {"net_pct_oi": 8.0, "pctile_1y": 90.0, "chg_4w": 0.5,
           "report_date": "2026-10-27"}
    out = score_positioning(lev, cot, {})
    assert out["status"] == "observed"
    assert out["score"] >= 70


def test_positioning_cot_deleveraging_softens_crowding():
    lev = {"lev_vol_share": 0.12}
    crowded = score_positioning(
        lev, {"net_pct_oi": 6.0, "pctile_1y": 85.0, "chg_4w": 0.5}, {})
    degross = score_positioning(
        lev, {"net_pct_oi": 6.0, "pctile_1y": 85.0, "chg_4w": -3.0}, {})
    assert degross["score"] < crowded["score"]


def test_credit_funding_reuses_classifier_state():
    out = score_credit_funding(
        {"credit_state": "stress", "hy_oas": 5.2, "hy_oas_d20": 0.6,
         "ig_oas_d20": 0.2, "confidence": "high",
         "fred_asof": "2026-11-04"},
        hyg_lqd_20d=-0.015, move=135.0)
    assert out["score"] >= 90
    assert out["status"] == "observed"


def test_credit_funding_healthy_scores_low():
    out = score_credit_funding(
        {"credit_state": "healthy", "hy_oas": 3.1}, None, 95.0)
    assert out["score"] <= 15


def test_trigger_probs_scale_by_band_and_horizon():
    calm = _trigger_probs(20, "calm", [])
    fragile = _trigger_probs(65, "fragile", [])
    assert calm["5d"] < fragile["5d"]
    assert fragile["10d"] > fragile["5d"] > fragile["3d"] > fragile["1d"]
    fired = _trigger_probs(65, "fragile", ["ma_triggers_broken",
                                          "credit_stress"])
    assert fired["5d"] > fragile["5d"]


def test_assemble_renormalizes_missing_legs():
    legs = {
        "positioning": {"score": 60, "status": "observed", "read": "",
                        "signals": {}},
        "vol_control": {"score": 60, "status": "observed", "read": "",
                        "signals": {}},
        "market_structure": {"score": None, "status": "missing",
                             "read": "", "signals": {}},
        "trigger_proximity": {"score": 60, "status": "observed",
                              "read": "", "signals": {}},
        "credit_funding": {"score": 60, "status": "observed",
                           "read": "", "signals": {}},
        "liquidity": {"score": None, "status": "missing", "read": "",
                      "signals": {}},
    }
    out = _assemble(legs, [], __import__("datetime").date.today(),
                    {"validators": {}}, [])
    assert out["vulnerability"] == 60.0
    assert "market_structure" in out["missing"]
    assert "liquidity" in out["missing"]
    # 75 of 100 weight observed → medium confidence
    assert out["confidence"] == "medium"
    assert out["coverage_pct"] == 75.0


def test_assemble_all_estimated_caps_confidence():
    legs = {k: {"score": 50, "status": "estimated", "read": "",
                "signals": {}}
            for k in ("positioning", "vol_control",
                      "market_structure", "trigger_proximity",
                      "credit_funding", "liquidity")}
    out = _assemble(legs, [], __import__("datetime").date.today(),
                    {"validators": {}}, [])
    assert out["coverage_pct"] == 0.0
    assert out["confidence"] == "low"


# ---------- resolution: discharge + bottom + phase ----------

def test_discharge_leverage_visibly_leaving_scores_high():
    out = score_discharge(
        {"lev_aum_chg_pct": -12.0, "lev_vol_share_trend": -0.06},
        {"chg_4w": -2.5},
        {"deleveraging_firing": True, "rvol20": 22.0},
        vix=32.0, vix_chg5=-4.0, credit_state="healthy")
    assert out["score"] >= 80


def test_discharge_still_adding_scores_low():
    out = score_discharge(
        {"lev_aum_chg_pct": 9.0},
        {"chg_4w": 3.0},
        {"deleveraging_firing": False, "rvol20": 8.0},
        vix=14.0, vix_chg5=6.0, credit_state="severe")
    assert out["score"] <= 20


def test_bottom_structure_full_checklist_scores_high():
    cell = {"higher_low": True, "new_lows_5d": 0,
            "above_avwap": True, "bounce_vol_ratio": 1.4}
    out = score_bottom_structure(
        {"SPY": cell, "QQQ": cell, "SMH": cell}, smh_rs20=0.01)
    assert out["score"] >= 95


def test_bottom_structure_still_making_lows_scores_low():
    cell = {"higher_low": False, "new_lows_5d": 4,
            "above_avwap": False, "bounce_vol_ratio": 0.8}
    out = score_bottom_structure(
        {"SPY": cell, "QQQ": cell, "SMH": cell}, smh_rs20=-0.12)
    assert out["score"] <= 10


def test_resolution_recovering_needs_flush_and_structure():
    out = _resolution(70, ["ma_triggers_broken"],
                      {"score": 60, "signals": {}},
                      {"score": 65, "signals": {}}, dd52=-9.0)
    assert out["phase"] == "recovering"


def test_resolution_discharging_when_flushing_no_bottom():
    out = _resolution(70, ["vol_control_deleveraging",
                           "term_structure_inverted"],
                      {"score": 55, "signals": {}},
                      {"score": 10, "signals": {}}, dd52=-12.0)
    assert out["phase"] == "discharging"


def test_resolution_building_before_anything_trips():
    out = _resolution(55, [],
                      {"score": 10, "signals": {}},
                      {"score": 5, "signals": {}}, dd52=-2.0)
    assert out["phase"] == "building"


def test_resolution_stabilizing_on_bottom_evidence():
    out = _resolution(60, ["ma_triggers_broken"],
                      {"score": 25, "signals": {}},
                      {"score": 48, "signals": {}}, dd52=-8.0)
    assert out["phase"] == "stabilizing"
