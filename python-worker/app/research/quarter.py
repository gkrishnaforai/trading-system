"""Canonical multi-quarter print record.

One quarter object per reported period — reported values preserved,
derived values flagged 'calculated', est-vs-actual joined from
earnings_data, and driver deltas for the same window. The trend
reads (accel/decel, margin path, cash conversion, dilution) are the
deterministic multi-period layer — they need >=2 periods, never
extrapolate one print into a trend.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _f(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def quarters(sym: str, n: int = 6) -> list[dict]:
    """Most-recent-first quarterly records from fundamental_quarterly
    — the P&L/BS/CF source with filing_date provenance."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT period_end, filing_date, revenue, gross_profit,"
            " operating_income, net_income, eps_diluted, shares_diluted,"
            " total_debt, cash, operating_cf, capex, free_cf"
            " FROM fundamental_quarterly WHERE symbol=:s"
            " ORDER BY period_end DESC LIMIT :n",
            {"s": sym.upper(), "n": n})
    except Exception as exc:
        logger.debug("research quarters %s: %s", sym, exc)
        return []
    out = []
    for r in rows:
        rev, gp, oi = _f(r["revenue"]), _f(r["gross_profit"]), \
            _f(r["operating_income"])
        out.append({
            "period_end": str(r["period_end"]),
            "filing_date": str(r["filing_date"]) if r["filing_date"]
            else None,
            "revenue": {"value": rev, "flag": "reported"},
            "gross_margin": {
                "value": (gp / rev if rev else None),
                "flag": "calculated"},
            "op_margin": {
                "value": (oi / rev if rev else None),
                "flag": "calculated"},
            "net_income": {"value": _f(r["net_income"]),
                           "flag": "reported"},
            "eps_diluted": {"value": _f(r["eps_diluted"]),
                            "flag": "reported"},
            "shares_diluted": {"value": _f(r["shares_diluted"]),
                               "flag": "reported"},
            "cash": {"value": _f(r["cash"]), "flag": "reported"},
            "total_debt": {"value": _f(r["total_debt"]),
                           "flag": "reported"},
            "free_cf": {"value": _f(r["free_cf"]), "flag": "reported"},
        })
    return out


def trends(qs: list[dict]) -> dict:
    """Deterministic multi-period reads. qs is most-recent-first.
    Every read names its basis — 'trend' only when >=3 observations,
    a one-quarter move is 'latest', never 'trend'."""
    out: dict[str, Any] = {}
    if not qs:
        return out                          # no prints → no reads
    revs = [q["revenue"]["value"] for q in qs
            if q["revenue"]["value"] is not None]
    # YoY — same quarter a year ago needs ~4 periods back in the
    # sequence (rows are quarterly, descending)
    if len(qs) >= 5 and qs[0]["revenue"]["value"] and \
            qs[4]["revenue"]["value"]:
        out["rev_yoy"] = (qs[0]["revenue"]["value"]
                          / qs[4]["revenue"]["value"]) - 1
    if len(revs) >= 2 and revs[1]:
        out["rev_qoq"] = revs[0] / revs[1] - 1
    if len(revs) >= 3:
        # acceleration = latest qoq minus prior qoq — the honest
        # 3-point read; more points would fit a slope but 3 is the
        # minimum for "accelerating" to mean anything
        g0 = revs[0] / revs[1] - 1 if revs[1] else None
        g1 = revs[1] / revs[2] - 1 if revs[2] else None
        out["rev_accel"] = (g0 - g1) if None not in (g0, g1) else None
    oms = [q["op_margin"]["value"] for q in qs
           if q["op_margin"]["value"] is not None]
    if len(oms) >= 3:
        out["margin_trend"] = ("improving" if oms[0] > oms[2]
                               else "declining" if oms[0] < oms[2]
                               else "flat")
    if len(qs) >= 5 and qs[0]["shares_diluted"]["value"] and \
            qs[4]["shares_diluted"]["value"]:
        out["dilution_yoy"] = (qs[0]["shares_diluted"]["value"]
                               / qs[4]["shares_diluted"]["value"]) - 1
    # cash conversion — does FCF back the P&L?
    ni, fcf = qs[0]["net_income"]["value"], qs[0]["free_cf"]["value"]
    if ni and ni > 0 and fcf is not None:
        out["fcf_conversion"] = fcf / ni
    # runway — cash / quarterly burn; only meaningful when burning
    cash = qs[0]["cash"]["value"]
    if cash is not None and fcf is not None and fcf < 0:
        out["runway_quarters"] = cash / abs(fcf)
    elif fcf is not None and fcf >= 0:
        out["runway_quarters"] = None  # self-funding — n/a, not ∞
    return out
