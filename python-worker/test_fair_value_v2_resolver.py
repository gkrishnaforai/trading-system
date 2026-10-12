"""Fair-value v2 resolver reuse-policy tests.

Fair value is price-independent, so a stored run stays valid until its inputs
change or the max-age floor is hit. These tests pin that decision logic.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.fair_value_v2.resolver import FairValueV2Resolver

NOW = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)


def _result(symbol="NVDA", fv=216.37):
    return SimpleNamespace(
        run_id="new-run-1",
        symbol=symbol,
        as_of_ts=NOW,
        fair_value=fv,
        scenario_fair_values={"base": fv, "bear": 170.0, "bull": 275.0},
        regime="ai_infra:mega_cap_high_growth",
        method_results=[],
        features_hash="abc123",
        warnings=[],
    )


def _stored_run(watermark, as_of=None):
    return {
        "run_id": "stored-run-1",
        "symbol": "NVDA",
        "as_of": as_of or NOW - timedelta(hours=2),
        "inputs_watermark": watermark,
        "features_hash": "abc123",
        "fair_value": 216.37,
        "scenario_fair_values": {"base": 216.37, "bear": 170.0, "bull": 275.0},
        "regime": "ai_infra:mega_cap_high_growth",
        "method_results": [],
        "warnings": [],
        "model_version": "fair_value_v2",
    }


@pytest.fixture
def resolver():
    svc = MagicMock()
    svc.calculate.return_value = _result()
    r = FairValueV2Resolver(service=svc)
    r._service = svc
    r._persist = MagicMock()
    r._active_override = MagicMock(return_value=None)
    return r


def _override(fv=250.0):
    return {
        "symbol": "NVDA",
        "fair_value": fv,
        "bear_fair_value": 200.0,
        "bull_fair_value": 310.0,
        "regime": "ai_infra:mega_cap_high_growth",
        "reason": "operator review",
        "updated_by": "tester",
        "updated_at": NOW,
    }


class TestReuse:
    def test_reuses_when_inputs_unchanged(self, resolver):
        wm = NOW - timedelta(hours=1)
        resolver._latest_run = MagicMock(return_value=_stored_run(watermark=wm))
        resolver._inputs_watermark = MagicMock(return_value=wm)

        result, meta = resolver.resolve("nvda")

        assert meta["reused"] is True
        assert meta["reason"] == "inputs_unchanged"
        assert meta["run_id"] == "stored-run-1"
        assert result.fair_value == pytest.approx(216.37)
        resolver._service.calculate.assert_not_called()
        resolver._persist.assert_not_called()

    def test_reuses_when_no_input_data_tracked(self, resolver):
        resolver._latest_run = MagicMock(
            return_value=_stored_run(watermark=None)
        )
        resolver._inputs_watermark = MagicMock(return_value=None)

        _, meta = resolver.resolve("NVDA")

        assert meta["reused"] is True

    def test_recomputes_when_inputs_changed(self, resolver):
        stored_wm = NOW - timedelta(hours=5)
        newer_wm = NOW - timedelta(minutes=10)  # estimate revision landed
        resolver._latest_run = MagicMock(return_value=_stored_run(watermark=stored_wm))
        resolver._inputs_watermark = MagicMock(return_value=newer_wm)

        result, meta = resolver.resolve("NVDA")

        assert meta["reused"] is False
        assert meta["reason"] == "inputs_changed"
        resolver._service.calculate.assert_called_once()
        resolver._persist.assert_called_once()

    def test_recomputes_when_run_exceeds_max_age(self, resolver):
        wm = NOW - timedelta(hours=3)
        old_run = _stored_run(watermark=wm, as_of=NOW - timedelta(days=2))
        resolver._latest_run = MagicMock(return_value=old_run)
        resolver._inputs_watermark = MagicMock(return_value=wm)

        _, meta = resolver.resolve("NVDA")

        assert meta["reused"] is False
        resolver._service.calculate.assert_called_once()

    def test_recomputes_when_no_prior_run(self, resolver):
        resolver._latest_run = MagicMock(return_value=None)
        resolver._inputs_watermark = MagicMock(return_value=NOW)

        _, meta = resolver.resolve("NVDA")

        assert meta["reused"] is False
        assert meta["reason"] == "no_prior_run"
        resolver._service.calculate.assert_called_once()

    def test_force_bypasses_reuse(self, resolver):
        wm = NOW - timedelta(hours=1)
        resolver._latest_run = MagicMock(return_value=_stored_run(watermark=wm))
        resolver._inputs_watermark = MagicMock(return_value=wm)

        _, meta = resolver.resolve("NVDA", force=True)

        assert meta["reused"] is False
        assert meta["reason"] == "forced"
        resolver._service.calculate.assert_called_once()

    def test_no_persist_when_engine_returns_no_fair_value(self, resolver):
        resolver._latest_run = MagicMock(return_value=None)
        resolver._inputs_watermark = MagicMock(return_value=None)
        resolver._service.calculate.return_value = _result(fv=None)

        _, meta = resolver.resolve("NVDA")

        resolver._persist.assert_not_called()

    def test_recomputes_when_stored_run_has_no_fair_value(self, resolver):
        bad = _stored_run(watermark=NOW)
        bad["fair_value"] = None
        resolver._latest_run = MagicMock(return_value=bad)
        resolver._inputs_watermark = MagicMock(return_value=NOW)

        _, meta = resolver.resolve("NVDA")

        assert meta["reused"] is False
        resolver._service.calculate.assert_called_once()


class TestUserOverride:
    def test_override_wins_over_stored_run(self, resolver):
        resolver._active_override = MagicMock(return_value=_override())
        resolver._latest_run = MagicMock(return_value=_stored_run(watermark=NOW))
        resolver._inputs_watermark = MagicMock(return_value=NOW)

        result, meta = resolver.resolve("NVDA")

        assert result.fair_value == 250.0
        assert result.model_version == "user_override"
        assert meta["reason"] == "user_override"
        resolver._service.calculate.assert_not_called()
        resolver._persist.assert_not_called()

    def test_override_wins_over_force(self, resolver):
        resolver._active_override = MagicMock(return_value=_override())

        result, meta = resolver.resolve("NVDA", force=True)

        assert result.fair_value == 250.0
        assert meta["source"] == "user_override"
        resolver._service.calculate.assert_not_called()

    def test_override_band_and_provenance(self, resolver):
        resolver._active_override = MagicMock(return_value=_override())

        result, meta = resolver.resolve("NVDA")

        assert result.scenario_fair_values == {"bear": 200.0, "bull": 310.0}
        assert result.run_id == "override:NVDA"
        assert meta["reused"] is True
        assert result.warnings[0]["code"] == "user_override"

    def test_no_override_falls_through_to_engine(self, resolver):
        resolver._latest_run = MagicMock(return_value=None)
        resolver._inputs_watermark = MagicMock(return_value=None)

        result, meta = resolver.resolve("NVDA")

        assert result.fair_value == 216.37
        assert meta["reason"] == "no_prior_run"


class TestDatetimeCoercion:
    def test_date_coerced_to_utc_midnight(self):
        from datetime import date
        out = FairValueV2Resolver._as_datetime(date(2026, 9, 19))
        assert out == datetime(2026, 9, 19, tzinfo=timezone.utc)

    def test_naive_datetime_gets_utc(self):
        out = FairValueV2Resolver._as_datetime(datetime(2026, 9, 19, 8, 30))
        assert out.tzinfo == timezone.utc
