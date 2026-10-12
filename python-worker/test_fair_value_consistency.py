"""Fair-value consistency tests.

Covers the three fixes that keep the API response internally coherent:
1. Rating thresholds match the effective fair value.
2. v1/v2 merge recomputes ratio/rating (no stale v1 metrics after override).
3. The swing-path bridge uses the same effective (v2) fair value the API returns.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.fair_value_service import FairValueService


class TestRatingThresholds:
    svc = FairValueService()

    @pytest.mark.parametrize("ratio,expected", [
        (0.50, "Deeply Undervalued"),
        (0.69, "Deeply Undervalued"),
        (0.70, "Undervalued"),
        (0.84, "Undervalued"),
        (0.85, "Slightly Undervalued"),
        (0.97, "Slightly Undervalued"),
        (1.00, "Fair Value"),
        (1.03, "Fair Value"),
        (1.14, "Fair Value"),
        (1.15, "Slightly Overvalued"),
        (1.29, "Slightly Overvalued"),
        (1.30, "Overvalued"),
    ])
    def test_thresholds(self, ratio, expected):
        assert self.svc._get_valuation_rating(ratio) == expected

    def test_small_discount_is_not_deeply_undervalued(self):
        # The observed bug: price/FV = 0.968 was labelled "Deeply Undervalued".
        assert self.svc._get_valuation_rating(0.968) == "Slightly Undervalued"


class TestCalibrateRating:
    svc = FairValueService()

    def test_high_dispersion_softens_deeply(self):
        out = self.svc._calibrate_rating(
            "Deeply Undervalued", confidence_score=50, high_dispersion=True
        )
        assert out.startswith("Undervalued")
        assert "unverified" in out

    def test_low_confidence_annotates(self):
        out = self.svc._calibrate_rating(
            "Undervalued", confidence_score=20, high_dispersion=False
        )
        assert "unverified" in out

    def test_fair_value_untouched(self):
        assert self.svc._calibrate_rating(
            "Fair Value", confidence_score=10, high_dispersion=True
        ) == "Fair Value"


class TestApplyV2Override:
    def _result(self):
        return SimpleNamespace(
            fair_value=445.0,
            current_price=222.27,
            individual_valuations={"dcf_simple": 800.0},
            valuation_metrics={
                "valuation_ratio": 0.47,
                "undervaluation_pct": 53.0,
                "valuation_rating": "Deeply Undervalued",
            },
        )

    def _v2(self):
        return SimpleNamespace(
            fair_value=216.37,
            scenario_fair_values={"bear": 171.9, "base": 216.37, "bull": 273.9},
            regime="ai_infra:mega_cap_high_growth",
            method_results=[SimpleNamespace(method_key="peg_corrected")],
        )

    def test_recomputes_ratio_and_rating(self):
        from app.api.fundamentals_api import _apply_v2_override
        result = self._result()
        _apply_v2_override(result, self._v2())
        vm = result.valuation_metrics
        assert result.fair_value == pytest.approx(216.37)
        assert vm["valuation_ratio"] == pytest.approx(222.27 / 216.37)
        assert vm["undervaluation_pct"] == pytest.approx((1 - 222.27 / 216.37) * 100)
        # price slightly above fair value -> Fair Value, not Deeply Undervalued
        assert vm["valuation_rating"] == "Fair Value"

    def test_surfaces_band_and_model(self):
        from app.api.fundamentals_api import _apply_v2_override
        result = self._result()
        _apply_v2_override(result, self._v2())
        vm = result.valuation_metrics
        assert vm["fair_value_model"] == "fair_value_v2.peg_corrected"
        assert vm["v2_regime"] == "ai_infra:mega_cap_high_growth"
        assert vm["scenario_fair_values"]["bull"] == pytest.approx(273.9)
        assert result.individual_valuations["peg_corrected_v2"] == pytest.approx(216.37)


class TestFairValueBridge:
    def _v2(self):
        return SimpleNamespace(
            fair_value=216.37,
            scenario_fair_values={"bear": 171.9, "base": 216.37, "bull": 273.9},
            regime="ai_infra:mega_cap_high_growth",
        )

    def test_v2_preferred_when_enabled(self):
        from app.fundamental_intelligence import fair_value_bridge as bridge
        with patch.object(bridge, "ENABLE_FAIR_VALUE_V2", True), \
             patch("app.fair_value_v2.resolver.FairValueV2Resolver") as res, \
             patch("app.services.fair_value_service.FairValueService") as svc1:
            res.return_value.resolve.return_value = (self._v2(), {"reused": True, "run_as_of": "t"})
            band = bridge.resolve_fair_value_band("nvda")
        assert band["source"] == "fair_value_v2"
        assert band["fair_value_base"] == pytest.approx(216.37)
        assert band["fair_value_bear"] == pytest.approx(171.9)
        assert band["fair_value_bull"] == pytest.approx(273.9)
        assert band["v2_regime"] == "ai_infra:mega_cap_high_growth"
        svc1.return_value.calculate_fair_value.assert_not_called()

    def test_falls_back_to_v1_when_v2_empty(self):
        from app.fundamental_intelligence import fair_value_bridge as bridge
        v1_result = SimpleNamespace(
            fair_value=180.0,
            valuation_metrics={"dcf_simple": {"scenarios": {
                "bear": {"fair_price": 140.0}, "bull": {"fair_price": 220.0}}}},
        )
        with patch.object(bridge, "ENABLE_FAIR_VALUE_V2", True), \
             patch("app.fair_value_v2.resolver.FairValueV2Resolver") as res, \
             patch("app.services.fair_value_service.FairValueService") as svc1:
            res.return_value.resolve.return_value = (SimpleNamespace(fair_value=None), {})
            svc1.return_value.calculate_fair_value.return_value = v1_result
            band = bridge.resolve_fair_value_band("XYZ")
        assert band["source"] == "fair_value_engine_v1"
        assert band["fair_value_base"] == pytest.approx(180.0)
        assert band["fair_value_bear"] == pytest.approx(140.0)

    def test_none_when_engines_fail(self):
        from app.fundamental_intelligence import fair_value_bridge as bridge
        with patch.object(bridge, "ENABLE_FAIR_VALUE_V2", False), \
             patch("app.services.fair_value_service.FairValueService") as svc1:
            svc1.return_value.calculate_fair_value.side_effect = RuntimeError("no data")
            assert bridge.resolve_fair_value_band("XYZ") is None
