"""EDGAR public-data spine — unit tests over the pure logic surface.

DB-touching seams are stubbed with a FakeDB (query-map dispatch) or
monkeypatched at the module attribute — the tests assert the RULES
(duration classes, derivation validation, coverage gate, drivers,
lineage eligibility), not live data.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.signals import edgar_resolver as R
from app.signals import company_health as H
from app.utils import lineage as L


class FakeDB:
    """execute_query dispatches on SQL substrings; updates recorded."""

    def __init__(self, query_map=None):
        self.query_map = query_map or {}
        self.updates: list[tuple] = []
        self.many: list[tuple] = []

    def execute_query(self, sql, params=None):
        for key, val in self.query_map.items():
            if key in sql:
                return val(params) if callable(val) else val
        return []

    def execute_update(self, sql, params=None):
        self.updates.append((sql, params))
        return 1

    def execute_many(self, sql, params_list):
        self.many.append((sql, params_list))
        return len(params_list)


def patch_db(monkeypatch, fake: FakeDB) -> FakeDB:
    """Wire the fake into `from app.database import db` — the lazy
    import inside functions resolves the attribute at call time, so
    setting the module attribute reaches every internal call site."""
    import app.database
    monkeypatch.setattr(app.database, "db", fake)
    return fake


def _obs(start, end, val, fp="Q3", frame=None, filed="2026-11-01",
         accn="0001-26-01", sfid=None, derived=False):
    return {"id": 1, "source_fact_id": sfid or f"sf{val}",
            "accn": accn, "taxonomy": "us-gaap",
            "tag": "T", "unit": "USD", "value": val,
            "period_start": start, "period_end": end,
            "instant": start is None, "fy": 2026, "fp": fp,
            "frame": frame, "form": "10-Q", "filed_at": filed,
            "is_amendment": False, "is_derived": derived,
            "quality_state": "reported"}


# -- duration classification -----------------------------------------------------

@pytest.mark.parametrize("start,end,expect", [
    (None, "2026-09-30", "instant"),
    ("2026-07-01", "2026-09-29", "quarter"),   # 90d
    ("2026-07-01", "2026-09-23", "quarter"),   # 13-wk quarter (84d)
    ("2026-07-01", "2026-10-06", "quarter"),   # 14-wk quarter (97d)
    ("2026-08-25", "2026-09-30", "short"),     # transition stub
    ("2026-04-01", "2026-09-30", "half"),      # 182d
    ("2026-01-01", "2026-09-30", "nine_month"),# 273d YTD
    ("2025-10-01", "2026-09-30", "annual"),    # 365d
    ("2025-09-28", "2026-10-02", "annual"),    # 53-wk fiscal year
])
def test_dur_class_bands(start, end, expect):
    assert R._dur_class({"period_start": start, "period_end": end,
                         "instant": start is None}) == expect


# -- resolver vintage ------------------------------------------------------------

def test_resolve_fact_latest_vs_as_of(monkeypatch):
    """latest_known_value folds restatements; as_known_at(t) can't
    see facts filed after t — the backtest-honesty contract."""
    early = _obs("2026-07-01", "2026-09-30", 100, filed="2026-11-01")
    late = _obs("2026-07-01", "2026-09-30", 140, filed="2027-02-01",
                sfid="restated")
    monkeypatch.setattr(R, "_obs",
                        lambda *a, **k: [late, early])

    cur = R.resolve_fact("CIK", ("T",), "USD", "2026-09-30")
    assert cur["value"] == 140
    assert cur["originally_reported"] == 100   # original stays visible

    def fake_obs(cik, tags, unit, pe, as_of=None):
        return [o for o in (late, early)
                if as_of is None or str(o["filed_at"]) <= as_of]
    monkeypatch.setattr(R, "_obs", fake_obs)
    mid = R.resolve_fact("CIK", ("T",), "USD", "2026-09-30",
                         as_of="2026-12-01")
    assert mid["value"] == 100                  # restatement invisible pre-filing


# -- derivation rules --------------------------------------------------------------

def test_derive_ytd_minus_prior_ytd(monkeypatch):
    """Q3 standalone = 9m-YTD − 6m-YTD, same FY start, adjacent ends."""
    ytd9 = _obs("2026-01-01", "2026-09-30", 900)
    prior = {"id": 2, "source_fact_id": "sf600", "accn": "a",
             "value": 600, "period_start": "2026-01-01",
             "period_end": "2026-06-30", "filed_at": "x", "fy": 2026,
             "fp": "Q2"}
    monkeypatch.setattr(R, "_obs",
                        lambda *a, **k: [ytd9])
    db = patch_db(monkeypatch,
                  FakeDB({"FROM fact_observations": [prior]}))
    out = R._derive_quarter(db, "CIK", ("T",), "USD",
                            date(2026, 9, 30), fy=2026)
    assert out is not None
    assert out["value"] == 300
    # derived fact carries the ISOLATED quarter's bounds
    ins = [p for s, p in db.updates if "INSERT INTO fact_observations" in s][0]
    assert ins["ps"] == "2026-07-01"
    assert ins["pe"] == "2026-09-30"
    assert '"ytd_minus_prior_ytd"' in ins["df"]


def test_derive_rejects_non_adjacent_ytd(monkeypatch):
    """A prior YTD ending >1 quarter earlier must not derive — the
    isolation window is the guard, not a suggestion."""
    ytd9 = _obs("2026-01-01", "2026-09-30", 900)
    far = {"id": 2, "source_fact_id": "sfX", "accn": "a",
           "value": 300, "period_start": "2026-01-01",
           "period_end": "2026-03-31", "filed_at": "x"}
    monkeypatch.setattr(R, "_obs", lambda *a, **k: [ytd9])
    db = FakeDB({"FROM fact_observations": [far]})
    assert R._derive_quarter(db, "CIK", ("T",), "USD",
                             date(2026, 9, 30), fy=2026) is None


def test_derive_fy_minus_three_quarters(monkeypatch):
    """Q4 = FY − (Q1+Q2+Q3) — only when all three standalone
    quarters resolve; two quarters is NOT enough to isolate."""
    ann = _obs("2026-01-01", "2026-12-31", 1000, fp="FY",
               frame="CY2026")
    monkeypatch.setattr(R, "_obs", lambda *a, **k: [ann])
    qs = [_obs(f"2026-0{m}-01", f"2026-0{m+2}-30", 200)
          for m in (1, 4, 7)]
    monkeypatch.setattr(R, "_standalone_quarters",
                        lambda *a: qs[:3])
    db = patch_db(monkeypatch, FakeDB())
    out = R._derive_quarter(db, "CIK", ("T",), "USD",
                            date(2026, 12, 31), fy=2026)
    assert out["value"] == 400
    ins = [p for s, p in db.updates if "INSERT INTO fact_observations" in s][0]
    assert ins["ps"] == "2026-10-01"       # isolated Q4 start

    # _standalone_quarters' contract: <3 resolved quarters → None
    monkeypatch.setattr(R, "_standalone_quarters", lambda *a: None)
    db2 = patch_db(monkeypatch, FakeDB())
    assert R._derive_quarter(db2, "CIK", ("T",), "USD",
                             date(2026, 12, 31), fy=2026) is None


def test_derive_fy_minus_9m_ytd(monkeypatch):
    """Q4 via FY − 9m-YTD — the classic path for YTD-only cash flow
    reporters; span and adjacency both validated."""
    ann = _obs("2026-01-01", "2026-12-31", 1000, fp="FY",
               frame="CY2026")
    monkeypatch.setattr(R, "_obs", lambda *a, **k: [ann])
    monkeypatch.setattr(R, "_standalone_quarters", lambda *a: None)
    nine_m = {"id": 9, "source_fact_id": "sf9m", "accn": "a",
              "value": 750, "period_start": "2026-01-01",
              "period_end": "2026-09-30", "filed_at": "x"}
    db = patch_db(monkeypatch,
                  FakeDB({"FROM fact_observations": [nine_m]}))
    out = R._derive_quarter(db, "CIK", ("T",), "USD",
                            date(2026, 12, 31), fy=2026)
    assert out["value"] == 250
    ins = [p for s, p in db.updates if "INSERT INTO fact_observations" in s][0]
    assert '"fy_minus_9m_ytd"' in ins["df"]
    assert ins["ps"] == "2026-10-01"


def test_derive_rejects_wrong_span_for_9m(monkeypatch):
    """FY minus a 6-month YTD is not a Q4 — span validation blocks
    the plausible-looking but wrong isolation."""
    ann = _obs("2026-01-01", "2026-12-31", 1000, fp="FY")
    monkeypatch.setattr(R, "_obs", lambda *a, **k: [ann])
    monkeypatch.setattr(R, "_standalone_quarters", lambda *a: None)
    six_m = {"id": 6, "source_fact_id": "sf6m", "accn": "a",
             "value": 400, "period_start": "2026-01-01",
             "period_end": "2026-06-30", "filed_at": "x"}
    db = FakeDB({"FROM fact_observations": [six_m]})
    assert R._derive_quarter(db, "CIK", ("T",), "USD",
                             date(2026, 12, 31), fy=2026) is None


# -- coverage gate ------------------------------------------------------------------

def _cats(**scores):
    return {c: {"score": scores.get(c)} for c in H._CATEGORIES}


def test_gate_requires_coverage_and_criticals():
    full = _cats(profitability=80, growth=70, cash_flow=75,
                 leverage=70, efficiency=60, quality=65)
    assert H._evaluate_gate(full, 0.9) == (True, True)

    # 80% coverage but missing cash_flow → NOT a score (spec case)
    no_cf = _cats(profitability=80, growth=70, leverage=70,
                  efficiency=60, quality=65)
    no_cf["cash_flow"] = {"score": None}
    assert H._evaluate_gate(no_cf, 0.8)[0] is False

    # each critical category gates independently
    for critical in H._CRITICAL:
        c = _cats(profitability=80, growth=70, cash_flow=75,
                  leverage=70, efficiency=60, quality=65)
        c[critical] = {"score": None}
        pub, ok = H._evaluate_gate(c, 0.9)
        assert pub is False and ok is False

    # everything present but coverage under 60% → gate fails
    assert H._evaluate_gate(full, 0.55)[0] is False


# -- trend + drivers ----------------------------------------------------------------

def test_trend_thresholds():
    assert H._trend(None) == "new"
    assert H._trend(6) == "improving"
    assert H._trend(-6) == "deteriorating"
    assert H._trend(2) == "stable"


def test_drivers_structure_and_order():
    prev = {"category_scores": {
        "cash_flow": {"score": 80},
        "leverage": {"score": 70}}}
    cur = {"category_scores": {
        "cash_flow": {"score": 60,
                      "legs": [{"name": "fcf_conversion", "score": 40},
                               {"name": "fcf_level", "score": 80}]},
        "leverage": {"score": 78,
                     "legs": [{"name": "debt_to_equity", "score": 78}]}}}
    drivers = H._drivers(cur, prev)
    assert drivers[0]["metric"].startswith("cash_flow:")
    assert drivers[0]["direction"] == "negative"
    assert drivers[0]["contribution"] < 0
    # contribution weights by category — cf 0.20 × -20 = -4.0
    assert drivers[0]["contribution"] == -4.0
    assert all("evidence_accn" in d for d in drivers)


def test_f_coerces_decimal_and_null():
    assert H._f(Decimal("1.5")) == 1.5
    assert H._f(None) is None
    assert H._f("x") is None


# -- lineage / license map ---------------------------------------------------------

def test_license_class_fail_closed():
    assert L.license_class("sec_edgar") == "public"
    assert L.license_class("fmp") == "licensed"
    assert L.license_class("unknown_vendor_xyz") == "licensed"
    assert L.license_class(None) == "licensed"


def test_eligibility_recursive_walk(monkeypatch):
    """Two-hop graph: score ← metric ← licensed fact → restricted
    leaf counts, eligible=False. Absence of a verdict is also
    ineligible (fail closed)."""
    import app.database
    edges = {
        ("score", "s1"): [("metric", "m1", "public"),
                          ("fact_observation", "f1", "licensed")],
        ("metric", "m1"): [("fact_observation", "f2", "public")],
    }
    db = FakeDB({
        "SELECT input_type, input_id, license_class":
            lambda p: [{"input_type": it, "input_id": iid,
                        "license_class": lc}
                       for it, iid, lc in
                       edges.get((p["ot"], p["oid"]), [])],
        "SELECT 1 FROM data_lineage":
            lambda p: ([1] if (p["it"], p["iid"]) in edges else []),
    })
    monkeypatch.setattr(app.database, "db", db)
    out = L.compute_eligibility("score", "s1")
    assert out["public_eligible"] is False
    assert out["restricted_leaves"] == 1
    assert out["public_leaves"] == 1

    assert L.is_public_eligible("score", "s1") is False


def test_invalidate_downstream_reaches_transitives(monkeypatch):
    """A restated input invalidates every output reachable from it —
    direct and transitive — so stale verdicts can't survive."""
    import app.database
    outputs = {("fact_observation", "f1"): [("metric", "m1")],
               ("metric", "m1"): [("score", "s1")]}
    db = FakeDB({
        "SELECT output_type, output_id FROM data_lineage":
            lambda p: [{"output_type": o, "output_id": i}
                       for o, i in outputs.get((p["it"], p["iid"]), [])],
    })
    monkeypatch.setattr(app.database, "db", db)
    n = L.invalidate_downstream("fact_observation", "f1")
    assert n == 2                       # metric + score both marked
    deletes = [p for s, p in db.updates
               if "DELETE FROM output_eligibility" in s]
    assert {d["ot"] for d in deletes} == {"metric", "score"}
