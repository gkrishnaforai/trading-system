"""Industry-relative valuation — a contradiction detector, not a vote.

Answers a different question than the intrinsic methods: "what multiple
does the market actually pay for comparable businesses?" Peers are
symbols sharing the subject's FMP industry classification — or an
explicit category group (peer_groups.yaml) when the taxonomy mislabels
the archetype; multiples are
read off each peer's latest fmp_key_metrics_ttm snapshot (evToSalesTTM,
evToEBITDATTM, evToFreeCashFlowTTM, earningsYieldTTM → implied P/E) and
revenue growth from fmp_financial_growth.

The output compares the subject's implied multiples at spot AND at the
computed fair value against peer medians. A justified-PE formula can be
internally consistent yet still disagree with the peer-adjusted market —
that disagreement is surfaced as a flag, never blended into fair_value.
"""
from __future__ import annotations

import logging
import statistics
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PEER_MIN = 3            # fewer than this → not a set, just anecdotes
_PEER_LIMIT = 40
_MULT_HI = 300.0         # sanity bound — multiples above this are
                         # data artifacts, not comparable evidence
_GROWTH_PREMIUM_TOLERANCE = 0.05  # subject growth must exceed peer
                                  # median by >5pts to earn a premium

_PE_KEY = "pe_implied"   # 1 / earningsYieldTTM
_EV_KEYS = {
    "ev_sales": ("evToSalesTTM",),
    "ev_ebitda": ("evToEBITDATTM",),
    "ev_fcf": ("evToFreeCashFlowTTM",),
}
_GROWTH_KEYS = ("revenueGrowth", "revenueGrowthTTM", "revGrowth",
                "revenue_growth")


def _f(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def _median(xs: List[float]) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 4) if xs else None


def peer_medians(peer_rows: List[Dict[str, Any]],
                 peer_growth: Optional[Dict[str, float]] = None
                 ) -> Dict[str, Any]:
    """Pure: key_metrics payloads + growth payloads -> median multiples.
    peer_rows: [{symbol, key_metrics}] where key_metrics is the
    key_metrics_ttm payload dict. peer_growth: {symbol: growth_decimal}."""
    pe, ev_sales, ev_ebitda, ev_fcf, growth = [], [], [], [], []
    used = 0
    for row in peer_rows or []:
        km = row.get("key_metrics") or {}
        v_pe = _f(km.get("earningsYieldTTM"))
        if v_pe is not None and 0 < (1.0 / v_pe) <= _MULT_HI:
            pe.append(1.0 / v_pe)
            used += 1
        for out_key, cands in _EV_KEYS.items():
            v = next((_f(km.get(c)) for c in cands
                      if _f(km.get(c)) is not None), None)
            if v is not None and 0 < v <= _MULT_HI:
                {"ev_sales": ev_sales, "ev_ebitda": ev_ebitda,
                 "ev_fcf": ev_fcf}[out_key].append(v)
        g = _f((peer_growth or {}).get(row.get("symbol")))
        if g is not None and -1.0 < g < 5.0:
            growth.append(g)
    return {
        "n_peers": len(peer_rows or []),
        "n_with_multiples": used,
        "pe": _median(pe), "ev_sales": _median(ev_sales),
        "ev_ebitda": _median(ev_ebitda), "ev_fcf": _median(ev_fcf),
        "revenue_growth": _median(growth),
    }


def _ev(price: Optional[float], shares: Optional[float],
        cash: Optional[float], debt: Optional[float]) -> Optional[float]:
    if not price or not shares or price <= 0 or shares <= 0:
        return None
    return price * shares + float(debt or 0) - float(cash or 0)


def subject_multiples(price: Optional[float], scalars: Dict[str, Any]
                      ) -> Dict[str, Optional[float]]:
    """The subject's market-implied multiples at a given price."""
    s = scalars or {}
    eps = _f(s.get("eps_ttm"))
    rev = _f(s.get("revenue_ttm"))
    rev_fwd = _f(s.get("revenue_forward"))
    fcf = _f(s.get("fcf_ttm"))
    ev = _ev(price, _f(s.get("shares_outstanding")),
             _f(s.get("cash_and_equivalents")), _f(s.get("total_debt")))
    out: Dict[str, Optional[float]] = {"ev": None, "pe": None,
                                       "ev_sales": None,
                                       "ev_sales_fwd": None,
                                       "ev_fcf": None}
    if not price or price <= 0:
        return out
    if eps and eps > 0:
        out["pe"] = round(price / eps, 2)
    if ev is not None:
        out["ev"] = round(ev, 0)
        if rev and rev > 0:
            out["ev_sales"] = round(ev / rev, 2)
        if rev_fwd and rev_fwd > 0:
            # forward basis — the denominator EV/S methods actually
            # price; keeps a 6x fwd multiple from reading as 35x trailing
            out["ev_sales_fwd"] = round(ev / rev_fwd, 2)
        if fcf and fcf > 0:
            out["ev_fcf"] = round(ev / fcf, 2)
    return out


def flag_relative(medians: Dict[str, Any], at_spot: Dict[str, Any],
                  at_fv: Dict[str, Any],
                  subject_growth: Optional[float]) -> Dict[str, Any]:
    """Compare the FV-implied multiple with the peer median, growth-
    adjusted. Returns {fv_premium, spot_premium, flag, note}."""
    out: Dict[str, Any] = {}
    peer_pe = medians.get("pe")
    if not peer_pe:
        return out
    subj_g = _f(subject_growth)
    peer_g = _f(medians.get("revenue_growth"))
    growth_edge = (subj_g is not None and peer_g is not None
                   and subj_g > peer_g + _GROWTH_PREMIUM_TOLERANCE)

    if at_fv.get("pe"):
        prem = at_fv["pe"] / peer_pe - 1.0
        out["fv_premium"] = round(prem, 3)
        if prem > 0.5 and not growth_edge:
            out["flag"] = "fv_premium_unsupported"
            out["note"] = (
                f"fair value implies {at_fv['pe']:.0f}x earnings vs "
                f"peer median {peer_pe:.0f}x (+{prem:.0%}) without a "
                "growth edge to support it")
        elif prem < -0.4:
            out["flag"] = "fv_discount_vs_peers"
            out["note"] = (
                f"fair value implies {at_fv['pe']:.0f}x vs peer median "
                f"{peer_pe:.0f}x ({prem:.0%}) — pessimistic vs the "
                "sector's own market")
    if at_spot.get("pe"):
        out["spot_premium"] = round(at_spot["pe"] / peer_pe - 1.0, 3)
    if growth_edge:
        out["growth_edge"] = {"subject": round(subj_g, 4),
                              "peer_median": round(peer_g, 4)}
    return out


def compute_relative(symbol: str, industry: Optional[str],
                     scalars: Dict[str, Any], *, spot: Optional[float],
                     fair_value: Optional[float],
                     peer_symbols: Optional[List[str]] = None
                     ) -> Dict[str, Any]:
    """Full leg: fetch peers, compute medians + subject multiples,
    flag disagreement. Never raises.

    peer_symbols — an explicit category peer group (peer_groups.yaml)
    that bypasses the FMP industry query; use it when the taxonomy
    mislabels the archetype (NBIS -> 'Internet Content')."""
    base = {"industry": industry, "status": "ok"}
    try:
        if peer_symbols:
            base["peer_source"] = "category_group"
            peer_rows, peer_growth = _fetch_peer_data(
                symbol, industry or "", peers=peer_symbols)
        else:
            base["peer_source"] = "industry"
            if not industry:
                return {**base, "status": "not_applicable",
                        "reason": "no_industry_classification"}
            peer_rows, peer_growth = _fetch_peer_data(symbol, industry)
        if len(peer_rows) < _PEER_MIN:
            return {**base, "status": "insufficient_peers",
                    "peers_found": len(peer_rows),
                    "reason": "fewer than 3 peers with key-metrics data"}
        med = peer_medians(peer_rows, peer_growth)
        if not any(med.get(k) for k in ("pe", "ev_sales", "ev_ebitda")):
            return {**base, "status": "insufficient_peers",
                    "peers_found": len(peer_rows),
                    "reason": "peers lack usable multiples"}
        at_spot = subject_multiples(spot, scalars)
        at_fv = subject_multiples(fair_value, scalars)
        rel = flag_relative(med, at_spot, at_fv,
                            scalars.get("revenue_growth_ttm"))
        return {**base, "peers_n": med["n_peers"],
                "peer_medians": {k: med[k] for k in
                                 ("pe", "ev_sales", "ev_ebitda",
                                  "ev_fcf", "revenue_growth")},
                "at_spot": at_spot, "at_fair_value": at_fv, **rel}
    except Exception as exc:  # never block a run on a reference leg
        logger.warning("relative valuation failed for %s: %s", symbol, exc)
        return {**base, "status": "error", "reason": str(exc)}


def _fetch_peer_data(symbol: str, industry: str,
                     peers: Optional[List[str]] = None):
    """Latest key-metrics + growth payload per peer. `peers` overrides
    the same-industry query with an explicit category group."""
    from sqlalchemy import text
    from app.database import db

    with db.get_session() as session:
        if peers is None:
            peers = [r[0] for r in session.execute(
                text(
                    """
                    SELECT DISTINCT stock_symbol
                    FROM stock_insights_snapshots
                    WHERE source = 'fmp_fundamentals'
                      AND stock_symbol != :sym
                      AND payload->'fundamentals'->>'industry' = :ind
                    LIMIT :n
                    """),
                {"sym": symbol, "ind": industry,
                 "n": _PEER_LIMIT}).fetchall()]
        else:
            peers = [p for p in peers if p != symbol]
        if not peers:
            return [], {}
        rows = session.execute(
            text(
                """
                SELECT DISTINCT ON (stock_symbol)
                       stock_symbol, payload
                FROM stock_insights_snapshots
                WHERE source = 'fmp_key_metrics_ttm'
                  AND stock_symbol = ANY(:peers)
                ORDER BY stock_symbol, generated_at DESC
                """),
            {"peers": peers}).fetchall()
        grows = session.execute(
            text(
                """
                SELECT DISTINCT ON (stock_symbol)
                       stock_symbol, payload
                FROM stock_insights_snapshots
                WHERE source = 'fmp_financial_growth'
                  AND stock_symbol = ANY(:peers)
                ORDER BY stock_symbol, generated_at DESC
                """),
            {"peers": peers}).fetchall()

    peer_rows = []
    for sym, payload in rows:
        p = payload or {}
        km = p.get("key_metrics_ttm") or p
        peer_rows.append({"symbol": sym, "key_metrics": km})
    peer_growth: Dict[str, float] = {}
    for sym, payload in grows:
        p = payload or {}
        fg = p.get("financial_growth") or p
        node = fg[0] if isinstance(fg, list) and fg else fg
        if isinstance(node, dict):
            g = next((_f(node.get(k)) for k in _GROWTH_KEYS
                      if _f(node.get(k)) is not None), None)
            if g is not None:
                peer_growth[sym] = g
    return peer_rows, peer_growth
