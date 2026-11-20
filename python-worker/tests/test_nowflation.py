"""Nowflation integration tests — fetch decomposition, journal
idempotency, fed-path inflation score, CPI-event enrichment.

The contract being pinned: the flat JSON files decompose into
nowflation_daily columns correctly (the DISPLAYED call is
official_projection[0].yoy — the model-only number lives at
forecast[0].central and must not leak into the display field), the
gauge maps onto the macro_snapshots 0-100 scale in the right
direction (high gauge → low score), and CPI events only pick up an
expected value when the release month covers the forecast month.
"""
import json
from datetime import date

import pytest

import app.database as appdb
from app.signals import nowflation as nf


# ------------------------------------------------------- live-shape fixtures
# Field names verified against https://nowflation.com/data/*.json —
# keep them honest: the flat-file contract is theirs, not ours.

REALTIME = {
    "today": {
        "record_type": "live",
        "date": "2026-11-20",
        "realtime_yoy_pct": 2.96,
        "realtime_dod_pp": -0.033,
        "realtime_wow_pp": -0.167,
        "cpi_gauge_yoy_pct": 2.95,
        "cpi_gauge_method_version": "gauge_v3.1",
        "official_cpi_yoy_pct": 4.0,
        "official_cpi_month": "2026-10",
        "truflation_yoy_pct": 2.64,
    }
}
FORECAST = {
    "asof": "2026-11-20",
    "model": "nowflation_forecast_v2.1_component",
    "official_projection": [{"month": "2026-11", "yoy": 3.84},
                            {"month": "2026-12", "yoy": 4.02}],
    "official_projection_anchor": {"month": "2026-11", "yoy": 3.84},
    "forecast": [{"month": "2026-11", "central": 3.24,
                  "mom": -0.072, "low": 2.97, "high": 3.51}],
}


def _fetch(monkeypatch):
    monkeypatch.setattr(nf, "_get",
                        lambda u: REALTIME if "realtime" in u else FORECAST)
    return nf.fetch()


# ------------------------------------------------------------- fetch decode

def test_fetch_decomposes_displayed_vs_model(monkeypatch):
    row = _fetch(monkeypatch)
    # displayed headline call is official_projection[0].yoy, NOT the
    # component-model central — the ledger grades the number they
    # actually publish
    assert row["print_forecast_month"] == "2026-11"
    assert row["print_forecast_yoy"] == 3.84
    assert row["model_forecast_yoy"] == 3.24
    assert row["as_of"] == "2026-11-20"
    assert row["cpi_gauge_yoy_pct"] == 2.95
    assert row["official_cpi_yoy_pct"] == 4.0
    assert row["gauge_gap_pp"] == pytest.approx(-1.05, abs=0.01)
    assert row["raw"]["realtime"] is REALTIME


def test_fetch_handles_missing_sections(monkeypatch):
    monkeypatch.setattr(nf, "_get", lambda u: {})
    row = nf.fetch()
    assert row["cpi_gauge_yoy_pct"] is None
    assert row["gauge_gap_pp"] is None
    assert row["print_forecast_yoy"] is None


# ------------------------------------------------------------- score mapping

def test_gauge_to_inflation_score_direction():
    # 0-100 scale, high = low inflation (matches macro_snapshots)
    assert nf.gauge_to_inflation_score(2.0) == pytest.approx(85.0)
    assert nf.gauge_to_inflation_score(4.0) == pytest.approx(25.0)
    assert nf.gauge_to_inflation_score(None) is None
    # clamped ends
    assert nf.gauge_to_inflation_score(0.0) == 100.0
    assert nf.gauge_to_inflation_score(9.0) == 0.0
    # hotter gauge → strictly worse score
    assert (nf.gauge_to_inflation_score(5.0)
            < nf.gauge_to_inflation_score(3.0))


# --------------------------------------------------------------- DB-stubbed

class _DB:
    """In-memory nowflation_daily — enough SQL surface for journal /
    latest without a database."""
    def __init__(self):
        self.rows = {}
        self.updates = []

    def execute_update(self, sql, params=None):
        self.updates.append((sql, params or {}))
        if "nowflation_daily" in sql and "INSERT" in sql:
            p = params
            self.rows[p["a"]] = {
                "as_of": p["a"], "cpi_gauge_yoy_pct": p.get("gy"),
                "print_forecast_month": p.get("pm"),
                "print_forecast_yoy": p.get("py"),
                "official_cpi_yoy_pct": p.get("oy"),
                "official_cpi_month": p.get("om"),
            }
        return 1

    def execute_query(self, sql, params=None):
        if "nowflation_daily" not in sql:
            return []
        if "narrative_claims" in sql:
            return []
        lim = params or {}
        rows = sorted(self.rows.values(),
                      key=lambda r: r["as_of"], reverse=True)
        return [r for r in rows if r["as_of"] <= lim.get("d", "9999")][:1]


@pytest.fixture
def stub_db(monkeypatch):
    db = _DB()
    monkeypatch.setattr(appdb, "db", db)
    return db


def test_journal_idempotent_and_latest(stub_db, monkeypatch):
    row = _fetch(monkeypatch)
    assert nf.journal(row) is True
    # same-day republish updates, doesn't duplicate
    row["cpi_gauge_yoy_pct"] = 3.10
    assert nf.journal(row) is True
    assert len(stub_db.rows) == 1
    got = nf.latest()
    assert got["cpi_gauge_yoy_pct"] == 3.10


def test_journal_rejects_missing_as_of(stub_db):
    assert nf.journal({}) is False
    assert stub_db.rows == {}


def test_inflation_score_from_journal(stub_db, monkeypatch):
    row = _fetch(monkeypatch)
    nf.journal(row)
    assert nf.inflation_score() == pytest.approx(
        nf.gauge_to_inflation_score(2.95))


def test_inflation_score_none_without_row(stub_db):
    assert nf.inflation_score() is None


# ------------------------------------------------------ CPI event enrichment

def test_cpi_event_expected_matches_release_month(stub_db, monkeypatch):
    nf.journal(_fetch(monkeypatch))
    # forecast month 2026-11 → its print releases in Dec 2026
    events = [{"name": "CPI", "kind": "cpi", "date": "2026-12-10",
               "days_away": 20},
              {"name": "FOMC", "kind": "fomc", "date": "2026-12-17",
               "days_away": 27}]
    out = nf.cpi_event_expected(events)
    assert out[0]["expected"] == 3.84
    assert out[0]["expected_source"] == "nowflation"
    assert "expected" not in out[1]          # non-CPI untouched


def test_cpi_event_no_match_wrong_month(stub_db, monkeypatch):
    nf.journal(_fetch(monkeypatch))
    # Jan 2027 release covers Dec 2026 — forecast is for Nov
    events = [{"kind": "cpi", "date": "2027-01-12", "days_away": 53}]
    nf.cpi_event_expected(events)
    assert "expected" not in events[0]


def test_cpi_event_passthrough_no_journal(stub_db):
    events = [{"kind": "cpi", "date": "2026-12-10", "days_away": 20}]
    assert nf.cpi_event_expected(events) == events


# ------------------------------------------------------------------ run()

def test_run_survives_fetch_failure(monkeypatch, stub_db):
    def boom(_u):
        raise ConnectionError("nope")
    monkeypatch.setattr(nf, "_get", boom)
    out = nf.run()
    assert out["fetched"] == 0
    assert "error" in out


def test_run_full_path(stub_db, monkeypatch):
    class _NL:
        emitted = []
        @staticmethod
        def emit(*a, **k):
            _NL.emitted.append((a, k))
            return 1
    import app.signals.narrative_ledger as nl_mod
    monkeypatch.setattr(nl_mod, "emit", _NL.emit)
    _fetch(monkeypatch)
    out = nf.run()
    assert out["journaled"] == 1
    assert out["claims_emitted"] == 2        # gauge claim + forecast claim
    assert out["gauge_yoy"] == 2.95
