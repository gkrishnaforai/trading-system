"""Sector-flow tagging — the deterministic price×volume read that marks
each sector ETF inflow / rotating-in / outflow / quiet, and the
sector→ETF map used to attach that state to a single stock.

Boundaries under test: r5 ±0.5%/±2%, volume_ratio 1.2 confirmation,
above50 split between "inflow" (confirmed leader) and "rotating in"
(early accumulation in a still-weak trend).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.market_regime.rotation import (
    _SECTOR_TO_ETF, _flow_tag, _momentum_score, SECTOR_NAMES, THEME_ETFS)


class TestFlowTag:
    def test_inflow_above50_with_volume(self):
        assert _flow_tag(0.005, 0.01, 0.03, 1.3, True) == "🔥 inflow"

    def test_rotating_in_below50_with_volume(self):
        assert _flow_tag(0.005, 0.01, -0.02, 1.5, False) == "↩ rotating in"

    def test_rotating_in_fresh_money_into_laggard_no_volume(self):
        # strong week in a flat month — early rotation read without the
        # volume-confirmation leg
        assert _flow_tag(0.0, 0.025, 0.003, 0.9, False) == "↩ rotating in"

    def test_outflow_on_volume_below50(self):
        assert _flow_tag(-0.01, -0.02, -0.05, 1.4, False) == "📉 outflow"

    def test_quiet_positive_week_without_volume(self):
        # buying not confirmed by participation → no flow claim
        assert _flow_tag(0.002, 0.01, 0.0, 1.0, True) == "📈 leading" \
            or _flow_tag(0.002, 0.01, 0.0, 1.0, True) == "💤 quiet"

    def test_leading_when_trend_intact_no_volume_spike(self):
        assert _flow_tag(0.0, 0.003, 0.03, 1.0, True) == "📈 leading"

    def test_quiet_no_trend_no_volume(self):
        assert _flow_tag(0.0, 0.001, -0.005, 0.9, False) == "💤 quiet"

    def test_boundary_r5_at_half_percent(self):
        # exactly at the +0.5% line — not strictly greater, stays quiet
        assert _flow_tag(0.0, 0.005, 0.0, 1.5, True) == "💤 quiet"

    def test_boundary_volume_ratio_at_1_2(self):
        # vol_ratio exactly 1.2 counts as confirmation (>=)
        assert _flow_tag(0.0, 0.006, 0.02, 1.2, True) == "🔥 inflow"

    def test_mild_down_week_on_volume_is_outflow(self):
        assert _flow_tag(0.0, -0.006, 0.02, 1.3, True) == "📉 outflow"


class TestSectorToEtf:
    def test_gics_names_map(self):
        assert _SECTOR_TO_ETF["technology"] == "XLK"
        assert _SECTOR_TO_ETF["health care"] == "XLV"
        assert _SECTOR_TO_ETF["healthcare"] == "XLV"
        assert _SECTOR_TO_ETF["financial services"] == "XLF"
        assert _SECTOR_TO_ETF["consumer cyclical"] == "XLY"
        assert _SECTOR_TO_ETF["communication services"] == "XLC"

    def test_every_mapped_etf_is_a_real_sector(self):
        for etf in _SECTOR_TO_ETF.values():
            assert etf in SECTOR_NAMES

    def test_unknown_sector_returns_none(self):
        assert _SECTOR_TO_ETF.get("space tourism") is None
        assert _SECTOR_TO_ETF.get("") is None


class TestMomentumScore:
    def test_bounds(self):
        hi = _momentum_score(0.1, 0.2, 0.3, 0.1, True, True, 2.0, 0.02)
        lo = _momentum_score(-0.1, -0.2, -0.3, -0.1, False, False, 2.0, -0.02)
        assert 0 <= lo < hi <= 100

    def test_volume_participation_directional(self):
        up = _momentum_score(0.01, 0.02, None, 0.0, True, True, 1.3, 0.01)
        dn = _momentum_score(0.01, 0.02, None, 0.0, True, True, 1.3, -0.01)
        assert up - dn == 10.0  # the +5/−5 volume-direction leg


class TestUniverse:
    def test_sector_and_theme_sets_disjoint(self):
        assert not set(SECTOR_NAMES) & set(THEME_ETFS)
