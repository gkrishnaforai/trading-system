"""FV v2 upgrade tests — survival tree, GQ fade, scenario tilt,
implied-margin reverse DCF.

Synthetic scalars only — no DB. The method YAMLs are the system under
test; formulas are loaded from disk so tests pin the shipped contract.
"""
import os

import pytest
import yaml

from app.fair_value_v2.blender import (
    SCENARIO_PROBS, enforce_scenario_order, expected_fair_value,
    tilted_scenario_probs)
from app.fair_value_v2.dsl.evaluator import evaluate_scenarios
from app.fair_value_v2.reverse_dcf import implied_margin_path

DEFS = os.path.join(os.path.dirname(__file__), "..",
                    "app", "fair_value_v2", "methods", "definitions")
SURV = yaml.safe_load(open(os.path.join(DEFS, "ev_sales_survival.yaml")))
QFADE = yaml.safe_load(open(os.path.join(DEFS, "dcf_quality_fade.yaml")))

HEALTHY = dict(revenue_ttm=1.0e9, shares_outstanding=100e6,
               cash_and_equivalents=2.0e9, revenue_growth_ttm=0.40,
               fcf_ttm=-2.0e8, market_cap=8.0e9, total_debt=0.3e9,
               net_profit_margin_ttm=-0.05)


def _surv(scalars, **params):
    p = dict(SURV["params"]); p.update(params)
    return evaluate_scenarios(SURV["formula"], scalars=scalars, params=p)


def _qf(scalars):
    return evaluate_scenarios(QFADE["formula"], scalars=scalars,
                              params=dict(QFADE["params"]))


# ---------------------------------------------------------- survival tree

class TestSurvivalTree:
    def test_healthy_name_prices_normally(self):
        sc, mt = _surv(HEALTHY)
        r = mt["report"]
        assert r["p_survival"] == pytest.approx(0.90)
        assert r["cash_runway_yrs"] >= 4.0
        assert sc["base"] and sc["base"] > 0
        assert sc["bear"] < sc["base"] < sc["bull"] < sc["explosive"]

    def test_p_survival_tiers_decrease_with_runway(self):
        def p(cash):
            sc, mt = _surv(dict(HEALTHY, cash_and_equivalents=cash,
                                fcf_ttm=-5e8))
            return mt["report"]["p_survival"]
        assert p(3e9) > p(1.5e9) > p(8e8) > p(5e8) > p(3e8)

    def test_leverage_stress_drops_to_floor(self):
        sc, mt = _surv(dict(HEALTHY, cash_and_equivalents=0.4e9,
                            total_debt=1.5e9, fcf_ttm=-5e8))
        assert mt["report"]["p_survival"] == pytest.approx(0.08)
        assert "survival_at_risk" in (mt.get("flags") or [])

    def test_dilution_monotonic_within_tier(self):
        # more burn inside the same runway tier → deeper dilution →
        # lower fair price
        def fp(burn):
            sc, _mt = _surv(dict(HEALTHY, fcf_ttm=-burn,
                                 cash_and_equivalents=5e9))
            return sc["base"]
        a, b, c = fp(3e8), fp(4e8), fp(6e8)
        assert a > b > c

    def test_funding_gap_raises_dilution(self):
        sc, mt = _surv(dict(HEALTHY, cash_and_equivalents=0.3e9,
                            fcf_ttm=-5e8))
        r = mt["report"]
        assert r["funding_gap"] > 0
        assert r["raise_dilution"] > 0
        assert r["dilution_mult"] > 1.0

    def test_survival_equity_floors_at_zero(self):
        # levered stub — EV/S equity < debt → survival leg = 0, the
        # distressed leg carries the residual
        sc, mt = _surv(dict(HEALTHY, cash_and_equivalents=0.3e9,
                            total_debt=5e9, fcf_ttm=-5e8,
                            market_cap=1e9))
        assert mt["report"]["survival_per_share"] == 0
        assert sc["base"] and sc["base"] > 0

    def test_report_exposes_internals(self):
        _, mt = _surv(HEALTHY)
        for k in ("p_survival", "cash_runway_yrs", "dilution_mult",
                  "wacc_eff", "scap_eff", "distressed_per_share"):
            assert k in mt["report"], k

    def test_wacc_tiers_follow_runway(self):
        def w(cash):
            _, mt = _surv(dict(HEALTHY, cash_and_equivalents=cash,
                               fcf_ttm=-5e8))
            return mt["report"]["wacc_eff"]
        assert w(3e9) == pytest.approx(0.10)   # 6y runway → low
        assert w(1.3e9) == pytest.approx(0.13) # 2.6y → mid
        assert w(1e9) == pytest.approx(0.16)   # 2.0y → high
        assert w(2e8) == pytest.approx(0.18)   # 0.4y → critical


# ---------------------------------------------------------- GQ fade

class TestQualityFade:
    BASE = dict(fcf_ttm=1e9, shares_outstanding=100e6,
                cash_and_equivalents=2e9, total_debt=0.5e9,
                revenue_growth_ttm=0.15)

    def test_high_gq_gets_long_fade(self):
        _, mt = _qf(dict(self.BASE, gq_score=80))
        r = mt["report"]
        assert r["flat_years"] == 10 and r["fade_years"] == 10
        assert r["horizon_years"] == 20

    def test_low_gq_compresses(self):
        sc, mt = _qf(dict(self.BASE, gq_score=30))
        r = mt["report"]
        assert r["flat_years"] == 3 and r["fade_years"] == 2
        assert "short_fade" in (mt.get("flags") or [])

    def test_missing_gq_defaults_mid(self):
        _, mt = _qf(dict(self.BASE))
        assert mt["report"]["flat_years"] == 7
        assert mt["report"]["fade_years"] == 5

    def test_moat_worth_more(self):
        hi, _ = _qf(dict(self.BASE, gq_score=80))
        lo, _ = _qf(dict(self.BASE, gq_score=30))
        assert hi["base"] > lo["base"]

    def test_scenario_order_holds(self):
        sc, _ = _qf(dict(self.BASE, gq_score=60))
        assert sc["bear"] < sc["base"] < sc["bull"] < sc["explosive"]


# ---------------------------------------------------------- scenario tilt

class TestScenarioTilt:
    def test_calm_unchanged(self):
        p = tilted_scenario_probs(vix=15, regime="technology:standard")
        assert p == {k: round(v, 4) for k, v in SCENARIO_PROBS.items()}

    def test_vix_stress_fattens_bear(self):
        p = tilted_scenario_probs(vix=32, regime="technology:standard")
        assert p["bear"] > SCENARIO_PROBS["bear"]
        assert p["explosive"] > SCENARIO_PROBS["explosive"]
        assert p["base"] < SCENARIO_PROBS["base"]
        assert sum(p.values()) == pytest.approx(1.0)

    def test_pre_earnings_regime_tilts(self):
        p = tilted_scenario_probs(vix=15, regime="growth:pre_earnings")
        assert p["bear"] > SCENARIO_PROBS["bear"]

    def test_flags_tilt(self):
        p = tilted_scenario_probs(
            vix=None, regime="x:standard",
            quality_flags=["extreme_gap", "tv_dominant"])
        assert p["bear"] > SCENARIO_PROBS["bear"]

    def test_floor_and_normalization(self):
        p = tilted_scenario_probs(vix=99, regime="a:pre_earnings",
                                  quality_flags=["extreme_gap",
                                                 "no_scenarios",
                                                 "tv_dominant"])
        assert all(v >= 0.02 for v in p.values())
        assert sum(p.values()) == pytest.approx(1.0)

    def test_expected_uses_tilted_weights(self):
        scen = {"bear": 10, "base": 20, "bull": 30, "explosive": 40}
        e_static = expected_fair_value(scen)
        e_stress = expected_fair_value(
            scen, probs=tilted_scenario_probs(vix=35,
                                              regime="x:pre_earnings"))
        assert e_stress < e_static  # bear weight pulled expected FV down


# ---------------------------------------------------------- reverse DCF

class TestImpliedMargin:
    KW = dict(wacc=0.10, terminal_growth=0.03, margin_ceiling=0.30)

    def test_solver_finds_reasonable_margin(self):
        # $50 spot, $1B rev growing 30%, burning -20% — solve the
        # normalized margin the price implies
        r = implied_margin_path(1e9, 0.30, -0.20, 100e6, 2e9, 50.0,
                                total_debt=0.3e9, **self.KW)
        assert r["status"] == "ok"
        assert -0.2 <= r["implied_normalized_margin"] <= 1.0
        assert r["implied_inflection_year"] is not None or \
            r["boundary"] == "at_cap"

    def test_speculative_flag_above_ceiling(self):
        # price demanding >ceiling margin → flagged
        r = implied_margin_path(1e9, 0.30, -0.20, 100e6, 2e9, 200.0,
                                total_debt=0.3e9, **self.KW)
        if r["implied_normalized_margin"] > 0.30:
            assert r["flag"] in ("implied_margin_speculative",
                                 "implied_margin_stretched")

    def test_not_applicable_guards(self):
        assert implied_margin_path(None, 0.3, -0.2, 1e8, 0, 50,
                                   **self.KW)["status"] == "not_applicable"
        assert implied_margin_path(1e9, 0.3, -0.2, 1e8, 0, None,
                                   **self.KW)["status"] == "not_applicable"


# ---------------------------------------------------------- ordering

class TestOrdering:
    def test_enforce_clamps_inversions(self):
        scen = {"bear": 12, "base": 10, "bull": 20, "explosive": 30}
        out, flags = enforce_scenario_order(scen)
        assert out["base"] >= out["bear"]
        assert any("ordering_violation" in f for f in flags)
