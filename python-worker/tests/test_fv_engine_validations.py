"""FV v2 engine validation suite — the 20-test catalog.

Each test is numbered to the catalog entry it implements and tests
VALUES against the deployed YAML definitions (loaded through the real
registry + evaluator), not code paths. A failed validation has a
defined outcome: rejection (DslError / missing_data), a qualified
estimate, or a flagged confidence — never a confident number from
invalid inputs.

Scope honesty:
- 16 (peer-set quality): the engine has no comparable-companies method;
  analyst_consensus is the nearest reference leg — tested for the
  no-fabrication contract; peer selection is N/A by design.
- 9/10 (FCF reconciliation, capex/D&A): the engine consumes fcf_ttm
  (OCF−capex, computed upstream PIT) — tests assert the convention is
  consistent (required, never raw OCF, cash credited exactly once);
  line-item reconciliation belongs to the ingest layer.
"""
import math
import os
import sys
from types import SimpleNamespace

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.fair_value_v2.blender import (  # noqa: E402
    SCENARIO_ORDER,
    SCENARIO_PROBS,
    WeightedBlender,
    enforce_scenario_order,
    expected_fair_value,
)
from app.fair_value_v2.decision import decide  # noqa: E402
from app.fair_value_v2.dsl.evaluator import DslError, evaluate_scenarios  # noqa: E402
from app.fair_value_v2.feature_resolver import FeatureResolver  # noqa: E402
from app.fair_value_v2.methods.registry import MethodRegistry  # noqa: E402

_DEFS = os.path.join(os.path.dirname(__file__), "..", "app",
                     "fair_value_v2", "methods", "definitions")
REG = MethodRegistry.load_from_dir(_DEFS)
METHOD_KEYS = sorted(REG.definitions.keys())


def _eval(method_key, scalars, params=None):
    """Run a deployed method definition against synthetic inputs."""
    d = REG.get(method_key)
    return evaluate_scenarios(
        d.formula,
        scalars=scalars,
        params={**(d.params or {}), **(params or {})},
        validations=list(d.validations or []),
    )[0]


def _defn(k):
    return REG.get(k)


# A healthy mid-cap growth profile — covers every scalar any method
# may consume so the full 18-method ordering matrix is evaluable.
BASE = {
    "eps_ttm": 5.0, "eps_forward": 6.0, "eps_growth_ttm": 0.20,
    "forward_growth": 0.18, "forward_growth_pct_1y": 20.0,
    "revenue_ttm": 1.0e10, "revenue_forward": 1.2e10,
    "revenue_growth_ttm": 0.15,
    "net_profit_margin_ttm": 0.20, "net_profit_margin_midcycle": 0.18,
    "operating_margin_ttm": 0.25,
    "fcf_ttm": 1.5e9, "net_income_ttm": 2.0e9,
    "shares_outstanding": 1.0e8, "cash_and_equivalents": 5.0e9,
    "total_debt": 3.0e9, "market_cap": 5.0e10,
    "eps_est_start": 4.0, "eps_est_end": 7.0, "eps_est_years": 3.0,
    "eps_est_analysts": 15,
    "tnx_yield": 4.0, "roe": 0.15, "book_value_per_share": 50.0,
    "consensus_price_target": 200.0, "price_target_low": 170.0,
    "price_target_high": 260.0, "analyst_count": 15,
    "dilution_overhang": 1.02, "cash_conversion": 1.0,
}


# ---------------- 1. known-answer DCF --------------------------------

def test_1_dcf_simple_known_answer():
    # fcf 1e9, g 8%, wacc 10%, gt 3% → PV explicit 4.7338e9,
    # PV TV 13.4244e9, +cash 2e9 → 20.1582e9 / 1e8 shares = 201.58
    out = _eval("dcf_simple", {"fcf_ttm": 1e9, "shares_outstanding": 1e8,
                               "cash_and_equivalents": 2e9})
    assert out["base"] == pytest.approx(201.58, rel=2e-3)


def test_1_dcf_mega_cap_reference_fade():
    # Independent reimplementation of the documented spec:
    # 5y compound at g0, 5y linear fade g→terminal, Gordon TV at y10.
    fcf, shares, cash = 1e9, 1e8, 1e9
    g0, wacc, gt = 0.10, 0.10, 0.03
    step = (g0 - gt) / 5
    f = fcf
    pv = 0.0
    for t in range(1, 11):
        g = g0 if t <= 5 else g0 - step * (t - 5)
        f *= (1 + g)
        pv += f / (1 + wacc) ** t
    tv = f * (1 + gt) / (wacc - gt)
    expected = (pv + tv / (1 + wacc) ** 10 + cash) / shares

    out = _eval("dcf_mega_cap",
                {"fcf_ttm": fcf, "shares_outstanding": shares,
                 "cash_and_equivalents": cash,
                 "revenue_growth_ttm": g0})
    assert out["base"] == pytest.approx(expected, rel=1e-9)


# ---------------- 2. scenario ordering --------------------------------

def test_2_all_methods_bear_le_base_le_bull_le_explosive():
    for key in METHOD_KEYS:
        out = _eval(key, BASE)
        vals = [out[k] for k in ("bear", "base", "bull", "explosive")
                if out.get(k) is not None]
        assert vals == sorted(vals), f"{key}: {out}"


def test_2_ordering_violation_clamped_and_flagged():
    scen, flags = enforce_scenario_order(
        {"bear": 90.0, "base": 80.0, "bull": 160.0, "explosive": 200.0})
    assert flags == ["ordering_violation:base<bear"]
    assert scen["base"] == 90.0
    assert scen["bull"] == 160.0  # untouched


# ---------------- 3. discount-rate sensitivity -------------------------

def test_3_higher_wacc_lowers_value_simple():
    scalars = {"fcf_ttm": 1e9, "shares_outstanding": 1e8,
               "cash_and_equivalents": 1e9}
    vals = [_eval("dcf_simple", scalars, {"wacc": w})["base"]
            for w in (0.09, 0.10, 0.12)]
    assert vals[0] > vals[1] > vals[2] > 0


def test_3_higher_wacc_lowers_value_mega():
    # fixture mild enough that the explosive leg also clears the
    # terminal-share cap — monotonicity is what's being tested
    scalars = {"fcf_ttm": 1e9, "shares_outstanding": 1e8,
               "cash_and_equivalents": 1e9, "revenue_growth_ttm": 0.05}
    vals = [_eval("dcf_mega_cap", scalars, {"wacc": w})["base"]
            for w in (0.11, 0.12, 0.14)]
    assert vals[0] > vals[1] > vals[2] > 0


# ---------------- 4. terminal-growth sensitivity -----------------------

def test_4_higher_terminal_growth_raises_value_when_below_wacc():
    scalars = {"fcf_ttm": 1e9, "shares_outstanding": 1e8,
               "cash_and_equivalents": 1e9}
    vals = [_eval("dcf_simple", scalars, {"terminal_growth": g})["base"]
            for g in (0.02, 0.03, 0.035)]
    assert vals[0] < vals[1] < vals[2]


@pytest.mark.parametrize("gt", [0.10, 0.12])
def test_4_terminal_growth_at_or_above_wacc_rejected(gt):
    scalars = {"fcf_ttm": 1e9, "shares_outstanding": 1e8,
               "cash_and_equivalents": 1e9}
    assert _eval("dcf_simple", scalars,
                 {"terminal_growth": gt})["base"] is None
    # mega: base leg nulls via the wacc−gt≤0 guard; a scenario leg may
    # reject outright (TV dominance) — either is a rejection, not a value
    try:
        out = _eval("dcf_mega_cap", {**scalars, "revenue_growth_ttm": 0.10},
                    {"terminal_growth": gt})
        assert out["base"] is None
    except DslError:
        pass


# ---------------- 5. terminal-value dominance ---------------------------

def test_5_dcf_simple_default_params_emit():
    # 5y stable DCF legitimately carries ~74% TV — the cap must let a
    # normal stable name through while still catching pathological TV.
    out = _eval("dcf_simple", {"fcf_ttm": 1e9, "shares_outstanding": 1e8,
                               "cash_and_equivalents": 1e9})
    assert out["base"] is not None


def test_5_excessive_terminal_share_flagged_not_rejected():
    # terminal_growth 5% vs wacc 10% → TV ~80%+ of EV — legitimate for
    # long-duration names: emit the value, flag the dependence so the
    # decision layer charges uncertainty instead of losing the answer
    d = _defn("dcf_simple")
    scen, metrics = evaluate_scenarios(
        d.formula,
        scalars={"fcf_ttm": 1e9, "shares_outstanding": 1e8,
                 "cash_and_equivalents": 1e9},
        params={**(d.params or {}), "terminal_growth": 0.05},
        validations=list(d.validations or []),
    )
    assert scen["base"] is not None
    assert "tv_dominant" in (metrics.get("flags") or [])


def test_5_terminal_share_within_cap_not_flagged():
    # a normal stable name must NOT carry the flag
    d = _defn("dcf_simple")
    scen, metrics = evaluate_scenarios(
        d.formula,
        scalars={"fcf_ttm": 1e9, "shares_outstanding": 1e8,
                 "cash_and_equivalents": 1e9},
        params=dict(d.params or {}),
        validations=list(d.validations or []),
    )
    assert scen["base"] is not None
    assert "tv_dominant" not in (metrics.get("flags") or [])


# ---------------- 6. horizon & convergence ------------------------------

def test_6_mega_cap_growth_fades_not_compounds():
    # Same fcf/wacc/cash: growth must fade to 3% by year 10 — the faded
    # price must sit BELOW a naive 10y compound bound at the same g0.
    scalars = {"fcf_ttm": 1e9, "shares_outstanding": 1e8,
               "cash_and_equivalents": 0.0, "revenue_growth_ttm": 0.15}
    faded = _eval("dcf_mega_cap", scalars)["base"]
    fcf10 = 1e9 * 1.15 ** 10
    naive = (sum(1e9 * 1.15 ** t / 1.10 ** t for t in range(1, 11))
             + fcf10 * 1.03 / 0.07 / 1.10 ** 10) / 1e8
    assert 0 < faded < naive


# ---------------- 7. revenue-growth consistency --------------------------

def test_7_forward_revenue_drives_sales_base_and_ramp_floor():
    # forward rev 2x trailing → ramp floor lifts negative margin to 10%
    ramp = _eval("ev_sales_growth", {
        "revenue_ttm": 1e10, "revenue_forward": 2e10,
        "revenue_growth_ttm": 0.30, "net_profit_margin_ttm": -0.20,
        "fcf_ttm": -2e9, "shares_outstanding": 1e8,
        "cash_and_equivalents": 1e9})
    no_ramp = _eval("ev_sales_growth", {
        "revenue_ttm": 1e10, "revenue_forward": None,
        "revenue_growth_ttm": 0.30, "net_profit_margin_ttm": -0.20,
        "fcf_ttm": -2e9, "shares_outstanding": 1e8,
        "cash_and_equivalents": 1e9})
    # ramp: sales 2e10, pe=12+40*.3=24, margin .10 → evs 2.4 → 49e9 → 490
    assert ramp["base"] == pytest.approx(490.0, rel=2e-3)
    # no forward: sales 1e10, margin floor .03 → evs .72 → 8.2e9 → 82
    assert no_ramp["base"] == pytest.approx(82.0, rel=2e-3)


# ---------------- 8. margin realism -------------------------------------

def test_8_impossible_margin_rejected():
    with pytest.raises(DslError) as e:
        _eval("ev_sales_growth", {**BASE, "net_profit_margin_ttm": 1.20})
    assert e.value.code == "invalid_input"


def test_8_margin_capped_at_60pct():
    out = _eval("ev_sales_growth", {**BASE, "revenue_forward": None,
                                    "net_profit_margin_ttm": 0.90,
                                    "net_profit_margin_midcycle": 0.85,
                                    "fcf_ttm": 9e9})
    # margin min((.9+.85)/2, .9)=.875 → src min(.875,.6)=.6; pe 18 →
    # evs 10.8 → 1e10*10.8=1.08e11 + 5e9 cash − 3e9 debt → 1100
    assert out["base"] == pytest.approx(1100.0, rel=2e-3)


# ---------------- 9. cash-flow reconciliation ----------------------------

def test_9_fcf_margin_used_when_better_than_net_margin():
    # fcf/revenue .30 > net .20 → margin_raw .30, cash added exactly once
    out = _eval("ev_sales_growth", {
        "revenue_ttm": 1e10, "revenue_forward": None,
        "revenue_growth_ttm": 0.15, "net_profit_margin_ttm": 0.20,
        "fcf_ttm": 3e9, "shares_outstanding": 1e8,
        "cash_and_equivalents": 4e9})
    assert out["base"] == pytest.approx(580.0, rel=2e-3)


def test_10_dcf_consumes_fcf_not_unreconciled_flows():
    # capex is already netted inside fcf_ttm upstream — the DCF methods
    # must require fcf and never double-count a capex/OCF pair.
    for key in ("dcf_simple", "dcf_mega_cap"):
        req = (_defn(key).requires or {}).get("scalars") or []
        assert "fcf_ttm" in req
        assert "operating_cash_flow" not in req
        assert "capex" not in req


# ---------------- 11. share dilution ------------------------------------

def test_11_per_share_fair_value_scales_with_share_count():
    scalars = {"fcf_ttm": 1.5e9, "revenue_growth_ttm": 0.15,
               "cash_and_equivalents": 5e9}
    a = _eval("ev_fcf", {**scalars, "shares_outstanding": 1e8})["base"]
    b = _eval("ev_fcf", {**scalars, "shares_outstanding": 2e8})["base"]
    assert a == pytest.approx(2 * b, rel=1e-9)


def test_11_dilution_overhang_priced_in_decision():
    def _mr(fv, inputs):
        return {"method_key": "m", "status": "ok", "fair_price": fv,
                "inputs_used": inputs, "metrics": {}}
    scen = {"bear": 80.0, "base": 120.0, "bull": 160.0, "explosive": 190.0}
    ok = {"fcf_ttm": 2e9, "analyst_count": 20, "net_income_ttm": 3e9,
          "cash_conversion": 1.1, "cash_and_equivalents": 5e9,
          "total_debt": 1e9}
    d = decide("technology", 120.0, 122.0, scen, [], 100.0,
               [_mr(120.0, {**ok, "dilution_overhang": 1.08}),
                _mr(122.0, ok)])
    assert "share_dilution" in d["mos_adders"]
    d2 = decide("technology", 120.0, 122.0, scen, [], 100.0,
                [_mr(120.0, {**ok, "dilution_overhang": 1.04}),
                 _mr(122.0, ok)])
    assert "share_dilution" not in d2["mos_adders"]


# ---------------- 12. EV → equity bridge ---------------------------------

@pytest.mark.parametrize("method,extra", [
    ("ev_sales_growth", {"revenue_ttm": 1e10, "revenue_growth_ttm": 0.15,
                         "net_profit_margin_ttm": 0.2, "fcf_ttm": 1.5e9}),
    ("ev_fcf", {"revenue_growth_ttm": 0.15, "fcf_ttm": 1.5e9}),
    ("dcf_simple", {"fcf_ttm": 1.5e9}),
    ("dcf_mega_cap", {"fcf_ttm": 1.5e9, "revenue_growth_ttm": 0.10}),
])
def test_12_debt_subtracted_in_equity_bridge(method, extra):
    # equity = EV + cash − debt: +5e9 debt at 1e8 shares must lower
    # the fair price by exactly $50 — levered names are not free
    base = {"shares_outstanding": 1e8, "cash_and_equivalents": 5e9,
            **extra}
    a = _eval(method, base)["base"]
    b = _eval(method, {**base, "total_debt": 5e9})["base"]
    assert a is not None and b is not None
    assert a - b == pytest.approx(50.0, rel=1e-9)


def test_12_missing_debt_resolves_as_zero():
    # absent debt data means no subtraction, not a rejection
    out = _eval("ev_fcf", {"fcf_ttm": 1.5e9, "revenue_growth_ttm": 0.15,
                           "shares_outstanding": 1e8,
                           "cash_and_equivalents": 5e9})["base"]
    assert out == pytest.approx(395.0, rel=1e-6)


def test_12_diluted_shares_priced_when_present():
    scalars = {"fcf_ttm": 1.5e9, "revenue_growth_ttm": 0.15,
               "shares_outstanding": 1e8, "cash_and_equivalents": 5e9}
    basic = _eval("ev_fcf", scalars)["base"]
    diluted = _eval("ev_fcf", {**scalars, "shares_diluted": 1.1e8})["base"]
    assert diluted == pytest.approx(basic / 1.1, rel=1e-6)


def test_12_cash_credited_exactly_once():
    out = _eval("ev_fcf", {"fcf_ttm": 1.5e9, "revenue_growth_ttm": 0.15,
                           "shares_outstanding": 1e8,
                           "cash_and_equivalents": 5e9})["base"]
    # fair*shares − fcf*mult == cash → 395*1e8 − 34.5e9 = 5e9
    assert out * 1e8 - (1.5e9 * 23.0) == pytest.approx(5e9, rel=1e-6)


# ---------------- 13. cyclical normalization ------------------------------

def test_13_pe_cyclical_normalizes_peak_eps():
    # eps_norm = 0.6*fwd + 0.4*ttm — peak TTM earns no compounder PE
    out = _eval("pe_cyclical", {"eps_ttm": 8.0, "eps_forward": 4.0})
    assert out["base"] == pytest.approx(5.6 * 11.0, rel=1e-9)
    # missing forward → TTM carries the normalization alone
    out2 = _eval("pe_cyclical", {"eps_ttm": 8.0, "eps_forward": None})
    assert out2["base"] == pytest.approx(8.0 * 11.0, rel=1e-9)


def test_13_midcycle_margin_shrinks_peak_never_lifts_trough():
    peak = _eval("ev_sales_growth", {
        **BASE, "revenue_forward": None, "net_profit_margin_ttm": 0.50,
        "fcf_ttm": 5e9, "net_profit_margin_midcycle": 0.20})
    no_mid = _eval("ev_sales_growth", {
        **BASE, "revenue_forward": None, "net_profit_margin_ttm": 0.50,
        "fcf_ttm": 5e9, "net_profit_margin_midcycle": None})
    assert peak["base"] < no_mid["base"]
    trough = _eval("ev_sales_growth", {
        **BASE, "revenue_forward": None, "net_profit_margin_ttm": 0.10,
        "fcf_ttm": 1e9, "net_profit_margin_midcycle": 0.40})
    assert trough["base"] == pytest.approx(
        _eval("ev_sales_growth", {**BASE, "revenue_forward": None,
                                  "net_profit_margin_ttm": 0.10,
                                  "fcf_ttm": 1e9,
                                  "net_profit_margin_midcycle": None}
              )["base"], rel=1e-9)


# ---------------- 14. negative earnings / FCF -----------------------------

def test_14_no_method_emits_from_negative_denominators():
    dead = dict(BASE)
    dead.update(eps_ttm=-1.0, eps_forward=-1.0, fcf_ttm=-5e9,
                forward_growth_pct_1y=0.0, eps_est_start=-1.0,
                eps_est_end=-2.0,
                net_profit_margin_ttm=-0.30, revenue_forward=None)
    for key in METHOD_KEYS:
        try:
            out = _eval(key, dead)
        except DslError:
            continue  # explicit rejection is an acceptable outcome
        for k, v in out.items():
            assert v is None or v >= 0, f"{key}.{k} = {v} on dead inputs"
        # methods that NEED positive earnings/cash must refuse outright
        if key in ("pe_basic", "pe_forward", "pe_growth", "pe_technology",
                   "pe_value", "pe_cyclical", "pe_technology_dynamic",
                   "ev_fcf", "dcf_simple", "dcf_mega_cap", "peg",
                   "peg_corrected", "peg_40", "peg_r40_cagr"):
            assert out["base"] is None, f"{key} emitted {out['base']}"


# ---------------- 15. method selection by economics ----------------------

METHODS_DIR = os.path.dirname(_DEFS)


def test_15_every_routed_method_exists():
    for fn in ("category_methods.yaml", "regime_methods.yaml"):
        spec = yaml.safe_load(open(os.path.join(METHODS_DIR, fn)))
        found = set()
        def walk(o):
            if isinstance(o, dict):
                if "method_key" in o:
                    found.add(o["method_key"])
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(spec)
        unknown = found - set(METHOD_KEYS)
        assert not unknown, f"{fn} routes to missing methods: {unknown}"


def test_15_pre_earnings_never_routes_to_eps_methods():
    spec = yaml.safe_load(open(os.path.join(METHODS_DIR,
                                            "regime_methods.yaml")))
    bad = []
    for cat, regimes in (spec.get("selections") or {}).items():
        pe = (regimes or {}).get("pre_earnings")
        for m in ((pe or {}).get("methods") or []):
            k = m["method_key"]
            if k.startswith(("pe_", "peg", "dcf")):
                bad.append(f"{cat}:pre_earnings→{k}")
    assert not bad, f"pre-earnings routed to earnings methods: {bad}"


def test_15_cyclical_and_bank_economics_routed():
    spec = yaml.safe_load(open(os.path.join(METHODS_DIR,
                                            "regime_methods.yaml")))
    sel = spec["selections"]
    assert {m["method_key"] for m in
            sel["cyclical"]["cyclical"]["methods"]} == {"pe_cyclical"}
    assert {m["method_key"] for m in
            sel["financials"]["bank"]["methods"]} == {"pb_bank"}
    mega = {m["method_key"]
            for m in sel["ai_infra"]["mega_cap_high_growth"]["methods"]}
    assert "dcf_mega_cap" in mega  # mega-caps get a cash-flow anchor


# ---------------- 16. reference leg honesty (comps N/A) -------------------

def test_16_analyst_consensus_known_answer_and_no_fabrication():
    out = _eval("analyst_consensus", BASE)
    assert out["base"] == 200.0 and out["bear"] == 170.0
    assert out["bull"] == 260.0 and out["explosive"] is None
    # no high/low → ±12% band; no consensus → nothing
    out2 = _eval("analyst_consensus",
                 {"consensus_price_target": 200.0})
    assert out2["bear"] == pytest.approx(176.0)
    assert out2["bull"] == pytest.approx(224.0)
    out3 = _eval("analyst_consensus",
                 {"consensus_price_target": 0.0})
    assert all(v is None for v in out3.values())


# ---------------- 17. independent-method cross-check ----------------------

def _mr(fv=None, status="ok", inputs=None):
    return {"method_key": "m", "status": status, "fair_price": fv,
            "inputs_used": inputs or {}, "metrics": {}}


SCEN = {"bear": 80.0, "base": 120.0, "bull": 160.0, "explosive": 190.0}
OK_IN = {"fcf_ttm": 2e9, "analyst_count": 20, "net_income_ttm": 3e9,
         "cash_conversion": 1.1, "cash_and_equivalents": 5e9,
         "total_debt": 1e9, "dilution_overhang": 1.0}


def test_17_dispersion_flags_not_forces_agreement():
    # $477 vs $146 on $228 spot → disagreement flagged, blend still emits
    mrs = [_mr(477.0, inputs=OK_IN), _mr(146.0), _mr(172.0)]
    d = decide("ai_infra", 258.0, 264.0, SCEN, [], 228.52, mrs)
    assert d["valuation_confidence"] == "low"
    assert "method_dispersion" in d["mos_adders"]
    assert d["method_dispersion"] == pytest.approx(1.449, abs=1e-3)
    assert d["buy_below"] is not None  # flagged, not fabricated away


def test_17_dispersion_boundaries():
    def disp_at(spread_frac, spot=100.0):
        lo, hi = 100.0, 100.0 + spread_frac * spot
        return decide("technology", 100.0, 100.0, SCEN, [], spot,
                      [_mr(lo, inputs=OK_IN), _mr(hi)])
    assert disp_at(0.34)["valuation_confidence"] == "high"
    assert disp_at(0.36)["valuation_confidence"] == "medium"
    assert "method_dispersion" not in disp_at(0.49)["mos_adders"]
    assert "method_dispersion" in disp_at(0.51)["mos_adders"]
    assert disp_at(0.71)["valuation_confidence"] == "low"


# ---------------- 18. data freshness & integrity --------------------------

# ---------------- reverse DCF — market-implied expectations -------------

_DCF_KW = dict(wacc=0.10, terminal_growth=0.03, growth_cap=0.20,
               fade_years=5, explicit_years=10)
_DCF_PRICE_KW = {k: v for k, v in _DCF_KW.items() if k != "growth_cap"}


def test_reverse_dcf_recovers_known_growth():
    from app.fair_value_v2.reverse_dcf import dcf_price, implied_growth
    for g_true in (-0.10, 0.0, 0.05, 0.12, 0.19):
        price = dcf_price(1e9, 1e8, 5e9, growth=g_true,
                          **_DCF_PRICE_KW)["price"]
        out = implied_growth(1e9, 1e8, 5e9, price, **_DCF_KW)
        assert out["boundary"] is None
        assert abs(out["implied_fcf_growth"] - g_true) < 1e-4, \
            f"g_true={g_true} → {out['implied_fcf_growth']}"


def test_reverse_dcf_boundary_flags():
    from app.fair_value_v2.reverse_dcf import dcf_price, implied_growth
    # price far above what the cap-growth DCF can produce → at_cap
    p_high = 5 * dcf_price(1e9, 1e8, 5e9, growth=0.20,
                           **_DCF_PRICE_KW)["price"]
    out = implied_growth(1e9, 1e8, 5e9, p_high, **_DCF_KW)
    assert out["boundary"] == "at_cap" and out["flag"] == "implied_above_cap"
    # price below the -60%/yr floor → below_floor
    p_low = 0.5 * dcf_price(1e9, 1e8, 5e9, growth=-0.60,
                            **_DCF_PRICE_KW)["price"]
    out = implied_growth(1e9, 1e8, 5e9, p_low, **_DCF_KW)
    assert out["boundary"] == "below_floor" \
        and out["flag"] == "implied_below_floor"


def test_reverse_dcf_not_applicable_cases():
    from app.fair_value_v2.reverse_dcf import implied_growth
    for kwargs, reason in (
            ({}, "no_spot_price"),
            ({"fcf_ttm": -1e9, "spot": 100.0}, "fcf_ttm_not_positive"),
            ({"shares_outstanding": 0, "spot": 100.0},
             "shares_not_positive")):
        base = dict(fcf_ttm=1e9, shares_outstanding=1e8,
                    cash_and_equivalents=5e9, spot=None)
        base.update(kwargs)
        fcf = base.pop("fcf_ttm"); sh = base.pop("shares_outstanding")
        cash = base.pop("cash_and_equivalents"); spot = base.pop("spot")
        out = implied_growth(fcf, sh, cash, spot, **_DCF_KW)
        assert out["status"] == "not_applicable" \
            and out["reason"] == reason


def test_reverse_dcf_spec_matches_deployed_dcf():
    # the inversion must price IDENTICALLY to the deployed
    # dcf_mega_cap at the same growth input (modulo the g>=0 clamp)
    from app.fair_value_v2.reverse_dcf import dcf_price
    d = _defn("dcf_mega_cap")
    scalars = {"fcf_ttm": 1.5e9, "shares_outstanding": 1e8,
               "cash_and_equivalents": 5e9, "revenue_growth_ttm": 0.12}
    out = _eval("dcf_mega_cap", scalars)
    p = dict(d.params or {})
    ref = dcf_price(1.5e9, 1e8, 5e9, wacc=p["wacc"],
                    terminal_growth=p["terminal_growth"], growth=0.12,
                    fade_years=p["fade_years"],
                    explicit_years=p["explicit_years"])["price"]
    assert abs(ref - out["base"]) < 0.01 * out["base"]


def test_18_missing_required_scalar_rejects_not_zeros():
    with pytest.raises(DslError) as e:
        _eval("pe_basic", {"eps_ttm": None})
    assert e.value.code in ("missing", "missing_data", "invalid_number")


def test_18_missing_series_input_is_missing_data_not_zero():
    # peg needs a growth feature — absent means missing, not g=0 priced
    with pytest.raises(DslError):
        _eval("peg", {"eps_forward": 5.0, "forward_growth_pct_1y": None})


def test_18_no_method_invents_growth_from_absent_inputs():
    # every method evaluated on a near-empty scalar dict must either
    # reject (DslError) or emit null — never a number from nothing.
    for key in METHOD_KEYS:
        try:
            out = _eval(key, {})
        except DslError:
            continue
        assert all(v is None for v in out.values()), \
            f"{key} emitted {out} from empty inputs"


def test_18_source_db_error_degrades_to_missing_then_fallback(tmp_path):
    # A source-level DB failure (schema drift: renamed/dropped column
    # or table) must NOT abort the run — the source resolves to
    # unavailable with explicit metadata and coalesce falls through.
    feats = tmp_path / "features.yaml"
    feats.write_text(yaml.safe_dump({
        "allow_table_columns": {
            "ghost_table": {"as_of_columns": ["d"], "columns": ["c"]},
        },
        "features": {
            "with_fallback": {
                "type": "coalesce",
                "sources": [
                    {"type": "table_column", "table": "ghost_table",
                     "column": "c", "as_of": "d", "order_by": "d",
                     "where_not_null": True},
                    {"type": "snapshot_json_path", "source": "snap",
                     "path": ["x"]},
                ],
            },
            "no_fallback": {
                "type": "table_column", "table": "ghost_table",
                "column": "c", "as_of": "d", "order_by": "d",
            },
        },
    }))

    class BoomStore:
        def get_table_scalar(self, **kw):
            raise RuntimeError('column "c" does not exist')

        def get_snapshot_payload(self, symbol, as_of_ts, source=None):
            return {"x": 42.0}, as_of_ts

    import datetime as _dt
    r = FeatureResolver(BoomStore(), str(feats))
    scalars, sources, quality = r.resolve_scalars(
        "MCD", _dt.datetime(2026, 10, 14, tzinfo=_dt.timezone.utc),
        ["with_fallback", "no_fallback"])

    assert scalars["with_fallback"] == 42.0            # fell through
    assert scalars["no_fallback"] is None              # no fabricated 0
    assert quality["with_fallback.part_0.source_error"] is True
    assert quality["no_fallback.source_error"] is True
    assert quality["with_fallback.selected"] == 1


# ---------------- 19. extreme values & boundaries -------------------------

def test_19_growth_unit_mistake_rejected():
    for key in ("peg", "peg_corrected"):
        with pytest.raises(DslError) as e:
            _eval(key, {"eps_forward": 5.0,
                        "forward_growth_pct_1y": 350.0})
        assert e.value.code == "invalid_input"


def test_19_zero_shares_and_negative_flows_yield_null():
    for key, extra in (
            ("ev_fcf", {"fcf_ttm": 1e9, "revenue_growth_ttm": 0.1}),
            ("ev_sales_growth", {"revenue_ttm": 1e10,
                                 "revenue_growth_ttm": 0.1}),
            ("dcf_simple", {"fcf_ttm": 1e9})):
        out = _eval(key, {**extra, "shares_outstanding": 0.0,
                          "cash_and_equivalents": 1e9})
        assert out["base"] is None, f"{key} priced on zero shares"


def test_19_absurd_and_non_finite_outputs_rejected():
    with pytest.raises(DslError) as e:
        evaluate_scenarios(
            {"fair_price": {"var": "x"}}, scalars={"x": 5e7}, params={})
    assert e.value.code == "invalid_assumption"
    with pytest.raises(DslError):
        evaluate_scenarios(
            {"fair_price": {"div": [{"var": "x"}, 0]}},
            scalars={"x": 1.0}, params={})


def test_19_division_by_zero_never_leaks():
    # roe=g → (roe−g)/(r−g) numerator 0 → P/B floor, NOT a crash
    out = _eval("pb_bank", {"book_value_per_share": 50.0, "roe": 0.03})
    assert out["base"] == pytest.approx(50.0 * 0.7, rel=1e-9)


# ---------------- 20. scenario & uncertainty validation -------------------

def test_20_scenario_weights_sum_to_one_and_cover_all_keys():
    assert set(SCENARIO_PROBS) == set(SCENARIO_ORDER)
    assert sum(SCENARIO_PROBS.values()) == pytest.approx(1.0)


def test_20_expected_fv_renormalizes_on_missing_scenarios():
    full = {"bear": 80.0, "base": 120.0, "bull": 160.0, "explosive": 200.0}
    assert expected_fair_value(full) == pytest.approx(
        0.25 * 80 + 0.50 * 120 + 0.20 * 160 + 0.05 * 200)
    partial = {**full, "explosive": None}
    assert expected_fair_value(partial) == pytest.approx(
        (0.25 * 80 + 0.50 * 120 + 0.20 * 160) / 0.95)
    assert expected_fair_value({}) is None


def _mr_obj(key, fv, status="ok"):
    return SimpleNamespace(method_key=key, enabled=True, status=status,
                           fair_price=fv, inputs_used={}, metrics={})


def test_20_blend_drops_invalid_methods_and_renormalizes():
    blend = WeightedBlender().blend([
        (_mr_obj("pe_a", 100.0), 0.5), (_mr_obj("pe_b", 200.0), 0.5),
        (_mr_obj("pe_c", None, status="missing_data"), 0.9)])
    assert blend.fair_value == pytest.approx(150.0)


def test_20_family_cap_bounds_correlated_cluster():
    mrs = [_mr_obj("peg_a", 100.0), _mr_obj("peg_b", 100.0),
           _mr_obj("peg_c", 100.0), _mr_obj("dcf_a", 200.0)]
    blend = WeightedBlender().blend(list(zip(mrs, [1, 1, 1, 1])))
    # peg family 3/4 = 75% > 55% → each scaled to 0.55·4/3 = 0.7333
    w_peg = 0.55 * 4 / 3
    assert blend.fair_value == pytest.approx(
        (3 * w_peg * 100 + 200) / (3 * w_peg + 1), rel=1e-9)


def test_20_confidence_reflects_evidence_not_optimism():
    # 1 ok method + no_scenarios flag → can never be 'high'
    d = decide("technology", 120.0, 120.0, {}, ["no_scenarios"], 100.0,
               [_mr(120.0, inputs=OK_IN)])
    assert d["valuation_confidence"] == "low"
    # clean 2-method agreement earns high
    d2 = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
                [_mr(119.0, inputs=OK_IN), _mr(121.0, inputs=OK_IN)])
    assert d2["valuation_confidence"] == "high"


# ---------------- 21. earnings-quality & capital signals -------------------

def test_21_earnings_divergence_classified_by_cause():
    base = dict(OK_IN)
    base.update({"revenue_growth_ttm": 0.30, "eps_growth_ttm": 0.25})
    # aligned growth → no signal
    d = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
               [_mr(120.0, inputs=base), _mr(122.0, inputs=base)])
    assert d["earnings_quality"] is None
    # adverse + dilution overhang → divergence_dilution
    dil = {**base, "eps_growth_ttm": 0.05, "dilution_overhang": 1.10}
    d2 = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
                [_mr(120.0, inputs=dil), _mr(122.0, inputs=dil)])
    assert d2["earnings_quality"]["classification"] == "divergence_dilution"
    assert "divergence_dilution" in d2["mos_adders"]
    # funding risk wins over dilution when fcf<0 and levered
    fund = {**base, "eps_growth_ttm": -0.10, "fcf_ttm": -1e9,
            "total_debt": 15e9, "cash_and_equivalents": 3e9,
            "dilution_overhang": 1.10}
    d3 = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
                [_mr(120.0, inputs=fund), _mr(122.0, inputs=fund)])
    assert d3["earnings_quality"]["classification"] == "divergence_funding_risk"
    # clean balance sheet → investment phase: smaller watch adder
    inv = {**base, "eps_growth_ttm": 0.05, "dilution_overhang": 1.0}
    d4 = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
                [_mr(120.0, inputs=inv), _mr(122.0, inputs=inv)])
    assert d4["earnings_quality"]["classification"] == "divergence_investment_phase"
    assert "divergence_investment_phase" in d4["mos_adders"]
    # eps outpacing revenue → favorable: recorded, never penalized
    fav = {**base, "eps_growth_ttm": 0.50}
    d5 = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
                [_mr(120.0, inputs=fav), _mr(122.0, inputs=fav)])
    assert d5["earnings_quality"]["classification"] == "divergence_favorable"
    assert "divergence_favorable" not in d5["mos_adders"]


def test_21_roic_gate_flags_value_destroying_growth():
    low_roic = {**OK_IN, "roic_ttm": 0.06, "revenue_growth_ttm": 0.30}
    d = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
               [_mr(120.0, inputs=low_roic), _mr(122.0, inputs=low_roic)])
    assert "reinvestment_below_wacc" in d["mos_adders"]
    assert d["capital_quality"]["flag"] == "growth_below_wacc"
    hi = {**OK_IN, "roic_ttm": 0.22, "revenue_growth_ttm": 0.30}
    d2 = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
                [_mr(120.0, inputs=hi), _mr(122.0, inputs=hi)])
    assert "reinvestment_below_wacc" not in d2["mos_adders"]
    assert d2["capital_quality"]["flag"] == "capital_efficient"
    # no roic data → clean no-op
    d3 = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
                [_mr(120.0, inputs=OK_IN), _mr(121.0, inputs=OK_IN)])
    assert d3["capital_quality"] is None


def test_21_tv_dominant_charges_uncertainty_and_caps_confidence():
    d = decide("technology", 120.0, 122.0, SCEN, ["tv_dominant"], 100.0,
               [_mr(119.0, inputs=OK_IN), _mr(121.0, inputs=OK_IN)])
    assert "tv_dominant" in d["mos_adders"]
    # forbidden flag → can never be 'high'
    assert d["valuation_confidence"] != "high"


# ---------------- 22. industry-relative leg & uncertainty split -----------

def test_22_peer_medians_from_key_metrics():
    from app.fair_value_v2.relative import peer_medians
    rows = [{"symbol": f"P{p}", "key_metrics": {
                "earningsYieldTTM": 1.0 / p,
                "evToSalesTTM": p / 10.0}}
            for p in (20, 30, 40)]
    med = peer_medians(rows)
    assert med["pe"] == pytest.approx(30.0, rel=1e-6)
    assert med["ev_sales"] == pytest.approx(3.0, rel=1e-6)
    # outlier (pe=1000) exceeds the sanity bound — excluded, not averaged
    rows2 = rows + [{"symbol": "PX", "key_metrics": {
        "earningsYieldTTM": 0.001, "evToSalesTTM": 3.0}}]
    assert peer_medians(rows2)["pe"] == pytest.approx(30.0, rel=1e-6)


def test_22_relative_flag_is_growth_normalized():
    from app.fair_value_v2.relative import flag_relative
    med = {"pe": 20.0, "revenue_growth": 0.10}
    # fv implies 40x vs 20x peers but subject grows 30% vs peers' 10%
    # → the premium is growth-supported, not flagged
    r = flag_relative(med, {"pe": 45.0}, {"pe": 40.0}, 0.30)
    assert r.get("flag") is None
    assert r["growth_edge"]["subject"] == pytest.approx(0.30)
    # same 40x premium without the growth edge → flagged unsupported
    r2 = flag_relative(med, {"pe": 45.0}, {"pe": 40.0}, 0.10)
    assert r2["flag"] == "fv_premium_unsupported"
    # fv far below peers → pessimism flagged
    r3 = flag_relative(med, {"pe": 10.0}, {"pe": 10.0}, 0.10)
    assert r3["flag"] == "fv_discount_vs_peers"


def test_22_uncertainty_split_two_axes():
    # business risk high (divergence + no coverage + negative fcf)
    # while methods agree tightly → valuation uncertainty stays low
    risky = {"fcf_ttm": -1e9, "analyst_count": 0, "net_income_ttm": -2e9,
             "cash_and_equivalents": 3e9, "total_debt": 15e9,
             "revenue_growth_ttm": 0.30, "eps_growth_ttm": -0.10,
             "dilution_overhang": 1.0}
    tight = {"bear": 110.0, "base": 120.0, "bull": 130.0,
             "explosive": 135.0}
    d = decide("technology", 120.0, 122.0, tight, [], 100.0,
               [_mr(120.0, inputs=risky), _mr(122.0, inputs=risky)])
    assert d["business_uncertainty"]["score"] == "high"
    assert d["valuation_uncertainty"]["score"] == "low"
    # flip: clean inputs but methods disagree 3x → valuation axis fires
    far = _mr(60.0, inputs=OK_IN)
    d2 = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
                [_mr(120.0, inputs=OK_IN), far, _mr(180.0, inputs=OK_IN)])
    assert d2["valuation_uncertainty"]["score"] in ("moderate", "high")
    assert "method_dispersion" in d2["valuation_uncertainty"]["drivers"]


def test_22_sbc_drives_dilution_classification():
    base = dict(OK_IN)
    base.update({"revenue_growth_ttm": 0.30, "eps_growth_ttm": 0.05,
                 "dilution_overhang": 1.0, "sbc_to_revenue_ttm": 0.08})
    d = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
               [_mr(120.0, inputs=base), _mr(122.0, inputs=base)])
    assert d["earnings_quality"]["classification"] == "divergence_dilution"


# ---------------- 23. scenario degeneracy + NBIS audit regressions ----

def test_23_scenario_degenerate_flagged_when_upside_collapses():
    # bear < base == bull — the NBIS signature: expected value biased low
    scen, flags = enforce_scenario_order(
        {"bear": 40.0, "base": 70.0, "bull": 70.0, "explosive": 75.0})
    assert "scenario_degenerate" in flags
    # distinct upside → no flag
    scen, flags = enforce_scenario_order(
        {"bear": 40.0, "base": 70.0, "bull": 90.0, "explosive": 110.0})
    assert "scenario_degenerate" not in flags
    # flat everywhere incl. bear is a different pathology — not this flag
    scen, flags = enforce_scenario_order(
        {"bear": 70.0, "base": 70.0, "bull": 70.0, "explosive": 75.0})
    assert "scenario_degenerate" not in flags


def test_23_ev_sales_growth_differentiates_at_g_saturation():
    # revenue growth far above g_cap used to give base == bull (NBIS).
    # Revenue-axis shocks must keep bear < base < bull < explosive.
    s = dict(BASE, revenue_growth_ttm=6.0, revenue_forward=3.3e9,
             revenue_ttm=5.3e8, net_profit_margin_ttm=-0.5,
             net_profit_margin_midcycle=0.10, operating_margin_ttm=-0.4,
             fcf_ttm=-1.0e9)
    out = _eval("ev_sales_growth", s)
    assert out["bear"] < out["base"] < out["bull"] < out["explosive"]


def test_23_ev_sales_fintech_differentiates_at_g_saturation():
    s = dict(BASE, revenue_growth_ttm=4.0)
    out = _eval("ev_sales_fintech", s)
    assert out["bear"] < out["base"] < out["bull"] < out["explosive"]


def test_23_forward_revenue_inflation_flagged_not_silent():
    # forward sales base running >3x trailing is ARR-flavoured
    # extrapolation — a flag_* binding that must surface in metrics
    s = dict(BASE, revenue_forward=4.0e10, revenue_ttm=1.0e10)
    scen, metrics = evaluate_scenarios(
        REG.get("ev_sales_growth").formula, scalars=s,
        params=dict(REG.get("ev_sales_growth").params or {}),
        validations=list(REG.get("ev_sales_growth").validations or []))
    assert "forward_revenue_inflated" in (metrics.get("flags") or [])
    # 2.5x forward — under the bound, no flag
    s2 = dict(BASE, revenue_forward=2.5e10, revenue_ttm=1.0e10)
    _, metrics2 = evaluate_scenarios(
        REG.get("ev_sales_growth").formula, scalars=s2,
        params=dict(REG.get("ev_sales_growth").params or {}),
        validations=list(REG.get("ev_sales_growth").validations or []))
    assert "forward_revenue_inflated" not in (metrics2.get("flags") or [])


def test_23_new_flags_charge_mos_and_uncertainty():
    s = dict(OK_IN)
    d = decide("ai_infra", 70.0, 61.0, {"bear": 40.0, "base": 70.0,
                                      "bull": 70.0, "explosive": 75.0},
               ["scenario_degenerate", "forward_revenue_inflated",
                "single_method"], 100.0, [_mr(70.0, inputs=s)],
               scalars=s)
    applied = set(d.get("mos_adders") or [])
    assert {"scenario_degenerate", "forward_revenue_inflated",
            "single_method"} <= applied
    assert "scenario_degenerate" in d["valuation_uncertainty"]["drivers"]
    assert "single_method" in d["valuation_uncertainty"]["drivers"]
    assert "forward_revenue_inflated" in d["business_uncertainty"]["drivers"]
