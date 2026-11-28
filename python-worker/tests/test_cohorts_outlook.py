"""Phase D — cohort snapshots (aggregate+median+quartiles, label,
survivorship flag, 3-member floor) and the outlook composite
(leg resolution, renormalized weights, grading)."""
from __future__ import annotations

import json
from datetime import date

from app.signals import cohorts as C
from app.signals import outlook as O


class _FakeDB:
    def __init__(self, query_map=None):
        self.query_map = query_map or {}
        self.updates = []

    def execute_query(self, sql, params=None):
        for key, val in self.query_map.items():
            if key in sql:
                return val(params) if callable(val) else val
        return []

    def execute_update(self, sql, params=None):
        self.updates.append((sql, params))
        return 1


def _entities():
    return [{"cik": str(i), "symbol": f"S{i}",
             "sic": f"367{i%10}", "sic_description": "Semis"}
            for i in range(5)] + \
           [{"cik": "9", "symbol": "LONELY",
             "sic": "7399", "sic_description": "Other"}]


def _health(params):
    syms = params["s"]
    return [{"symbol": s, "period_end": "2026-09-30",
             "score": 40 + i * 10, "verdict": "scored",
             "coverage_pct": 0.9,
             "category_scores": {"leverage": {"score": 50 + i * 5}}}
            for i, s in enumerate(syms)]


def test_snapshot_writes_cohort_and_stats():
    db = _FakeDB({
        "FROM edgar_entities": _entities(),
        "FROM company_health_quarterly": _health,
    })
    out = C.snapshot(db, as_of=date(2026, 11, 27))
    assert out["written"] == 1            # sic:36 has 5 members; sic:73 only 1
    ins = [p for s, p in db.updates if "cohort_snapshots" in s][0]
    assert ins["k"] == "sic:36"
    assert ins["mc"] == 5
    assert ins["cov"] == 1.0
    metrics = json.loads(ins["m"])
    hs = metrics["health_score"]
    assert hs["aggregate"] == 60.0        # mean of 40,50,60,70,80
    assert hs["median"] == 60.0
    assert hs["p25"] == 45.0 and hs["p75"] == 75.0
    assert "cat:leverage" in metrics
    align = json.loads(ins["fa"])
    assert align == {"2026-09-30": 5}
    assert ins["lbl"] == "public-filing-based cohort intelligence"


def test_snapshot_skips_thin_cohorts():
    db = _FakeDB({
        "FROM edgar_entities": [{"cik": "1", "symbol": "A",
                                 "sic": "3674", "sic_description": "x"},
                                {"cik": "2", "symbol": "B",
                                 "sic": "3674", "sic_description": "x"}],
        "FROM company_health_quarterly": _health,
    })
    out = C.snapshot(db)
    assert out["written"] == 0            # 2 members < 3-member floor


def test_quartiles_small_and_even():
    q = C._quartiles([10, 20, 30, 40])
    assert q["median"] == 25 and q["n"] == 4
    assert C._quartiles([5])["median"] == 5


# -- outlook composite -------------------------------------------------------------

def _outlook_db(health_rows, cohort=None, insider=None, tone=None):
    return _FakeDB({
        "FROM company_health_quarterly": health_rows,
        "FROM cohort_snapshots": cohort or [],
        "FROM insider_transactions": insider or [],
        "FROM narrative_claims": tone or [],
    })


def test_health_leg_score_plus_delta():
    db = _outlook_db([{"period_end": "2026-09-30", "score": 70,
                       "score_delta": 10, "trend": "improving",
                       "id": 1}])
    leg, info = O._health_leg(db, "X")
    assert leg == 85.0                    # 70 + 10*1.5
    assert info["health_row_id"] == 1


def test_cohort_leg_relative_position():
    db = _outlook_db([], cohort=[{
        "id": 7, "cohort_key": "sic:36",
        "metrics": json.dumps({"health_score": {"median": 50}}),
        "cohort_label": "x", "as_of": "2026-11-27"}])
    leg, info = O._cohort_leg(db, "X", {"latest_score": 70})
    assert leg == 100.0                   # 50 + 20*2.5 clamped
    assert info["cohort_snapshot_id"] == 7


def test_insider_leg_buy_ratio():
    db = _outlook_db([], insider=[
        {"transaction_code": "P", "shares": 100, "price": 10},
        {"transaction_code": "S", "shares": 100, "price": 10},
        {"transaction_code": "F", "shares": 999, "price": 10}])  # tax
    leg, info = O._insider_leg(db, "X")
    assert leg == 50.0                    # F codes ignored
    assert info["n_tx"] == 2


def test_tone_leg_balance():
    db = _outlook_db([], tone=[
        {"direction": "positive", "n": 3},
        {"direction": "negative", "n": 1}])
    leg, info = O._tone_leg(db, "X")
    assert leg == 75.0 and info == {"positive": 3, "negative": 1}


def test_score_symbol_renormalizes_weights():
    """Only health resolves → composite = the health leg, and inputs
    carry the health row's lineage ref."""
    db = _outlook_db([{"period_end": "2026-09-30", "score": 80,
                       "score_delta": 0, "trend": "stable", "id": 9}])
    out = O.score_symbol(db, "X", as_of=date(2026, 11, 27))
    assert out["scored"] and out["score"] == 80.0
    assert out["grade"] == "A"
    ins = [p for s, p in db.updates if "outlook_scores" in s][0]
    inputs = json.loads(ins["i"])
    assert inputs["health_row_id"] == 9
    assert ins["v"] == "d1_v1"


def test_score_symbol_no_legs():
    out = O.score_symbol(_outlook_db([]), "X")
    assert out["scored"] is False and out["score"] is None


def test_grade_bands():
    assert O._grade(80) == "A" and O._grade(65) == "B"
    assert O._grade(50) == "C" and O._grade(35) == "D"
    assert O._grade(10) == "F"
