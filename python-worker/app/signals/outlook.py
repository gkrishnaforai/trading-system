"""Composite outlook — Phase D part 2. ADMIN-ONLY (admin_only=true
on every row; the public release boundary is A+B+E only).

Four legs, all EDGAR-sourced:
  health_trajectory  latest company_health score + delta momentum
  cohort_relative    score vs the SIC cohort's median
  insider_flow       open-market buys vs sells, trailing 90d (Form 4)
  guidance_tone      forward_looking claim balance, trailing 120d

The composite is a HEURISTIC research signal — ranked-company output
stays labeled as such; the outcome journal (realized_*d columns) is
what eventually proves or disproves it.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_VERSION = "d1_v1"
_WEIGHTS = {"health_trajectory": 0.35, "cohort_relative": 0.25,
            "insider_flow": 0.20, "guidance_tone": 0.20}
_GRADES = ((80, "A"), (65, "B"), (50, "C"), (35, "D"))


def _clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, v))


def _health_leg(db, symbol: str) -> tuple[Optional[float], dict]:
    rows = db.execute_query(
        "SELECT period_end, score, score_delta, trend, id"
        " FROM company_health_quarterly"
        " WHERE symbol=:s AND NOT superseded AND score IS NOT NULL"
        " ORDER BY period_end DESC LIMIT 2", {"s": symbol})
    if not rows:
        return None, {}
    cur = rows[0]
    delta = cur.get("score_delta") or 0
    leg = _clamp(float(cur["score"]) + float(delta) * 1.5)
    return leg, {"latest_score": cur["score"],
                 "delta": cur["score_delta"], "trend": cur["trend"],
                 "health_row_id": cur["id"]}


def _cohort_leg(db, symbol: str, health: dict) -> tuple[Optional[float], dict]:
    from app.signals import cohorts
    snap = cohorts.cohort_for(db, symbol)
    score = health.get("latest_score")
    if not snap or score is None:
        return None, {}
    metrics = snap.get("metrics") or {}
    if isinstance(metrics, str):
        metrics = json.loads(metrics)
    med = (metrics.get("health_score") or {}).get("median")
    if med is None:
        return None, {}
    # +10 above cohort median ≈ 75 — position, not absolute level
    leg = _clamp(50 + (float(score) - float(med)) * 2.5)
    return leg, {"cohort_key": snap["cohort_key"],
                 "cohort_median": med,
                 "cohort_snapshot_id": snap["id"]}


def _insider_leg(db, symbol: str) -> tuple[Optional[float], dict]:
    rows = db.execute_query(
        "SELECT transaction_code, shares, price"
        " FROM insider_transactions"
        " WHERE symbol=:s AND transaction_code IN ('P','S')"
        " AND transaction_date >= :cut", {
            "s": symbol,
            "cut": str(date.today() - timedelta(days=90))})
    rows = [r for r in rows if r["transaction_code"] in ("P", "S")]
    buys = sum(float(r["shares"] or 0) * float(r["price"] or 0)
               for r in rows if r["transaction_code"] == "P")
    sells = sum(float(r["shares"] or 0) * float(r["price"] or 0)
                for r in rows if r["transaction_code"] == "S")
    if not rows:
        return None, {}
    total = buys + sells
    leg = _clamp(buys / total * 100) if total else 50.0
    return leg, {"buy_notional": round(buys),
                 "sell_notional": round(sells), "n_tx": len(rows)}


def _tone_leg(db, symbol: str) -> tuple[Optional[float], dict]:
    rows = db.execute_query(
        "SELECT direction, count(*) AS n FROM narrative_claims"
        " WHERE symbol=:s AND claim_type='management_guidance'"
        " AND source LIKE 'edgar%' AND version=1"
        " AND created_at >= :cut"
        " GROUP BY direction",
        {"s": symbol,
         "cut": str(date.today() - timedelta(days=120))})
    pos = sum(r["n"] for r in rows if r["direction"] == "positive")
    neg = sum(r["n"] for r in rows if r["direction"] == "negative")
    if not rows or pos + neg == 0:
        return None, {}
    return _clamp(pos / (pos + neg) * 100), {
        "positive": pos, "negative": neg}


def _grade(score: float) -> str:
    for floor, g in _GRADES:
        if score >= floor:
            return g
    return "F"


def score_symbol(db, symbol: str,
                 as_of: Optional[date] = None) -> dict[str, Any]:
    """Composite → versioned journal row. Legs that don't resolve
    are dropped and weights renormalized — a sparse composite is
    still journaled, but inputs make the sparsity auditable."""
    as_of = as_of or date.today()
    legs, inputs = {}, {"symbol": symbol}
    legs["health_trajectory"], h = _health_leg(db, symbol)
    inputs.update(h)
    legs["cohort_relative"], c = _cohort_leg(db, symbol, h)
    inputs.update(c)
    legs["insider_flow"], i = _insider_leg(db, symbol)
    inputs.update(i)
    legs["guidance_tone"], t = _tone_leg(db, symbol)
    inputs.update(t)

    avail = {k: v for k, v in legs.items() if v is not None}
    if not avail:
        return {"symbol": symbol, "score": None, "scored": False}
    w = sum(_WEIGHTS[k] for k in avail)
    composite = sum(avail[k] * _WEIGHTS[k] for k in avail) / w
    db.execute_update(
        "INSERT INTO outlook_scores (symbol, as_of, score, grade,"
        " components, inputs, score_version, admin_only) VALUES"
        " (:s,:d,:sc,:g,CAST(:c AS jsonb),CAST(:i AS jsonb),:v,true)"
        " ON CONFLICT (symbol, as_of, score_version)"
        " DO UPDATE SET score=:sc, grade=:g,"
        " components=CAST(:c AS jsonb), inputs=CAST(:i AS jsonb)",
        {"s": symbol, "d": str(as_of), "sc": round(composite, 1),
         "g": _grade(composite), "c": json.dumps(legs),
         "i": json.dumps(inputs, default=str), "v": _VERSION})
    return {"symbol": symbol, "score": round(composite, 1),
            "grade": _grade(composite), "components": avail,
            "legs_resolved": len(avail), "scored": True}


def run(symbols: Optional[list[str]] = None) -> dict[str, Any]:
    from app.database import db
    if symbols is None:
        symbols = [r["symbol"] for r in db.execute_query(
            "SELECT DISTINCT symbol FROM company_health_quarterly"
            " WHERE NOT superseded")]
    results = [score_symbol(db, s) for s in symbols]
    return {"symbols": len(symbols),
            "scored": sum(r["scored"] for r in results),
            "grades": {g: sum(r.get("grade") == g for r in results)
                       for g in "ABCDF"}}
