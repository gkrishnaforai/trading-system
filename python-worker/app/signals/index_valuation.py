"""Index valuation — the market-level "is the tape expensive" read.

Two numbers, journaled daily:

  - SPY/QQQ trailing P/E from Yahoo — the index-level trailing
    multiple, provider-sourced.
  - tracked-universe forward P/E: cap-weighted Σmcap/Σfwd-earnings
    over names with a fresh nearest-FY consensus snapshot — our own
    estimate substrate, forward-looking (~400+ names).

The verdict is the earnings-yield spread: tracked EY minus the 10Y
Treasury is what the market pays (or charges) to hold equity risk —
the same spread desks quote as the equity risk premium proxy. A bare
P/E level can't say "too high" without the rate context next to it.

Journal rows accrue the percentile window (same convention as the
per-symbol fwd_pe_pctile): until enough sessions exist, percentile
context is reported as a short window, never implied all-time.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone, timedelta
from typing import Any, Dict, Optional

from app.database import db

log = logging.getLogger(__name__)

_EY_MAX = 0.25          # EY >25% (P/E <4) = unit/currency mismatch, not economics
_MIN_OBS_PCTILE = 8     # percentile needs a real window before it speaks


def _spy_multiples() -> Dict[str, Any]:
    """Index-ETF trailing P/Es — Yahoo reports the fund's trailing P/E,
    which is effectively the index P/E."""
    out: Dict[str, Any] = {}
    try:
        import yfinance as yf
    except Exception as e:
        log.warning("index_valuation: yfinance unavailable: %s", e)
        return out
    for sym in ("SPY", "QQQ"):
        try:
            info = yf.Ticker(sym).info or {}
            pe = info.get("trailingPE")
            if pe:
                out[f"{sym.lower()}_pe_trailing"] = round(float(pe), 2)
        except Exception as e:
            log.warning("index_valuation: %s trailingPE failed: %s", sym, e)
    return out


def _tracked_fwd() -> Dict[str, Any]:
    """Cap-weighted forward P/E of the estimate-covered universe —
    Σmcap/Σfwd-earnings where earnings_i = mcap_i × (eps_fwd_i/px_i).
    EY above _EY_MAX is a unit/currency mismatch (ADR EPS in local
    currency vs USD price), dropped rather than trusted."""
    mc: Dict[str, float] = {}
    for r in db.execute_query(
            "SELECT DISTINCT ON (stock_symbol) stock_symbol, payload "
            "FROM stock_insights_snapshots WHERE source='fmp_fundamentals' "
            "ORDER BY stock_symbol, generated_at DESC"):
        p = r["payload"]
        if isinstance(p, str):
            p = json.loads(p)
        f = (p or {}).get("fundamentals") or p or {}
        if f.get("market_cap"):
            mc[r["stock_symbol"]] = float(f["market_cap"])
    px = {r["symbol"]: float(r["close"]) for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, close FROM daily_bars "
        "ORDER BY symbol, date DESC")}
    near: Dict[str, Any] = {}
    for r in db.execute_query(
            "SELECT DISTINCT ON (symbol, period_end) symbol, period_end,"
            " eps_avg FROM symbol_estimate_snapshots"
            " WHERE period_end > :cut AND eps_avg IS NOT NULL"
            " ORDER BY symbol, period_end, as_of DESC",
            {"cut": date.today() + timedelta(days=60)}):
        if r["symbol"] not in near:
            near[r["symbol"]] = r["eps_avg"]
    tot_cap = tot_earn = 0.0
    n = dropped = 0
    for s, eps in near.items():
        if s not in mc or s not in px or not eps or float(eps) <= 0:
            continue
        ey = float(eps) / px[s]
        if ey > _EY_MAX:
            dropped += 1
            continue
        tot_cap += mc[s]
        tot_earn += mc[s] * ey
        n += 1
    if not n or not tot_earn:
        return {}
    return {
        "tracked_fwd_pe": round(tot_cap / tot_earn, 2),
        "tracked_names": n,
        "tracked_cap_usd": round(tot_cap, 0),
        "tracked_ey_pct": round(tot_earn / tot_cap * 100, 2),
        "dropped_unit_mismatches": dropped,
    }


def _tnx() -> tuple:
    """Latest 10Y + its vintage — the spread is only honest if the
    card can tell when TNX is stale vs the EY side's fresh inputs."""
    r = db.execute_query(
        "SELECT tnx_yield, data_date FROM macro_market_data"
        " WHERE tnx_yield IS NOT NULL ORDER BY data_date DESC LIMIT 1")
    if not r:
        return None, None
    return float(r[0]["tnx_yield"]), r[0]["data_date"]


def _verdict(spread: Optional[float]) -> Dict[str, str]:
    """ey_spread tiers — the plain-English read AND the technical
    label, both journaled so the card never has to interpret a bare
    number."""
    if spread is None:
        return {}
    if spread >= 1.5:
        return {
            "verdict": "deep_premium",
            "verdict_tone": "ok",
            "headline": "Stocks still pay a real premium over bonds — "
                        "valuation supports owning risk",
            "detail": f"earnings yield minus 10Y = {spread:+.2f}pp — "
                      "a deep equity risk premium",
        }
    if spread >= 0.5:
        return {
            "verdict": "healthy_premium",
            "verdict_tone": "ok",
            "headline": "Stocks pay more than bonds — a healthy "
                        "cushion for holding risk",
            "detail": f"earnings yield minus 10Y = {spread:+.2f}pp — "
                      "fair-to-reasonable premium",
        }
    if spread >= -0.25:
        return {
            "verdict": "thin_premium",
            "verdict_tone": "warn",
            "headline": "Thin cushion — the market needs earnings "
                        "growth to keep justifying these prices",
            "detail": f"earnings yield minus 10Y = {spread:+.2f}pp — "
                      "stocks barely out-yield risk-free rates",
        }
    return {
        "verdict": "negative_premium",
        "verdict_tone": "bad",
        "headline": "Stocks yield less than bonds — priced for "
                    "delivery, sensitive to rate shocks",
        "detail": f"earnings yield minus 10Y = {spread:+.2f}pp — "
                  "equity holders are paying for growth, not being "
                  "paid to hold risk",
    }


def evaluate(as_of: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """Compute + journal today's row; returns the payload."""
    as_of = as_of or date.today()
    mult = _spy_multiples()
    trk = _tracked_fwd()
    tnx, tnx_date = _tnx()
    ey = trk.get("tracked_ey_pct")
    spread = round(ey - tnx, 2) if ey is not None and tnx is not None \
        else None
    verdict = _verdict(spread)

    row = {
        "as_of": as_of,
        **{k: mult.get(k) for k in
           ("spy_pe_trailing", "qqq_pe_trailing")},
        **{k: trk.get(k) for k in
           ("tracked_fwd_pe", "tracked_names", "tracked_cap_usd",
            "tracked_ey_pct", "dropped_unit_mismatches")},
        "tnx_yield_pct": tnx,
        "tnx_as_of": tnx_date,
        "ey_spread_pp": spread,
        **verdict,
        "raw": {"multiples": mult, "tracked": trk,
                "tnx_as_of": str(tnx_date)},
    }
    db.execute_query(
        """
        INSERT INTO index_valuation_daily
        (as_of, spy_pe_trailing, qqq_pe_trailing, tracked_fwd_pe,
         tracked_names, tracked_cap_usd, tracked_ey_pct, tnx_yield_pct,
         tnx_as_of, ey_spread_pp, verdict, verdict_tone, headline,
         detail, raw)
        VALUES (:as_of, :spy_pe_trailing, :qqq_pe_trailing,
         :tracked_fwd_pe, :tracked_names, :tracked_cap_usd,
         :tracked_ey_pct, :tnx_yield_pct, :tnx_as_of, :ey_spread_pp,
         :verdict, :verdict_tone, :headline, :detail, :raw)
        ON CONFLICT (as_of) DO UPDATE SET
         spy_pe_trailing = EXCLUDED.spy_pe_trailing,
         qqq_pe_trailing = EXCLUDED.qqq_pe_trailing,
         tracked_fwd_pe = EXCLUDED.tracked_fwd_pe,
         tracked_names = EXCLUDED.tracked_names,
         tracked_cap_usd = EXCLUDED.tracked_cap_usd,
         tracked_ey_pct = EXCLUDED.tracked_ey_pct,
         tnx_yield_pct = EXCLUDED.tnx_yield_pct,
         tnx_as_of = EXCLUDED.tnx_as_of,
         ey_spread_pp = EXCLUDED.ey_spread_pp,
         verdict = EXCLUDED.verdict,
         verdict_tone = EXCLUDED.verdict_tone,
         headline = EXCLUDED.headline,
         detail = EXCLUDED.detail,
         raw = EXCLUDED.raw
        """,
        {**row, "raw": json.dumps(row["raw"])})
    return row


def latest() -> Optional[Dict[str, Any]]:
    """Latest journaled row + accrual-window percentiles; lazy-evals
    once per weekday so an empty journal doesn't wait for the job."""
    rows = db.execute_query(
        "SELECT * FROM index_valuation_daily"
        " ORDER BY as_of DESC LIMIT 90")
    if not rows:
        # empty journal — evaluate inline so first deploys render
        try:
            ev = evaluate()
            rows = db.execute_query(
                "SELECT * FROM index_valuation_daily"
                " ORDER BY as_of DESC LIMIT 90")
        except Exception as e:
            log.warning("index_valuation: lazy eval failed: %s", e)
            return None
        if ev is None:
            return None
    r = dict(rows[0])
    obs = len(rows)
    r["obs_n"] = obs
    # direction of travel — a thin cushion arrived at by widening is a
    # different read than one arrived at by compressing. Delta vs the
    # row nearest the lookback, in basis points.
    if r.get("ey_spread_pp") is not None and r.get("as_of"):
        cands = [x for x in rows
                 if x.get("ey_spread_pp") is not None
                 and x.get("as_of") and x["as_of"] < r["as_of"]]
        for days, key in ((7, "spread_change_1w_bps"),
                          (30, "spread_change_1m_bps")):
            if cands:
                target = r["as_of"] - timedelta(days=days)
                prev = min(cands,
                           key=lambda x: abs((x["as_of"] - target).days))
                r[key] = round(
                    (float(r["ey_spread_pp"])
                     - float(prev["ey_spread_pp"])) * 100)
            else:
                r[key] = None
    # percentile-vs-own-window — same honesty convention as
    # fwd_pe_pctile: reported with the observation count so a short
    # window is never implied to be all-time context
    if obs >= _MIN_OBS_PCTILE:
        try:
            if r.get("spy_pe_trailing") is not None:
                vals = [float(x["spy_pe_trailing"]) for x in rows
                        if x.get("spy_pe_trailing") is not None]
                cur = float(r["spy_pe_trailing"])
                r["spy_pe_pctile"] = round(
                    sum(1 for v in vals if v <= cur) / len(vals), 3)
            if r.get("ey_spread_pp") is not None:
                vals = [float(x["ey_spread_pp"]) for x in rows
                        if x.get("ey_spread_pp") is not None]
                cur = float(r["ey_spread_pp"])
                r["ey_spread_pctile"] = round(
                    sum(1 for v in vals if v <= cur) / len(vals), 3)
        except Exception:
            pass
    return r


def run() -> Dict[str, Any]:
    """Job entry — journal today's row; returns a small summary."""
    row = evaluate()
    if not row:
        return {"ok": False, "reason": "no data"}
    return {
        "ok": True,
        "as_of": str(row["as_of"]),
        "spy_pe_trailing": row.get("spy_pe_trailing"),
        "tracked_fwd_pe": row.get("tracked_fwd_pe"),
        "ey_spread_pp": row.get("ey_spread_pp"),
        "verdict": row.get("verdict"),
    }
