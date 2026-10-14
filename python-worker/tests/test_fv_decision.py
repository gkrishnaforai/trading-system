"""FV v2 decision layer — end-to-end guarantees.

A method can be individually correct and the ensemble still wrong:
stale data, negative FCF, wide dispersion, or an absent fair value must
never produce an accumulable decision. These tests pin the contract.
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.fair_value_v2.decision import decide  # noqa: E402


def _mr(fv=None, status="ok", inputs=None):
    return {"method_key": "m", "status": status, "fair_price": fv,
            "inputs_used": inputs or {}, "metrics": {}}


SCEN = {"bear": 80.0, "base": 120.0, "bull": 160.0, "explosive": 190.0}
OK_INPUTS = {"fcf_ttm": 2e9, "total_debt": 1e9, "cash_and_equivalents": 5e9,
             "analyst_count": 25, "net_income_ttm": 3e9,
             "cash_conversion": 1.1, "dilution_overhang": 1.01}


def test_all_methods_missing_never_produces_gate():
    d = decide("technology", None, None, {}, [],
               100.0, [_mr(status="missing_data"),
                       _mr(status="missing_data")])
    assert d["buy_below"] is None
    assert d["valuation_confidence"] == "low"
    assert "no_fair_value" in d["risk_flags"]


def test_zero_or_negative_fv_never_produces_gate():
    d = decide("technology", 0.0, None, {}, [], 100.0,
               [_mr(fv=None, status="missing_data")])
    assert d["buy_below"] is None


def test_negative_fcf_priced_as_uncertainty():
    inputs = {**OK_INPUTS, "fcf_ttm": -1e9}
    d = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
               [_mr(110.0, inputs=inputs), _mr(130.0, inputs={})])
    assert "negative_fcf" in d["mos_adders"]


def test_wide_method_dispersion_caps_confidence():
    # peg at $477 vs dcf at $146 on a $228 spot → 145% dispersion
    mrs = [_mr(477.0, inputs=OK_INPUTS), _mr(146.0), _mr(172.0)]
    d = decide("ai_infra", 258.0, 264.0, SCEN, [], 228.52, mrs)
    assert d["valuation_confidence"] == "low"
    assert d["method_dispersion"] is not None
    assert "method_dispersion" in d["mos_adders"]


def test_tight_methods_keep_high_confidence():
    mrs = [_mr(118.0, inputs=OK_INPUTS), _mr(122.0), _mr(125.0)]
    d = decide("technology", 120.0, 122.0, SCEN, [], 100.0, mrs)
    assert d["valuation_confidence"] == "high"
    assert "method_dispersion" not in d["mos_adders"]


def test_leverage_adder_still_wired():
    inputs = {**OK_INPUTS, "total_debt": 20e9, "cash_and_equivalents": 5e9}
    d = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
               [_mr(120.0, inputs=inputs), _mr(122.0)])
    assert "high_leverage" in d["mos_adders"]


def test_dilution_and_accrual_adders():
    inputs = {**OK_INPUTS, "dilution_overhang": 1.08,
              "cash_conversion": 0.4}
    d = decide("technology", 120.0, 122.0, SCEN, [], 100.0,
               [_mr(120.0, inputs=inputs), _mr(122.0)])
    assert "share_dilution" in d["mos_adders"]
    assert "weak_cash_conversion" in d["mos_adders"]


def test_bear_loss_and_mos_gates():
    severe = {**SCEN, "bear": 50.0}  # −50% vs spot 100
    d = decide("pre_earnings", 120.0, 120.0, severe, [], 100.0,
               [_mr(120.0, inputs={**OK_INPUTS, "analyst_count": None})])
    assert "bear_loss_severe" in d["risk_flags"]
    assert d["buy_below"] is not None  # gate exists but deeply discounted


def test_uninvestable_mos_flags_instead_of_gating():
    # enough adders to hit the 0.60 cap → flagged uninvestable
    inputs = {"fcf_ttm": -1e9, "total_debt": 20e9, "cash_and_equivalents": 1e9,
              "analyst_count": None, "dilution_overhang": 1.10,
              "cash_conversion": 0.3, "net_income_ttm": 1e9}
    mrs = [_mr(477.0, inputs=inputs), _mr(146.0), _mr(172.0)]
    d = decide("pre_earnings", 258.0, 264.0, SCEN,
               ["no_scenarios", "extreme_gap"], 228.52, mrs,
               demand={"capital_funding_risk": "critical"})
    assert "uninvestable_mos" in d["risk_flags"]


def test_decision_never_exceeds_cap():
    d = decide("pre_earnings", 100.0, 100.0, SCEN, [], 100.0,
               [_mr(100.0, inputs={"fcf_ttm": -1e9, "analyst_count": None})])
    assert d["mos_pct"] <= 0.60


# --- method-level validity contract -------------------------------

def test_validation_rejects_bad_input_not_null():
    from app.fair_value_v2.dsl.evaluator import evaluate_scenarios, DslError
    import pytest
    with pytest.raises(DslError) as e:
        evaluate_scenarios(
            {"fair_price": {"mul": [{"var": "eps_ttm"}, 10]}},
            scalars={"eps_ttm": 5.0}, params={},
            validations=[{"name": "always_on",
                          "when": {"gt": [{"var": "eps_ttm"}, 0]},
                          "reason": "test_rule"}])
    assert e.value.code == "invalid_input"


def test_non_finite_and_absurd_fv_rejected():
    import pytest
    from app.fair_value_v2.dsl.evaluator import evaluate_scenarios, DslError
    with pytest.raises(DslError):
        evaluate_scenarios(
            {"fair_price": {"div": [{"var": "x"}, 0]}},
            scalars={"x": 1.0}, params={})
    with pytest.raises(DslError) as e:
        evaluate_scenarios(
            {"fair_price": {"var": "x"}},
            scalars={"x": 1e9}, params={})
    assert e.value.code == "invalid_assumption"
