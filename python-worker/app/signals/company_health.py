"""Quarterly company health — Phase B of the public-data spine.

One score per (symbol, period) computed entirely from EDGAR-derived
canonical statements + the forensic legs (early_warning_flags,
earnings_quality). The score publishes only when the gate passes —
overall coverage >= 60% AND every critical category (cash_flow,
leverage, quality) resolves at least one leg; below the gate the row
carries verdict='insufficient_data' and the categories still score.

Rows are versioned (superseded, never overwritten) so a restatement-
driven rescore preserves what the prior read said. Drivers are
structured {metric, direction, contribution, evidence_accn} rows —
the human-readable "why it moved" is generated FROM them, never the
other way round.

Alert classes (all four, per spec):
  financial_health   — score drop >= 10 or trend → deteriorating
  earnings_quality   — new forensic flag / EWF GREEN→YELLOW|RED
  filing_governance  — new amendment covering a scored period
  data_quality       — critical-leg loss vs the prior scored row
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

def _j(payload: Any) -> str:
    """jsonb serializer — Decimal/date come back from the DB verbatim;
    coerce once here instead of sprinkling float() everywhere."""
    from decimal import Decimal
    def _d(o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (date,)):
            return o.isoformat()
        raise TypeError(type(o))
    return json.dumps(payload, default=_d)


_VERSION = "b1_v1"
_MIN_COVERAGE = 0.60
# critical legs per the frozen spec — a score can't publish while
# any of these categories resolves zero legs, whatever the overall
# coverage percentage says
_CRITICAL = ("cash_flow", "leverage", "quality")

_CATEGORIES: dict[str, float] = {
    "profitability": 0.20, "growth": 0.15, "cash_flow": 0.20,
    "leverage": 0.20, "efficiency": 0.15, "quality": 0.10,
}


@dataclass
class Leg:
    """One scored input — score 0-100, or None when the data isn't
    there (missing legs don't pretend to be zeros)."""
    name: str
    weight: float
    score: Optional[float] = None
    value: Any = None
    evidence_accn: Optional[str] = None
    detail: Optional[str] = None


# -- pure scoring curves (declared basis: heuristic_v1) -------------------------

def _piece(v: Optional[float], bands: list[tuple[float, float]]) -> Optional[float]:
    """(threshold, score) pairs evaluated top-down — first band the
    value clears wins. Declared scoring curve; no hidden fitting."""
    if v is None:
        return None
    for floor, sc in bands:
        if v >= floor:
            return sc
    return bands[-1][1]


def _margin_score(om: Optional[float]) -> Optional[float]:
    return _piece(om, [(0.25, 95), (0.18, 85), (0.12, 72), (0.06, 60),
                       (0.0, 45), (-0.10, 25)])


def _growth_score(rev_yoy: Optional[float]) -> Optional[float]:
    return _piece(rev_yoy, [(0.40, 95), (0.25, 85), (0.12, 72),
                            (0.03, 58), (0.0, 45), (-0.10, 28)])


def _fcf_conv_score(conv: Optional[float]) -> Optional[float]:
    return _piece(conv, [(1.2, 95), (1.0, 88), (0.8, 75), (0.5, 60),
                         (0.0, 40), (-0.5, 20)])


def _de_score(de: Optional[float]) -> Optional[float]:
    if de is None:
        return None
    if de <= 0.5:  return 95
    if de <= 1.0:  return 82
    if de <= 2.0:  return 65
    if de <= 4.0:  return 45
    return 22


def _roic_score(roic: Optional[float]) -> Optional[float]:
    return _piece(roic, [(0.25, 95), (0.15, 85), (0.10, 72),
                         (0.05, 55), (0.0, 35)])


def _dilution_score(yoy: Optional[float]) -> Optional[float]:
    """share-count drift YoY — negative is buyback (good)."""
    if yoy is None:
        return None
    if yoy <= -0.02: return 90
    if yoy <= 0.005: return 75
    if yoy <= 0.02:  return 55
    if yoy <= 0.05:  return 35
    return 15


# -- statement reads ------------------------------------------------------------

def _stmt(db, table: str, symbol: str, cols: str, n: int = 8) -> list[dict]:
    return db.execute_query(
        f"SELECT fiscal_date_ending, {cols} FROM {table}"
        " WHERE symbol=:s AND data_source='sec_edgar'"
        " ORDER BY fiscal_date_ending DESC LIMIT :n",
        {"s": symbol, "n": n})


def _prior_period(db, symbol: str, period_end) -> Optional[dict]:
    rows = db.execute_query(
        "SELECT * FROM company_health_quarterly WHERE symbol=:s"
        " AND period_end < :pe AND NOT superseded"
        " ORDER BY period_end DESC LIMIT 1",
        {"s": symbol, "pe": str(period_end)})
    return rows[0] if rows else None


def _year_ago(rows: list[dict], period_end) -> Optional[dict]:
    """The row ~4 quarters back — YoY legs need the comparison year."""
    lo = period_end - timedelta(days=380)
    hi = period_end - timedelta(days=340)
    for r in rows:
        e = r["fiscal_date_ending"]
        e = e if isinstance(e, date) else date.fromisoformat(str(e))
        if lo <= e <= hi:
            return r
    return None


def _shares_yoy(db, cik: str, period_end) -> Optional[float]:
    rows = db.execute_query(
        "SELECT period_end, value FROM fact_observations"
        " WHERE cik=:c AND tag='EntityCommonStockSharesOutstanding'"
        " AND instant AND NOT is_derived"
        " ORDER BY period_end DESC LIMIT 12", {"c": cik})
    if len(rows) < 2:
        return None
    cur = next((r for r in rows
                if str(r["period_end"]) <= str(period_end)), None)
    yr = next((r for r in rows
               if str(r["period_end"]) <= str(period_end - timedelta(days=300))),
              None)
    if cur and yr and yr["value"]:
        return float(cur["value"]) / float(yr["value"]) - 1
    return None


# -- category legs --------------------------------------------------------------

def _legs(db, symbol: str, cik: Optional[str], period_end) -> dict[str, list[Leg]]:
    """Resolve every leg for one quarter. Categories with zero legs
    carry an empty list — the coverage gate reads that, not a zero."""
    inc = _stmt(db, "income_statements", symbol,
                "total_revenue, gross_profit, operating_income, net_income")
    bal = _stmt(db, "balance_sheets", symbol,
                "total_assets, total_liabilities,"
                " total_shareholder_equity, cash_and_cash_equivalents,"
                " long_term_debt, net_receivables, inventory")
    cf = _stmt(db, "cash_flow_statements", symbol,
               "operating_cash_flow, free_cash_flow, capital_expenditures")
    rat = _stmt(db, "financial_ratios", symbol,
                "roe, roa, roic, debt_to_equity, current_ratio,"
                " gross_profit_margin, operating_margin,"
                " net_profit_margin, receivables_turnover")
    cur = lambda rows: next(
        (r for r in rows
         if str(r["fiscal_date_ending"]) == str(period_end)), None)
    i, b, c, r_ = cur(inc), cur(bal), cur(cf), cur(rat)
    i_yoy = _year_ago(inc, period_end)
    rev_yoy = None
    if i and i_yoy and i.get("total_revenue") and i_yoy.get("total_revenue"):
        rev_yoy = float(i["total_revenue"]) / float(i_yoy["total_revenue"]) - 1

    legs: dict[str, list[Leg]] = {k: [] for k in _CATEGORIES}
    if r_:
        accn = None  # canonical rows don't carry accn — statement_row
                     # lineage edges resolve the evidence accession
        legs["profitability"] = [
            Leg("operating_margin", 0.5,
                _margin_score(_f(r_.get("operating_margin"))),
                r_.get("operating_margin"), accn),
            Leg("roe", 0.5,
                _piece(_f(r_.get("roe")),
                       [(0.20, 90), (0.12, 75), (0.06, 55), (0.0, 30)]),
                r_.get("roe"), accn)]
        legs["leverage"] = [
            Leg("debt_to_equity", 0.6,
                _de_score(_f(r_.get("debt_to_equity"))),
                r_.get("debt_to_equity"), accn),
            Leg("current_ratio", 0.4,
                _piece(_f(r_.get("current_ratio")),
                       [(2.0, 90), (1.4, 70), (1.0, 50), (0.7, 30)]),
                r_.get("current_ratio"), accn)]
        legs["efficiency"] = [
            Leg("roic", 0.6, _roic_score(_f(r_.get("roic"))),
                r_.get("roic"), accn)]
    if rev_yoy is not None:
        legs["growth"].append(
            Leg("revenue_yoy", 1.0, _growth_score(rev_yoy),
                round(rev_yoy, 4), None))
    if c:
        conv = None
        if c.get("free_cash_flow") is not None and i and i.get("net_income"):
            ni = float(i["net_income"])
            if ni:
                conv = float(c["free_cash_flow"]) / ni
        legs["cash_flow"] = [
            Leg("fcf_conversion", 0.6, _fcf_conv_score(conv),
                conv, None),
            Leg("fcf_level", 0.4,
                _piece(_f(c.get("free_cash_flow")),
                       [(1e9, 80), (1e8, 65), (0, 50), (-1e9, 30)]),
                c.get("free_cash_flow"), None)]
    if b:
        legs["leverage"] = legs.get("leverage") or []
        if not legs["leverage"]:
            tl, eq = b.get("total_liabilities"), b.get("total_shareholder_equity")
            de = float(tl) / float(eq) if tl is not None and eq else None
            legs["leverage"].append(
                Leg("debt_to_equity", 1.0, _de_score(de), de, None))
    if cik:
        dil = _shares_yoy(db, cik, period_end)
        legs["quality"].append(
            Leg("dilution_yoy", 0.5, _dilution_score(dil), dil, None))
        if i:
            recv, rev = b and b.get("net_receivables"), i.get("total_revenue")
            if recv and rev:
                rr = float(recv) / float(rev)
                legs["quality"].append(
                    Leg("recv_rev_ratio", 0.5,
                        _piece(-rr, [(-0.15, 85), (-0.35, 60), (-0.6, 40)]),
                        round(rr, 4), None))
    return legs


def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


# -- scoring --------------------------------------------------------------------

def _evaluate_gate(cat_scores: dict[str, Any],
                   coverage: float) -> tuple[bool, bool]:
    """The publish gate — pure function. A score publishes only when
    overall coverage >= 60% AND every critical category resolved at
    least one leg; 60% with a missing cash-flow leg is NOT a score."""
    critical_ok = all(
        (cat_scores.get(c) or {}).get("score") is not None
        for c in _CRITICAL)
    return coverage >= _MIN_COVERAGE and critical_ok, critical_ok


def score_quarter(db, symbol: str, cik: Optional[str],
                  period_end, eq: Optional[dict],
                  ewf_state: Optional[str]) -> dict[str, Any]:
    """Score one quarter — pure composition over resolved legs."""
    legs = _legs(db, symbol, cik, period_end)
    cat_scores: dict[str, Any] = {}
    total_w = resolved_w = 0.0
    for cat, cat_weight in _CATEGORIES.items():
        cat_legs = legs.get(cat, [])
        scored = [lg for lg in cat_legs if lg.score is not None]
        w = sum(lg.weight for lg in scored)
        total_w += cat_weight
        if scored and w > 0:
            resolved_w += cat_weight
            cat_scores[cat] = {
                "score": round(sum(lg.score * lg.weight
                                   for lg in scored) / w, 1),
                "legs": [{"name": lg.name, "score": lg.score,
                          "value": lg.value} for lg in scored],
            }
        else:
            cat_scores[cat] = {"score": None,
                               "legs": [{"name": lg.name}
                                        for lg in cat_legs]}
    coverage = resolved_w / total_w if total_w else 0.0
    publishable, critical_ok = _evaluate_gate(cat_scores, coverage)
    score = None
    if publishable:
        score = round(sum(cat_scores[c]["score"] * _CATEGORIES[c]
                          for c in _CATEGORIES
                          if cat_scores[c]["score"] is not None)
                      / resolved_w)
    available = [lg.name for ls in legs.values()
                 for lg in ls if lg.score is not None]
    missing = [lg.name for ls in legs.values()
               for lg in ls if lg.score is None] + \
              [f"cat:{c}" for c in _CATEGORIES
               if not legs.get(c)]
    confidence = ("high" if coverage >= 0.85
                  else "medium" if coverage >= 0.6 else "low")
    return {"score": score,
            "verdict": "scored" if publishable else "insufficient_data",
            "coverage_pct": round(coverage, 4),
            "confidence": confidence,
            "available_legs": available, "missing_legs": missing,
            "category_scores": cat_scores,
            "quality_score": (eq or {}).get("quality"),
            "eq_flags": (eq or {}).get("flags") or [],
            "ewf_state": ewf_state}


def _trend(delta: Optional[int]) -> str:
    if delta is None:
        return "new"
    if delta >= 5:  return "improving"
    if delta <= -5: return "deteriorating"
    return "stable"


def _drivers(cur: dict, prev: Optional[dict],
             evidence_accn: Optional[str] = None) -> list[dict]:
    """Structured change attribution — metric, direction,
    contribution, evidence accession. Prose is generated FROM these."""
    if not prev:
        return []
    prev_cats = (prev.get("category_scores") or {})
    out = []
    for cat, cs in (cur.get("category_scores") or {}).items():
        cur_s, prev_s = cs.get("score"), (prev_cats.get(cat) or {}).get("score")
        if cur_s is None or prev_s is None:
            continue
        delta = cur_s - prev_s
        if abs(delta) < 4:
            continue
        worst = min(cs.get("legs") or [],
                    key=lambda l: l.get("score") or 0, default=None)
        out.append({
            "metric": f"{cat}:{worst['name'] if worst else cat}",
            "direction": "positive" if delta > 0 else "negative",
            "contribution": round(delta * _CATEGORIES.get(cat, 0), 1),
            "category": cat,
            "evidence_accn": evidence_accn,
        })
    return sorted(out, key=lambda d: abs(d["contribution"]),
                  reverse=True)


def _alert(db, symbol: str, klass: str, title: str, detail: dict,
           materiality: str = "HIGH") -> None:
    fp = hashlib.sha1(
        f"{symbol}|{klass}|{title}".encode()).hexdigest()[:32]
    db.execute_update(
        "INSERT INTO alert_items (symbol, event_type, direction,"
        " materiality, title, detail, fingerprint, source,"
        " source_timestamp, status, priority_score) VALUES"
        " (:s,'health',:di,:m,:t,CAST(:de AS jsonb),:fp,"
        " 'company_health', now(),'new',130)"
        " ON CONFLICT (fingerprint) DO NOTHING",
        {"s": symbol,
         "di": "DOWN" if materiality == "HIGH" else "FLAT",
         "m": materiality, "t": title,
         "de": _j({**detail, "class": klass}), "fp": fp})


def persist(db, symbol: str, cik, period_end, scored: dict,
            drivers: list, red_flags: list, filing_accn,
            trend: str, prev: Optional[dict]) -> None:
    db.execute_update(
        "UPDATE company_health_quarterly SET superseded=true"
        " WHERE symbol=:s AND period_end=:pe AND NOT superseded",
        {"s": symbol, "pe": str(period_end)})
    db.execute_update(
        "INSERT INTO company_health_quarterly (symbol, cik,"
        " period_end, score, verdict, coverage_pct, confidence,"
        " available_legs, missing_legs, category_scores, drivers,"
        " red_flags, ewf_state, quality_score, trend, previous_score,"
        " score_delta, filing_accn, score_version)"
        " VALUES (:s,:cik,:pe,:sc,:v,:cov,:conf,:al,:ml,:cs,:dr,:rf,"
        " :ewf,:qs,:tr,:ps,:sd,:fa,:sv)",
        {"s": symbol, "cik": cik, "pe": str(period_end),
         "sc": scored["score"], "v": scored["verdict"],
         "cov": scored["coverage_pct"], "conf": scored["confidence"],
         "al": _j(scored["available_legs"]),
         "ml": _j(scored["missing_legs"]),
         "cs": _j(scored["category_scores"]),
         "dr": _j(drivers), "rf": _j(red_flags),
         "ewf": scored["ewf_state"], "qs": scored["quality_score"],
         "tr": trend, "ps": (prev or {}).get("score"),
         "sd": (scored["score"] - prev["score"]
                if scored["score"] is not None
                and prev and prev.get("score") is not None else None),
         "fa": filing_accn, "sv": _VERSION})


def _filing_governance_flags(db, symbol: str, cik, period_end) -> list[dict]:
    """Amendments covering this period — a restatement event is itself
    a red flag class."""
    if not cik:
        return []
    rows = db.execute_query(
        "SELECT accession_number, form, filing_date FROM edgar_filings"
        " WHERE cik=:c AND is_amendment"
        "   AND report_period=:pe",
        {"c": cik, "pe": str(period_end)})
    return [{"class": "filing_governance", "pattern": "amended_filing",
             "values": {"form": r["form"],
                        "filed": str(r["filing_date"])},
             "evidence_accn": r["accession_number"]} for r in rows]


def score_symbol(db, symbol: str, quarters: int = 8) -> dict[str, Any]:
    """Score the latest N quarters for one issuer."""
    from app.providers import sec_edgar
    cik = sec_edgar.cik_for(symbol)
    periods = [r["fiscal_date_ending"] for r in
               _stmt(db, "income_statements", symbol,
                     "total_revenue", n=quarters)]
    if not periods:
        return {"symbol": symbol, "scored": 0}
    # forensic legs — current-state reads, one call per symbol
    eq = (db.execute_query(
        "SELECT quality, flags FROM symbol_earnings_quality"
        " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1",
        {"s": symbol}) or [{}])[0]
    ewf = None
    try:
        from app.indicators.early_warning_flags import EarlyWarningEngine
        ewf = EarlyWarningEngine().analyze_growth_health(symbol).overall_risk.value
    except Exception as exc:
        logger.debug("ewf %s: %s", symbol, exc)
    scored_n = 0
    # oldest→newest: the journal is a chain — each row's delta,
    # trend and drivers compare against the prior quarter already
    # persisted. DESC order would leave every row 'new'.
    for pe in sorted(periods):
        pe = pe if isinstance(pe, date) else date.fromisoformat(str(pe))
        prev = _prior_period(db, symbol, pe)
        scored = score_quarter(db, symbol, cik, pe, eq, ewf)
        gov = _filing_governance_flags(db, symbol, cik, pe)
        red_flags = [{"class": "earnings_quality", "pattern": f,
                      "values": {}, "evidence_accn": None}
                     for f in scored["eq_flags"]] + gov
        delta = (scored["score"] - prev["score"]
                 if scored["score"] is not None and prev
                 and prev.get("score") is not None else None)
        trend = _trend(delta)
        filing_accn = None
        if cik:
            fr = db.execute_query(
                "SELECT accession_number FROM edgar_filings"
                " WHERE cik=:c AND report_period=:pe"
                " AND form IN ('10-Q','10-K','10-Q/A','10-K/A')"
                " ORDER BY filing_date DESC LIMIT 1",
                {"c": cik, "pe": str(pe)})
            filing_accn = fr[0]["accession_number"] if fr else None
        drivers = _drivers(scored, prev, filing_accn)
        persist(db, symbol, cik, pe, scored, drivers, red_flags,
                filing_accn, trend, prev)
        # -- alerts: the four classes ------------------------------
        if delta is not None and delta <= -10:
            _alert(db, symbol, "financial_health",
                   f"{symbol} health {prev['score']}→{scored['score']}"
                   f" ({pe})", {"period": str(pe), "delta": delta,
                                "drivers": drivers})
        if trend == "deteriorating" and prev \
                and prev.get("trend") != "deteriorating":
            _alert(db, symbol, "financial_health",
                   f"{symbol} trend → deteriorating ({pe})",
                   {"period": str(pe)})
        new_eq = [f for f in scored["eq_flags"]
                  if prev and f not in (prev.get("red_flags") or [])]
        if new_eq or (ewf in ("YELLOW", "RED") and prev
                      and prev.get("ewf_state") == "GREEN"):
            _alert(db, symbol, "earnings_quality",
                   f"{symbol} earnings-quality flags ({pe})",
                   {"flags": new_eq, "ewf": ewf}, "MED")
        if gov:
            _alert(db, symbol, "filing_governance",
                   f"{symbol} amended filing covers {pe}",
                   {"amendments": [g["evidence_accn"] for g in gov]})
        prev_missing = set((prev or {}).get("missing_legs") or [])
        lost = [c for c in _CRITICAL
                if f"cat:{c}" in scored["missing_legs"]
                and f"cat:{c}" not in prev_missing]
        if lost and prev:
            _alert(db, symbol, "data_quality",
                   f"{symbol} lost critical legs {lost} ({pe})",
                   {"lost": lost})
        scored_n += 1
    return {"symbol": symbol, "scored": scored_n,
            "latest": scored["score"], "trend": trend}


def run(symbols: list[str]) -> dict[str, Any]:
    from app.database import db
    totals = {"symbols": 0, "quarters_scored": 0, "errors": []}
    for sym in symbols:
        try:
            r = score_symbol(db, sym)
            totals["symbols"] += 1
            totals["quarters_scored"] += r["scored"]
        except Exception as exc:
            logger.warning("health %s failed: %s", sym, exc)
            totals["errors"].append(f"{sym}: {exc}")
    return totals
