"""SIC cohort snapshots — Phase D part 1 of the public-data spine.

"Public-filing-based cohort intelligence": members are the tracked
EDGAR universe grouped by SIC division (2-digit). Each snapshot
reports BOTH the aggregate-weighted metric and the median + quartiles
— a mega-cap-heavy cohort's mean lies where its median doesn't.

The label is structural, not decorative: the cohort is the tracked
universe, not the industry — survivorship_bias_warning is always
true and the label text ships on every row.
"""
from __future__ import annotations

import hashlib
import json
import logging
import statistics
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

_VERSION = "d1_v1"
_LABEL = "public-filing-based cohort intelligence"


def _quartiles(vals: list[float]) -> dict[str, float]:
    """Median + IQR bounds — small cohorts degrade gracefully."""
    s = sorted(vals)
    n = len(s)
    med = statistics.median(s)
    lo = s[:n // 2] or s
    hi = s[(n + 1) // 2:] or s
    return {"median": round(med, 1),
            "p25": round(statistics.median(lo), 1),
            "p75": round(statistics.median(hi), 1),
            "n": n}


def _cohort_key(sic: Optional[str]) -> Optional[str]:
    sic = (sic or "").strip()
    return f"sic:{sic[:2]}" if len(sic) >= 2 else None


def _latest_health(db, symbols: list[str]) -> dict[str, dict]:
    """Latest non-superseded health row per member."""
    rows = db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, period_end, score,"
        " verdict, coverage_pct, category_scores"
        " FROM company_health_quarterly"
        " WHERE symbol = ANY(:s) AND NOT superseded"
        " ORDER BY symbol, period_end DESC", {"s": symbols})
    out = {}
    for r in rows:
        cs = r.get("category_scores")
        if isinstance(cs, str):
            r["category_scores"] = json.loads(cs)
        out[r["symbol"]] = r
    return out


def snapshot(db, as_of: Optional[date] = None) -> dict[str, Any]:
    """One snapshot pass over all SIC cohorts with ≥3 tracked members
    — a 2-member 'cohort' is a pair, not a distribution."""
    as_of = as_of or date.today()
    entities = db.execute_query(
        "SELECT cik, symbol, sic, sic_description FROM edgar_entities"
        " WHERE symbol IS NOT NULL AND sic IS NOT NULL")
    cohorts: dict[str, list[dict]] = {}
    for e in entities:
        key = _cohort_key(e["sic"])
        if key:
            cohorts.setdefault(key, []).append(e)

    written = 0
    for key, members in sorted(cohorts.items()):
        if len(members) < 3:
            continue
        syms = [m["symbol"] for m in members]
        health = _latest_health(db, syms)
        scored = [h for h in health.values()
                  if h["verdict"] == "scored"
                  and h["score"] is not None]
        if not scored:
            continue
        coverage = len(health) / len(members)
        scores = [float(h["score"]) for h in scored]
        metrics: dict[str, dict] = {"health_score": {
            "aggregate": round(sum(scores) / len(scores), 1),
            **_quartiles(scores)}}
        # category medians — cohort-relative legs for the outlook
        cats = sorted({c for h in scored
                       for c in (h.get("category_scores") or {})})
        for cat in cats:
            vals = [float((h["category_scores"][cat] or {})["score"])
                    for h in scored
                    if (h.get("category_scores") or {}).get(cat)
                    and h["category_scores"][cat].get("score")
                    is not None]
            if len(vals) >= 3:
                metrics[f"cat:{cat}"] = _quartiles(vals)
        alignment: dict[str, int] = {}
        for h in health.values():
            pe = str(h["period_end"])
            alignment[pe] = alignment.get(pe, 0) + 1
        comp = hashlib.sha1(
            "|".join(sorted(syms)).encode()).hexdigest()[:12]
        label = next((m["sic_description"] for m in members
                      if m.get("sic_description")), key)
        db.execute_update(
            "INSERT INTO cohort_snapshots (cohort_key, cohort_label,"
            " as_of, member_count, reporting_coverage_pct,"
            " fiscal_period_alignment, metrics, composition_version,"
            " survivorship_bias_warning, label) VALUES"
            " (:k,:l,:d,:mc,:cov,CAST(:fa AS jsonb),CAST(:m AS jsonb),"
            " :cv,true,:lbl)"
            " ON CONFLICT (cohort_key, as_of, composition_version)"
            " DO NOTHING",
            {"k": key, "l": label, "d": str(as_of),
             "mc": len(members), "cov": round(coverage, 3),
             "fa": json.dumps(alignment), "m": json.dumps(metrics),
             "cv": comp, "lbl": _LABEL})
        written += 1
    return {"as_of": str(as_of), "cohorts": len(cohorts),
            "written": written}


def cohort_for(db, symbol: str) -> Optional[dict]:
    """Latest snapshot of the cohort containing symbol — the
    outlook's cohort-relative leg reads this."""
    rows = db.execute_query(
        "SELECT * FROM cohort_snapshots WHERE cohort_key = ("
        " SELECT 'sic:' || substring(sic from 1 for 2)"
        " FROM edgar_entities WHERE symbol=:s AND sic IS NOT NULL"
        " LIMIT 1) ORDER BY as_of DESC LIMIT 1", {"s": symbol.upper()})
    return rows[0] if rows else None


def run(symbols: Optional[list[str]] = None) -> dict[str, Any]:
    from app.database import db
    return snapshot(db)
