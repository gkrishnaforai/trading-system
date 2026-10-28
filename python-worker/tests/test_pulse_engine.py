"""Golden cases for pulse_engine — every acceptance test in
pulse_action_rules.yaml. Run: pytest tests/test_pulse_engine.py"""
from __future__ import annotations

import math

from app.signals.pulse_engine import evaluate


def _row(**kw):
    """A clean hold-baseline row — constructive everything, cheap,
    good fund, B revisions, earnings far out."""
    base = {
        "mom_state": "uptrend", "tape_dir": "flat",
        "fund_state": "growing", "revision_grade": "B",
        "priced_status": "partial", "fv_upside": 20.0,
        "rsi": 52.0, "vs_sma50": 0.02, "earn_days": 40,
        "num_analysts": 15, "flywheel_age_days": 1,
        "momentum_age_days": 0, "gq_flags": [], "is_etf": False,
        "momentum_detail": {"pct_b": 0.5}, "sector": "technology",
    }
    base.update(kw)
    return base


# ---------- reduce ------------------------------------------------------

def test_both_legs_failing():
    r = evaluate(_row(mom_state="downtrend", fund_state="deteriorating"))
    assert r["action"] == "reduce"
    assert r["matched_rule"] == "both_legs_failing"


def test_broken_rev_cutting():
    r = evaluate(_row(mom_state="downtrend", fund_state="growing",
                      revision_grade="D"))
    assert r["action"] == "reduce"
    assert r["matched_rule"] == "broken_rev_cutting"


def test_broken_no_support_valid_fv():
    r = evaluate(_row(mom_state="downtrend", fund_state="cyclical",
                      revision_grade="C-", fv_upside=-20.0))
    assert r["action"] == "reduce"
    assert r["matched_rule"] == "broken_no_support"
    assert r["confidence"] == "high"


def test_broken_no_support_missing_fv_low_conf():
    r = evaluate(_row(mom_state="knife", fund_state="watch",
                      revision_grade="C", fv_upside=None))
    assert r["action"] == "reduce"
    assert r["confidence"] == "low"


def test_rev_missing_qualifies_no_support():
    # missing revision = no upgrade evidence → rule still applies
    r = evaluate(_row(mom_state="breakdown", fund_state="cyclical",
                      revision_grade=None, fv_upside=None))
    assert r["action"] == "reduce"


def test_rev_A_rescues_broken_cyclical():
    # WDC pattern — cycle_turn watch, never reduce
    r = evaluate(_row(mom_state="capitulation", fund_state="cyclical",
                      revision_grade="A+", fv_upside=-84.0))
    assert r["action"] == "watch"
    assert r["label"] == "cycle_turn"


def test_broken_unknown_fund_is_review_not_reduce():
    r = evaluate(_row(mom_state="downtrend", fund_state=None,
                      fv_upside=None))
    assert r["action"] == "watch"
    assert r["label"] == "review"


def test_deteriorating_first_crack():
    r = evaluate(_row(mom_state="rolling_over",
                      fund_state="deteriorating", rsi=55.0,
                      vs_sma50=0.05))
    assert r["action"] == "reduce"


# ---------- trim ---------------------------------------------------------

def test_climax_corroborated():
    r = evaluate(_row(mom_state="climax", rsi=72.0, vs_sma50=0.18))
    assert r["action"] == "trim"


def test_climax_uncorroborated_is_watch():
    r = evaluate(_row(mom_state="climax", rsi=59.0, vs_sma50=0.01))
    assert r["action"] in ("watch", "hold")
    assert r["action"] != "trim"


def test_rolling_over_extended():
    r = evaluate(_row(mom_state="rolling_over", fund_state="cyclical",
                      rsi=57.0, vs_sma50=0.15))
    assert r["action"] == "trim"


def test_downtrend_rsi78_never_trims():
    # the v1 contradiction — extension on broken tape is an artifact
    r = evaluate(_row(mom_state="downtrend", fund_state="growing",
                      rsi=78.0, vs_sma50=0.25, fv_upside=45.0))
    assert r["action"] != "trim"


def test_trend_stretch_needs_both_legs():
    # RSI 71 but only +8% vs50 → not a trim
    r = evaluate(_row(mom_state="uptrend", rsi=71.0, vs_sma50=0.08))
    assert r["action"] != "trim"
    # both legs → trim
    r = evaluate(_row(mom_state="uptrend", rsi=71.0, vs_sma50=0.16))
    assert r["action"] == "trim"


def test_sell_strength():
    r = evaluate(_row(mom_state="uptrend", fund_state="deteriorating",
                      rsi=55.0, vs_sma50=0.08))
    assert r["action"] == "trim"
    assert r["matched_rule"] == "sell_strength"


def test_broken_premium_needs_corroboration():
    # priced corroborates rich → reduce (HOOD/FIG class)
    r = evaluate(_row(mom_state="knife", fund_state="accelerating",
                      revision_grade="A", fv_upside=-42.0,
                      priced_status="full"))
    assert r["action"] == "reduce"
    assert r["matched_rule"] == "broken_premium_valid_fv"
    # unclassified priced — single valid FV signal still reduces
    r = evaluate(_row(mom_state="downtrend", fund_state="growing",
                      fv_upside=-42.0, priced_status=None))
    assert r["action"] == "reduce"


def test_valuation_models_disagree_is_attention():
    # the ALGM case — FV says -41% rich, LT curve says partial:
    # disagreement is a warning, not a conviction
    r = evaluate(_row(mom_state="downtrend", fund_state="growing",
                      revision_grade="B", fv_upside=-40.5,
                      priced_status="partial"))
    assert r["action"] == "watch"
    assert r["label"] == "valuation_risk"


# ---------- watch --------------------------------------------------------

def test_accumulation_needs_valid_fv():
    # good fund + broken tape + cheap → accumulation watch
    r = evaluate(_row(mom_state="knife", fund_state="accelerating",
                      fv_upside=30.0, revision_grade="A-"))
    assert r["action"] == "watch" and r["label"] == "accumulation"
    # suspect fv can't qualify as cheap
    r = evaluate(_row(mom_state="knife", fund_state="accelerating",
                      fv_upside=150.0))
    assert r["label"] != "accumulation"


def test_cooling():
    r = evaluate(_row(mom_state="uptrend", fund_state="slowing",
                      rsi=50.0, vs_sma50=0.02))
    assert r["action"] == "watch" and r["label"] == "cooling"


def test_turnaround_watch():
    r = evaluate(_row(mom_state="knife", fund_state="turnaround",
                      fv_upside=None))
    assert r["action"] == "watch" and r["label"] == "turnaround"


# ---------- add & the gate ------------------------------------------------

def test_add_growth_clean():
    r = evaluate(_row(mom_state="pullback", fv_upside=18.0,
                      priced_status="not_priced"))
    assert r["action"] == "add"
    assert r["matched_rule"] == "add_growth"


def test_add_blocked_missing_earnings():
    r = evaluate(_row(mom_state="pullback", fv_upside=18.0,
                      priced_status="not_priced", earn_days=None))
    assert r["action"] == "watch" and r["label"] == "add_blocked"


def test_add_earn_boundary():
    assert evaluate(_row(mom_state="pullback", fv_upside=18.0,
                         priced_status="not_priced",
                         earn_days=7))["action"] == "watch"
    assert evaluate(_row(mom_state="pullback", fv_upside=18.0,
                         priced_status="not_priced",
                         earn_days=8))["action"] == "add"


def test_add_blocked_fcf_negative():
    # risk_review (watch) precedes add_growth — either it or the gate
    # must stop the add; both are correct first-match behavior
    r = evaluate(_row(mom_state="pullback", fv_upside=18.0,
                      priced_status="not_priced",
                      gq_flags=["fcf_negative"]))
    assert r["action"] == "watch" and r["label"] in ("add_blocked",
                                                   "review")


def test_add_blocked_fully_priced():
    # priced=full trips the fully-priced watch rule before add_growth;
    # gate is a second line of defense either way
    r = evaluate(_row(mom_state="pullback", fv_upside=18.0,
                      priced_status="full"))
    assert r["action"] == "watch"


def test_add_rev_D_never():
    r = evaluate(_row(mom_state="pullback", fv_upside=18.0,
                      priced_status="not_priced", revision_grade="D"))
    assert r["action"] != "add"


def test_add_underfollowed_exception():
    # thin coverage + no grade + deeper FV → allowed (confidence note)
    r = evaluate(_row(mom_state="pullback", fv_upside=20.0,
                      priced_status="not_priced", revision_grade=None,
                      num_analysts=2))
    assert r["action"] == "add"
    # …but shallow FV without coverage evidence is not enough
    r = evaluate(_row(mom_state="pullback", fv_upside=8.0,
                      priced_status="not_priced", revision_grade=None,
                      num_analysts=2))
    assert r["action"] != "add"


def test_add_value_recovery():
    r = evaluate(_row(mom_state="recovery", fund_state="turnaround",
                      fv_upside=18.0, revision_grade="C+",
                      priced_status="not_priced"))
    assert r["action"] == "add" and r["label"] == "recovery"
    # D revisions kill it
    r = evaluate(_row(mom_state="recovery", fund_state="turnaround",
                      fv_upside=18.0, revision_grade="F",
                      priced_status="not_priced"))
    assert r["action"] != "add"


def test_add_gate_never_overrides_reduce():
    # a reduce match must stay reduce even if gate inputs are bad
    r = evaluate(_row(mom_state="downtrend", fund_state="deteriorating",
                      earn_days=None))
    assert r["action"] == "reduce"


# ---------- fv_valid precedence -------------------------------------------

def test_fv_boundaries_and_junk():
    assert evaluate(_row(fv_upside=75.0))["stage0"]["fv_valid"] is True
    assert evaluate(_row(fv_upside=-75.0))["stage0"]["fv_valid"] is True
    assert evaluate(_row(fv_upside=75.01))["stage0"]["fv_valid"] is False
    assert evaluate(_row(fv_upside=-75.01))["stage0"]["fv_valid"] is False
    for junk in (None, float("nan"), float("inf"), -float("inf"),
                 "abc"):
        r = evaluate(_row(fv_upside=junk))
        assert r["stage0"]["fv_valid"] is False


# ---------- ETFs -----------------------------------------------------------

def test_etf_never_equity_rules():
    r = evaluate(_row(mom_state="downtrend", fund_state=None,
                      is_etf=True, fv_upside=None))
    assert r["matched_rule"] == "etf_broken"
    assert r["action"] == "reduce"


def test_etf_missing_tape_is_review():
    r = evaluate(_row(mom_state=None, is_etf=True))
    assert r["action"] == "watch" and r["label"] == "review"


def test_etf_hold_default():
    r = evaluate(_row(is_etf=True))
    assert r["matched_rule"] == "etf_hold"


# ---------- staleness boundaries -------------------------------------------

def test_stale_boundaries():
    # 21d = not stale (gt), 22 = stale → blocks add
    r = evaluate(_row(mom_state="pullback", fv_upside=18.0,
                      priced_status="not_priced", flywheel_age_days=21))
    assert r["action"] == "add"
    r = evaluate(_row(mom_state="pullback", fv_upside=18.0,
                      priced_status="not_priced", flywheel_age_days=22))
    assert r["action"] == "watch" and r["label"] == "add_blocked"


# ---------- unclassifiable inputs ---------------------------------------------

def test_missing_tape_is_review_not_hold():
    r = evaluate(_row(mom_state=None, fund_state="growing",
                      fv_upside=30.0, revision_grade="A"))
    assert r["action"] == "watch" and r["label"] == "review"
    assert r["matched_rule"] == "unclassifiable_inputs_review"


def test_missing_fund_constructive_tape_is_review():
    # uptrend + null fund must not silently hold
    r = evaluate(_row(fund_state=None))
    assert r["action"] == "watch" and r["label"] == "review"


def test_review_outranks_degraded_leg():
    # tape null + fund slowing → review, not degraded_leg's
    # partial-input inference
    r = evaluate(_row(mom_state=None, fund_state="slowing"))
    assert r["matched_rule"] == "unclassifiable_inputs_review"
    assert r["label"] == "review"


def test_unresolved_instrument_never_equity():
    # is_etf null → unknown_policy review — even with perfect
    # add-shaped inputs it can never reach a stock-level action
    r = evaluate(_row(mom_state="pullback", fv_upside=30.0,
                      priced_status="not_priced", is_etf=None))
    assert r["stage0"]["instrument"] == "unknown"
    assert r["action"] == "watch" and r["label"] == "review"
    assert r["matched_rule"] == "instrument_unclassifiable"


# ---------- dq_block contract --------------------------------------------------

def test_dq_caps_confidence_never_vetoes_reduce():
    # stale fundamentals + both legs failing → still reduce, conf low
    r = evaluate(_row(mom_state="downtrend", fund_state="deteriorating",
                      flywheel_age_days=30))
    assert r["action"] == "reduce"
    assert r["confidence"] == "low"
    assert "stale_fundamentals" in r["annotations"]["blocking"]


# ---------- revision-grade normalization ---------------------------------------

def test_malformed_rev_grade_is_not_missing():
    r = evaluate(_row(revision_grade="garbage"))
    assert r["stage0"]["rev_class"] == "malformed"
    assert "malformed_revision_grade" in r["annotations"]["confidence"]
    # missing-tokens normalize to missing, not malformed
    for tok in ("N/A", "n/a", "-", "", None):
        assert evaluate(_row(revision_grade=tok)
                        )["stage0"]["rev_class"] == "missing"
    # whitespace/case normalize — " a+ " is a real grade
    assert evaluate(_row(revision_grade=" a+ ")
                    )["stage0"]["rev_class"] == "A"
    # malformed satisfies no rev_class_in / rev_class condition
    r2 = evaluate(_row(mom_state="downtrend", fund_state="cyclical",
                       revision_grade="garbage", fv_upside=None))
    # falls through broken_no_support (malformed ∉ B,C,D,missing)
    assert r2["matched_rule"] != "broken_no_support"


# ---------- risk-flag 4-state --------------------------------------------------

def test_risk_flag_states_and_sector_exempt(monkeypatch):
    import copy
    import app.signals.pulse_engine as pe
    spec = copy.deepcopy(pe._load())
    spec["annotations"]["risk_flags"]["fcf_negative"][
        "sector_exempt"] = ["financials"]
    monkeypatch.setattr(pe, "_spec", spec)
    # exempt sector → not_applicable, can't block an add
    r = evaluate(_row(mom_state="pullback", fv_upside=18.0,
                      priced_status="not_priced", sector="financials",
                      gq_flags=["fcf_negative"]))
    assert r["annotations"]["risk_flags"]["fcf_negative"] == \
        "not_applicable"
    assert r["action"] == "add"
    # non-exempt, flag present → true → blocks
    r = evaluate(_row(mom_state="pullback", fv_upside=18.0,
                      priced_status="not_priced", sector="tech",
                      gq_flags=["fcf_negative"]))
    assert r["annotations"]["risk_flags"]["fcf_negative"] is True
    assert r["action"] == "watch"
    # flag absent with populated source → false
    r = evaluate(_row(gq_flags=["other_flag"]))
    assert r["annotations"]["risk_flags"]["fcf_negative"] is False
    # source missing → unknown → blocks add
    r = evaluate(_row(mom_state="pullback", fv_upside=18.0,
                      priced_status="not_priced", gq_flags=None))
    assert r["annotations"]["risk_flags"]["fcf_negative"] == "unknown"
    assert r["action"] == "watch" and r["label"] == "add_blocked"


def test_pending_flags_never_block_or_activate():
    # dilution/leverage are pending_calibration → journaled 'pending',
    # exempt from the gate, can never produce true/hard_risk
    r = evaluate(_row(mom_state="pullback", fv_upside=18.0,
                      priced_status="not_priced"))
    assert r["annotations"]["risk_flags"]["dilution_severe"] == \
        "pending"
    assert r["annotations"]["risk_flags"]["leverage_critical"] == \
        "pending"
    assert r["annotations"]["hard_risk_active"] is False
    assert r["action"] == "add"
    assert "dilution_severe" in r["annotations"]["risk_pending"]


def test_pending_flag_sector_exempt_is_not_applicable():
    # REIT + pending leverage → not_applicable (exempt beats pending)
    r = evaluate(_row(sector="real estate"))
    assert r["annotations"]["risk_flags"]["leverage_critical"] == \
        "not_applicable"


# ---------- boundary isolation --------------------------------------------------

def test_rsi75_boundary_isolated():
    # exactly 75 on uptrend trims via gte; 74.9 with small vs50 doesn't
    assert evaluate(_row(mom_state="uptrend", rsi=75.0,
                         vs_sma50=0.02))["action"] == "trim"
    assert evaluate(_row(mom_state="uptrend", rsi=74.9,
                         vs_sma50=0.02))["action"] != "trim"
    # vs50 0.30 boundary trims alone (gt is strict — 0.30 fails, 0.31 passes)
    assert evaluate(_row(mom_state="uptrend", rsi=50.0,
                         vs_sma50=0.30))["action"] != "trim"
    assert evaluate(_row(mom_state="uptrend", rsi=50.0,
                         vs_sma50=0.31))["action"] == "trim"


# ---------- turnaround gap -------------------------------------------------------

def test_turnaround_climax_is_not_hold():
    r = evaluate(_row(mom_state="climax", fund_state="turnaround",
                      rsi=55.0, vs_sma50=0.05))
    assert r["action"] == "watch" and r["label"] == "turnaround"


# ---------- add-gate termination --------------------------------------------------

def test_gate_fail_terminates_not_second_rule():
    # add_growth matches, gate fails → watch/add_blocked with
    # matched_rule preserved; never falls to hold or a later rule
    r = evaluate(_row(mom_state="pullback", fv_upside=18.0,
                      priced_status="not_priced", earn_days=3))
    assert r["action"] == "watch"
    assert r["label"] == "add_blocked"
    assert r["matched_rule"] == "add_growth"
    assert r["gate_results"]["earn_days_gt"] == "fail"


# ---------- determinism / journal -------------------------------------------

def test_replay_determinism():
    row = _row(mom_state="rolling_over", vs_sma50=0.15)
    a, b = evaluate(row), evaluate(dict(row))
    assert a["action"] == b["action"]
    assert a["matched_rule"] == b["matched_rule"]


def test_journal_shape():
    r = evaluate(_row(mom_state="downtrend", fund_state="cyclical",
                      fv_upside=None))
    for k in ("matched_rule", "condition_log", "input_snapshot",
              "rules_version", "engine_version", "annotations"):
        assert k in r
    assert isinstance(r["condition_log"], list) and r["condition_log"]


# ---------- dip_phase rescue -------------------------------------------------

def _repair_row(**kw):
    """Broken tape mid-repair — dip_phase confirmed inside detail."""
    kw.setdefault("momentum_detail",
                  {"pct_b": 0.1, "rsi": 30.0, "vs_sma50": -0.12,
                   "dip_phase": "confirmed",
                   "swing": {"phase": "base"}})
    kw.setdefault("fv_upside", -10.0)
    return _row(mom_state="downtrend", **kw)


def test_confirmed_repair_b_revisions_stalks():
    r = evaluate(_repair_row(fund_state="watch", revision_grade="B+"))
    assert r["action"] == "watch"
    assert r["label"] == "base_repair"
    assert r["matched_rule"] == "base_repairing"


def test_confirmed_repair_c_still_reduces():
    # street still cutting — repair evidence can't rescue a C/D grade
    r = evaluate(_repair_row(fund_state="watch", revision_grade="C"))
    assert r["action"] == "reduce"


def test_missing_dip_phase_never_rescues():
    # dip_phase unknown ≠ repair evidence — reduce fires as before
    r = evaluate(_row(mom_state="downtrend", fund_state="watch",
                      revision_grade="B", fv_upside=-10.0,
                      momentum_detail={"pct_b": 0.1, "rsi": 30.0}))
    assert r["action"] == "reduce"
    assert r["matched_rule"] == "broken_no_support"


# ---------- shared use-case readiness (Stock page) ----------------------------

from app.signals.pulse_engine import eval_use_case


def _asts_like(**kw):
    """ASTS profile — breakdown tape, still-falling dip, cyclical fund,
    A- revisions, suspect FV (-98.7% is an artifact, not evidence)."""
    base = {"mom_state": "breakdown", "fund_state": "cyclical",
            "revision_grade": "A-", "fv_upside": -98.7,
            "momentum_detail": {"rsi": 28.0, "pct_b": 0.05,
                                "vs_sma50": -0.19, "hist_dir": -0.8,
                                "dip_phase": "still_falling",
                                "swing": {"phase": "falling"}},
            "rev_growth": -0.05, "eps_growth": -0.2,
            "future_score": 40, "lane": "watch",
            "gq_score": 42, "structural_proof": 55}
    base.update(kw)
    return base


def test_swing_checklist_asts():
    r = eval_use_case(_asts_like(), "swing")
    assert r["state"] == "no" and r["of"] == 5
    oks = [x["ok"] for x in r["rules"]]
    # fails constructive / above-50dma / hist-dir; passes stretch +
    # structure-mapped — same verdict the old inline checklist gave
    assert oks == [False, False, True, False, True]


def test_invest_suspect_fv_is_unavailable_not_fail():
    # the core fix — fv=-98.7 is outside the ±75 validity band, so the
    # valuation check PASSES as 'unavailable' rather than failing
    r = eval_use_case(_asts_like(), "invest")
    fv_rule = r["rules"][3]
    assert fv_rule["ok"] is True
    # ...but a *valid* -30% FV still fails the check
    r2 = eval_use_case(_asts_like(fv_upside=-30.0), "invest")
    assert r2["rules"][3]["ok"] is False


def test_leap_call_no_when_tape_broken():
    r = eval_use_case(_asts_like(), "leap_call")
    assert r["state"] == "no"
    assert r["rules"][0]["ok"] is False   # trend gate
    assert r["rules"][4]["ok"] is True    # IV line always informative


def test_use_case_ready_when_all_pass():
    r = eval_use_case(_row(
        momentum_detail={"pct_b": 0.5, "rsi": 52.0, "vs_sma50": 0.02,
                         "hist_dir": 0.1, "dip_phase": "confirmed",
                         "swing": {"phase": "base"}},
        rev_growth=0.2, eps_growth=0.3, future_score=60,
        lane="deploy", gq_score=70), "swing")
    assert r["state"] == "ready" and r["score"] == 5
    r2 = eval_use_case(_row(
        rev_growth=0.2, eps_growth=0.3, future_score=60,
        lane="deploy", gq_score=70), "invest")
    assert r2["state"] == "ready" and r2["score"] == 6


def test_use_case_missing_data_fails_not_passes():
    # same missing-input semantics as the action rules — a checklist
    # item with no data never silently passes
    r = eval_use_case({"mom_state": None, "fund_state": None,
                       "momentum_detail": {}}, "swing")
    assert r["state"] == "no"
    assert sum(x["ok"] for x in r["rules"]) < r["of"]


def test_use_case_determinism():
    row = _asts_like()
    a = eval_use_case(row, "invest")
    b = eval_use_case(dict(row), "invest")
    assert [x["ok"] for x in a["rules"]] == [x["ok"] for x in b["rules"]]


def test_invest_climax_is_not_ready():
    # price must be ready too — euphoria tape fails the entry check
    # even when every fundamental leg is perfect (PLTR profile)
    r = eval_use_case(_row(
        mom_state="climax",
        momentum_detail={"pct_b": 1.11, "rsi": 76.0, "vs_sma50": 0.18,
                         "hist_dir": 1.14, "dip_phase": "turning_up",
                         "swing": {}},
        rev_growth=0.93, eps_growth=2.14, future_score=55,
        lane="deploy", gq_score=80, fv_upside=-80.7), "invest")
    assert r["state"] == "close" and r["score"] == 5
    assert r["rules"][2]["ok"] is False      # hostile-entry check
    assert r["rules"][3]["ok"] is True       # FV unusable, no premium corroboration


def test_invest_blind_fv_plus_priced_full_fails():
    # suspect FV escapes as 'unavailable' ONLY without corroboration —
    # priced=full says the market already knows it's expensive
    r = eval_use_case(_asts_like(priced_status="full"), "invest")
    assert r["rules"][3]["ok"] is False
    # partial / not_priced / missing still pass — models disagree or
    # can't see, which is not evidence of premium
    for ps in ("partial", "not_priced", None):
        rr = eval_use_case(_asts_like(priced_status=ps), "invest")
        assert rr["rules"][3]["ok"] is True, ps


def test_invest_valid_fv_premium_still_fails():
    # HOOD profile — valid -42% FV fails regardless of priced_status
    for ps in ("full", "partial", None):
        r = eval_use_case(_row(mom_state="knife", fv_upside=-41.8,
                               priced_status=ps), "invest")
        assert r["rules"][3]["ok"] is False, ps


# ---------- shared fv_usable policy + thesis stance coherence -----------
# The stance line must gate cheapness on the same ±75% plausibility
# band the action rules use — CLS surfaced the drift: thesis said
# 'accumulate, still cheap' on a +119% gap the rules refuse to read.

def test_fv_usable_band_and_edges():
    from app.signals.pulse_engine import fv_usable, FV_SUSPECT_BAND
    assert fv_usable(FV_SUSPECT_BAND)[0] is True      # boundary valid
    assert fv_usable(-FV_SUSPECT_BAND)[0] is True
    assert fv_usable(FV_SUSPECT_BAND + 0.1) == (False, "suspect band")
    assert fv_usable(None) == (False, "missing")
    assert fv_usable(float("nan")) == (False, "missing")
    assert fv_usable("junk") == (False, "missing")


def test_stance_rejects_suspect_fv_cheapness():
    from app.signals.thesis_health import stance_for
    s = stance_for("on_track", 119.2, "downtrend")
    assert "cheap" not in s and "Accumulate" not in s
    assert "suspect" in s and "downtrend" in s
    # symmetric — a suspect 'premium' can't claim price paid for it
    s2 = stance_for("on_track", -119.0, "pullback")
    assert "paid for it" not in s2 and "suspect" in s2


def test_stance_valid_fv_and_tape_suffix():
    from app.signals.thesis_health import stance_for
    assert stance_for("on_track", 40.0, "uptrend") == \
        "Accumulate candidate — confirmed and still cheap"
    # hostile-entry tape names the missing leg; weak tape notes it
    assert "don't chase" in stance_for("on_track", 40.0, "capitulation")
    assert "tape rolling_over" in stance_for("on_track", 40.0,
                                             "rolling_over")
    # defensive stances carry no tape clause — already defensive
    assert stance_for("broken", 119.2, "downtrend") == \
        "Avoid — thesis broken"


# ---------- Layer-B slowing severity (fund-state × decel-cause) --------
# CLS surfaced the coherence gap: `slowing` on base-effect EPS decel
# + demand strong + street raising was treated identically to real
# deterioration. The raw label is preserved; the ACTION rules read
# the cause-aware severity. Benign causes are candidates, not proof —
# hard risk overrides restore full severity.

def _slowing_row(**kw):
    base = dict(mom_state="downtrend", fund_state="slowing",
                decel_cause="base_normalization",
                demand_health="strong", est_revision_pct=0.296,
                rev_growth=0.825, gm_slope=-0.02,
                momentum_detail={"pct_b": 0.4,
                                 "dip_phase": "stabilizing"})
    base.update(kw)
    return _row(**base)


def test_benign_slowing_is_not_a_failing_leg():
    # CLS profile — severity low blocks both_legs_failing; broken tape
    # alone routes to watch, and the benign annotation surfaces why
    r = evaluate(_slowing_row())
    assert r["action"] == "watch" and r["matched_rule"] != \
        "both_legs_failing"
    assert r["stage0"]["slowing_severity"] == "low"
    assert "slowing_benign_cause" in r["annotations"]["confidence"]


def test_slow_severity_hard_overrides():
    # weak demand / estimate cuts / FCF burn / severe margin damage
    # each restore full severity even with a benign cause
    for kw in ({"demand_health": "weak"},
               {"est_revision_pct": -0.05},
               {"gq_flags": ["fcf_negative"]},
               {"gm_slope": -0.08}):
        r = evaluate(_slowing_row(**kw))
        assert r["action"] == "reduce", kw
        assert r["matched_rule"] == "both_legs_failing", kw


def test_slow_severity_context_must_corroborate():
    # benign cause alone doesn't neutralize — missing cause, weak
    # growth level, or flat revisions all keep full severity
    for kw in ({"decel_cause": None},
               {"rev_growth": 0.03},
               {"est_revision_pct": 0.0},
               {"decel_cause": "demand_deterioration"}):
        r = evaluate(_slowing_row(**kw))
        assert r["action"] == "reduce", kw


def test_slow_severity_only_modulates_slowing():
    # pressured/deteriorating carry the benign fields but are
    # unaffected — the modifier can never soften a real failing leg
    for fund in ("pressured", "deteriorating", "declining"):
        r = evaluate(_slowing_row(fund_state=fund))
        assert r["action"] == "reduce", fund
        assert r["stage0"]["slowing_severity"] == "normal", fund


# ---------- repair_eligible — shared broken-tape repair test ------------
# SNDK surfaced the inconsistency: base_repairing accepted turning_up
# while broken_no_support only deferred on confirmed — the same dip
# evidence was 'repair' in one rule and 'no support' in the other.
# One stage-0 flag now feeds both: deferred reduce ↔ stalk, never add.

def _repair_row(**kw):
    # SNDK profile — knife + turning_up + cyclical fund + B revisions
    base = dict(mom_state="knife", fund_state="cyclical",
                revision_grade="B", fv_upside=None, priced_status=None,
                momentum_detail={"pct_b": 0.2,
                                 "dip_phase": "turning_up"})
    base.update(kw)
    return _row(**base)


def test_turning_up_neutral_b_defers_to_stalk():
    # the SNDK case — reduce deferred, base_repair fires watch/stalk
    r = evaluate(_repair_row())
    assert r["action"] == "watch" and r["label"] == "base_repair"
    assert r["stage0"]["repair_eligible"] is True


def test_confirmed_repair_also_stalks():
    r = evaluate(_repair_row(momentum_detail={
        "pct_b": 0.2, "dip_phase": "confirmed"}))
    assert r["action"] == "watch" and r["label"] == "base_repair"


def test_repair_never_overrides_deterioration():
    # turning_up + soft/hard fundamental legs → reduce still fires;
    # a technical turn can't defer real deterioration
    for fund in ("pressured", "deteriorating", "slowing"):
        r = evaluate(_repair_row(
            fund_state=fund, revision_grade="C",
            decel_cause="demand_deterioration"))
        assert r["action"] == "reduce", fund
        assert r["stage0"]["repair_eligible"] is False


def test_repair_never_overrides_street_cuts():
    # C/D revisions cancel the deferral even with a confirmed dip +
    # neutral fund — the street cutting overrides the repair
    for grade in ("C", "D"):
        r = evaluate(_repair_row(revision_grade=grade,
                                 momentum_detail={
                                     "pct_b": 0.2,
                                     "dip_phase": "confirmed"}))
        assert r["action"] == "reduce", grade


def test_missing_repair_inputs_never_infer():
    # null dip / null fund → no repair; reduce path or review per
    # the surviving legs — repair is never inferred from missing data
    r = evaluate(_repair_row(momentum_detail={"pct_b": 0.2},
                             revision_grade="C"))
    assert r["action"] == "reduce"    # knife + neutral + C, no dip
    r2 = evaluate(_repair_row(fund_state=None))
    assert r2["action"] == "watch" and r2["label"] == "review"


def test_repair_eligible_never_becomes_add():
    # corroborated repair is stalk/watch — the label can never reach
    # an add action even when every other input is constructive
    r = evaluate(_repair_row(fund_state="growing",
                             revision_grade="A", fv_upside=30.0))
    assert r["action"] in ("watch", "hold")
    assert r["action"] != "add"


# ---------- trade_plan_outcomes — realized-R grading -------------------

def test_outcome_realized_r_math():
    from app.signals.trade_plans import _outcome
    from datetime import date, datetime
    o = _outcome({'id': 1, 'symbol': 'X', 'use_case': 'swing',
                  'direction': 'long', 'entry_px': 100,
                  'entry_date': date(2026, 10, 1), 'stop_px': 90,
                  'close_px': 115, 'closed_at': datetime(2026, 10, 10)},
                 ['target1_hit', 'trail_up'])
    assert o['realized_r'] == 1.5 and o['realized_pct'] == 15.0
    assert o['days_held'] == 9 and o['hit_t1'] and not o['hit_t2']
    # short direction inverts the sign — stop-out is negative R
    o2 = _outcome({'id': 2, 'symbol': 'Y', 'use_case': 'leap_put',
                   'direction': 'short', 'entry_px': 100,
                   'entry_date': date(2026, 10, 1), 'stop_px': 110,
                   'close_px': 112,
                   'closed_at': datetime(2026, 10, 5)},
                  ['stop_hit'])
    assert o2['realized_r'] == -1.2 and o2['stop_hit']
    # missing close → None, never a fabricated 0R
    o3 = _outcome({'id': 3, 'symbol': 'Z', 'use_case': 'swing',
                   'direction': 'long', 'entry_px': 100,
                   'entry_date': date(2026, 10, 1), 'stop_px': 90}, [])
    assert o3['realized_r'] is None and o3['realized_pct'] is None


def test_suggest_stamps_rules_version():
    # entry_snapshot must carry the spec version so realized R
    # attributes back to the rules that produced the entry
    import app.signals.trade_plans as tp
    called = {}
    def fake_live(sym):
        called['sym'] = sym
        return {'px': 100.0, 'det': {'atr_pct': 0.03},
                'mom': 'pullback', 'dip_phase': 'confirmed',
                'pulse_action': 'add', 'pulse_rule': 'add_growth'}
    old = tp._live
    tp._live = fake_live
    try:
        s = tp.suggest('X', 'swing')
    finally:
        tp._live = old
    assert s['rules_version'] and s['rules_version'].startswith('rules.')
    assert s['pulse_action'] == 'add' and s['entry_px'] == 100.0
