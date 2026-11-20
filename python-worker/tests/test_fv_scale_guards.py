"""FV v2 scale-guard regression tests — per-share scale sanity,
negative-margin glidepath, category growth cap.

The bug class: a provider per-share datum on the wrong scale
(KZT EPS vs a USD ADR, parent fundamentals on a $25 preferred,
stale share count after a split) produced absurd fair values —
KSPI read $340k, MGRE $896 on a $20 instrument. The engine must
abstain with a warning, never multiply a lie.

Synthetic scalars only — no DB. YAMLs load from disk so tests pin
the shipped contract.
"""
import os
from datetime import datetime, timezone

import pytest
import yaml

from app.fair_value_v2.dsl.evaluator import evaluate_scenarios
from app.fair_value_v2.runner import FairValueRunner

DEFS = os.path.join(os.path.dirname(__file__), "..",
                    "app", "fair_value_v2", "methods", "definitions")
FEATS = os.path.join(os.path.dirname(__file__), "..",
                     "app", "fair_value_v2", "methods", "features.yaml")
TRAJ = yaml.safe_load(open(os.path.join(DEFS, "eps_trajectory.yaml")))
MEGA = yaml.safe_load(open(os.path.join(DEFS, "dcf_mega_cap.yaml")))


def _traj(scalars, **params):
    p = dict(TRAJ["params"]); p.update(params)
    return evaluate_scenarios(TRAJ["formula"], scalars=scalars, params=p)


# ---------------------------------------------------------- margin glidepath

NEG_MARGIN = dict(revenue_ttm=1.0e9, shares_outstanding=100e6,
                  revenue_growth_ttm=0.40,
                  net_profit_margin_ttm=-0.05)


class TestMarginGlidepath:
    """A negative-margin anchor must not hold 2% forever — the
    trajectory recovers margin_recovery of the gap to the cap.
    Bear stays floored (no recovery in the bad case)."""

    def test_negative_anchor_base_recovers(self):
        sc, _ = _traj(NEG_MARGIN)
        flat, _ = _traj(NEG_MARGIN, margin_recovery=0.0)
        assert sc["base"] > flat["base"]

    def test_negative_anchor_bear_holds_floor(self):
        sc, _ = _traj(NEG_MARGIN)
        flat, _ = _traj(NEG_MARGIN, margin_recovery=0.0)
        assert sc["bear"] == pytest.approx(flat["bear"], rel=1e-9)

    def test_positive_anchor_unchanged(self):
        scalars = dict(NEG_MARGIN, net_profit_margin_ttm=0.12)
        sc, _ = _traj(scalars)
        # positive anchors clamp to themselves — same as before the fix
        flat, _ = _traj(scalars, margin_recovery=0.0)
        assert sc["base"] == pytest.approx(flat["base"], rel=1e-9)


# ---------------------------------------------------------- category growth cap

class TestCategoryGrowthCap:
    def test_ai_infra_cap_exceeds_default(self):
        p = MEGA["params"]
        assert p.get("growth_cap_ai_infra", 0) > p["growth_cap"]


# ---------------------------------------------------------- per-share sanity

class _StubResolver:
    def __init__(self, scalars):
        self._scalars = scalars

    def resolve_scalars(self, symbol, as_of_ts, required):
        return dict(self._scalars), {}, {}


TS = datetime(2025, 1, 15, tzinfo=timezone.utc)


def _runner(scalars):
    r = FairValueRunner.__new__(FairValueRunner)
    r.feature_resolver = _StubResolver(scalars)
    r._fx_notes = {}
    r._sanity_flags = None
    return r


class TestPerShareSanity:
    """The verdict is per-symbol, applied to every feature dict —
    methods that never request EPS must still lose suspect shares."""

    KSPI = dict(spot_price=90.0, market_cap=20e9,
                eps_forward=6803.0,           # KZT EPS vs USD ADR
                eps_ttm=6000.0, shares_outstanding=220e6)

    MGRE = dict(spot_price=20.0, market_cap=17e9,
                eps_ttm=22.0,                 # parent EPS on a pref
                shares_outstanding=60e6)      # parent share count —
                # implied_sh=850m vs 60m → ratio ~14 (prod read 14.31)

    HEALTHY = dict(spot_price=100.0, market_cap=50e9,
                   eps_forward=5.0, eps_ttm=4.5,
                   shares_outstanding=500e6)

    def test_currency_scale_flags_and_nulls_eps(self):
        r = _runner(dict(self.KSPI))
        scalars, _, _ = r.feature_resolver.resolve_scalars(
            "KSPI", TS, list(self.KSPI))
        flags = r._sanity_verdict("KSPI", TS, scalars)
        assert any("per_share_scale_suspect" in f for f in flags)

    def test_share_count_suspect_nulls_shares_for_all_dicts(self):
        r = _runner(dict(self.MGRE))
        row = r._get_features_for_requires(
            "MGRE", TS, ["shares_outstanding", "fcf_ttm"])
        # shares nulled even though this dict never asked for EPS
        assert row.scalars.get("shares_outstanding") is None

    def test_eps_suspect_kills_eps_in_dict(self):
        r = _runner(dict(self.KSPI))
        row = r._get_features_for_requires(
            "KSPI", TS, ["eps_forward", "eps_ttm"])
        assert row.scalars.get("eps_forward") is None
        assert row.scalars.get("eps_ttm") is None

    def test_healthy_scalars_untouched(self):
        r = _runner(dict(self.HEALTHY))
        row = r._get_features_for_requires(
            "NVDA", TS, list(self.HEALTHY))
        assert row.scalars["eps_forward"] == 5.0
        assert row.scalars["shares_outstanding"] == 500e6
        assert not r._sanity_flags

    def test_verdict_computed_once(self):
        r = _runner(dict(self.MGRE))
        scalars, _, _ = r.feature_resolver.resolve_scalars(
            "MGRE", TS, [])
        f1 = r._sanity_verdict("MGRE", TS, scalars)
        f2 = r._sanity_verdict("MGRE", TS, {})
        assert f1 == f2 and f1


# ---------------------------------------------------------- filing-grounded TTM

class TestFilingGroundedTtm:
    """Provider TTM fields can hold a single quarter's EPS — SMCI's
    netIncomePerShareTTM read 1.68 (one quarter) vs the real 4.75,
    blowing derived forward_growth to 238% and fv to $218 on a $24
    stock. eps_ttm/net_income_ttm must prefer the filing sum, and the
    derived growth legs must consume the canonical feature."""

    def test_eps_ttm_prefers_filing_sum(self):
        feats = yaml.safe_load(open(FEATS))
        src0 = feats["features"]["eps_ttm"]["sources"][0]
        assert src0["type"] == "table_column_sum"
        assert src0["table"] == "fundamental_quarterly"
        assert src0["column"] == "eps_diluted"
        assert src0["rows"] == 4 and src0["min_rows"] == 4

    def test_net_income_ttm_prefers_filing_sum(self):
        feats = yaml.safe_load(open(FEATS))
        src0 = feats["features"]["net_income_ttm"]["sources"][0]
        assert src0["type"] == "table_column_sum"
        assert src0["column"] == "net_income"

    def test_derived_growth_uses_canonical_eps_ttm(self):
        feats = yaml.safe_load(open(FEATS))
        fg = feats["features"]["forward_growth"]
        d = [s for s in fg["sources"] if s.get("type") == "derived"][0]
        assert d["params"]["eps_ttm"]["type"] == "feature_ref"
        assert d["params"]["eps_ttm"]["name"] == "eps_ttm"

    def test_sum_columns_allowlisted(self):
        feats = yaml.safe_load(open(FEATS))
        cols = feats["allow_table_columns"]["fundamental_quarterly"]["columns"]
        assert "eps_diluted" in cols and "net_income" in cols

    def test_min_rows_rejects_partial_ttm(self):
        from app.fair_value_v2.feature_store.postgres_point_in_time import \
            PostgresPointInTimeFeatureStore
        store = PostgresPointInTimeFeatureStore.__new__(
            PostgresPointInTimeFeatureStore)

        class _Sess:
            def execute(self, *_a, **_k):
                class R:
                    def fetchall(self):
                        return [(0.5, "2025-01-01"), (0.4, "2024-10-01")]
                return R()
            def __enter__(self): return self
            def __exit__(self, *a): return False

        class _DB:
            def get_session(self): return _Sess()
        store._get_symbol_column = lambda s, t: "symbol"
        store._has_currency_column = lambda s, t: False

        import app.fair_value_v2.feature_store.postgres_point_in_time as m
        old = m.db
        m.db = _DB()
        try:
            from datetime import datetime
            v, ts, ccy = store.get_table_column_sum(
                "X", datetime(2025, 6, 1), "t", "c", "d", "d",
                limit=4, min_rows=4)
            assert v is None            # 2 rows < min_rows 4 → reject
            v, ts, ccy = store.get_table_column_sum(
                "X", datetime(2025, 6, 1), "t", "c", "d", "d",
                limit=4, min_rows=2)
            assert v == pytest.approx(0.9)
        finally:
            m.db = old
