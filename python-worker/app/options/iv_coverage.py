"""Daily IV coverage — one iv_snapshots row per tracked symbol per day.

The put-entry scorers gate premium affordability on iv_hv (ATM IV vs
realized 20d vol). Rows were previously written only as a side-effect
of LEAPS scans and book marks — ~18 symbols covered, the rest of the
universe scoring a silent 0 on the premium leg. This job snapshots the
full tracked universe on the daily board cadence so the leg can fire.

Chain source is yfinance (FMP serves no options endpoints on this
tier — same constraint as the LEAPS screen). HV comes from the
canonical daily_bars store; no extra provider call for prices.
"""
from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace
from typing import Optional

logger = logging.getLogger(__name__)

MIN_DTE = 21        # put tenor is ~30-60d; first expiry ≥3w skips weekly noise
ATM_BAND = 0.10     # median IV of strikes within ±10% of spot
INDEX_HEDGES = ("QQQ", "SPY")   # crash_alpha's hedge gate reads QQQ


def _universe() -> list[str]:
    """Same universe the put scanner iterates, plus the index hedges."""
    from app.database import db
    rows = db.execute_query(
        "SELECT symbol FROM stocks WHERE momentum_state IS NOT NULL")
    return sorted({r["symbol"] for r in rows} | set(INDEX_HEDGES))


def _close_histories(symbols: list[str]) -> dict[str, list]:
    """Last ~40 daily closes per symbol as duck-typed bars — enough for
    hv20 via the canonical indicators.realized_vol (same object shape
    leaps_book builds from yf.download)."""
    from app.database import db
    rows = db.execute_query(
        "SELECT symbol, date, close FROM ("
        "  SELECT symbol, date, close,"
        "         ROW_NUMBER() OVER (PARTITION BY symbol"
        "                            ORDER BY date DESC) rn"
        "  FROM daily_bars WHERE symbol = ANY(:syms)) t"
        " WHERE rn <= 40 ORDER BY symbol, date",
        {"syms": list(symbols)})
    out: dict[str, list] = {}
    for r in rows:
        if r["close"] is None:
            continue
        out.setdefault(r["symbol"], []).append(SimpleNamespace(
            timestamp=r["date"], close=float(r["close"]),
            adj_close=None))
    return out


_IV_MIN, _IV_MAX = 0.05, 2.5   # sanity band: <5% or >250% IV = junk data


def _atm_put_iv(sym: str, spot: Optional[float]) -> Optional[float]:
    """Median IV of near-ATM options at the nearest expiry ≥ MIN_DTE.

    Only live-quoted strikes (bid>0 AND ask>0) count: outside market
    hours Yahoo zeroes quotes and reports quantized placeholder IVs
    (0.0625/0.125…) on dead contracts. Returns None when no live print
    exists — the scorer reads the latest snapshot regardless of date,
    so yesterday's honest print carries forward instead of writing a
    fabricated one."""
    if not spot:
        return None
    try:
        import pandas as pd
        import yfinance as yf
        t = yf.Ticker(sym)
        today = date.today()
        exps = [e for e in (t.options or [])
                if (date.fromisoformat(e) - today).days >= MIN_DTE]
        if not exps:
            return None
        for exp in exps[:3]:
            try:
                chain = t.option_chain(exp)
            except Exception:
                continue
            df = pd.concat([chain.puts, chain.calls])
            band = df[(df["strike"] > spot * (1 - ATM_BAND))
                      & (df["strike"] < spot * (1 + ATM_BAND))]
            if band.empty:
                continue
            live = band[(band["bid"] > 0) & (band["ask"] > 0)]
            ivs = pd.to_numeric(live["impliedVolatility"],
                                errors="coerce").dropna()
            ivs = ivs[(ivs > _IV_MIN) & (ivs < _IV_MAX)]
            if len(ivs) >= 3:
                return float(ivs.median())
        return None
    except Exception as exc:
        logger.debug("iv chain %s: %s", sym, exc)
        return None


def refresh_iv_coverage(symbols: Optional[list[str]] = None,
                        concurrency: int = 4) -> dict:
    """Snapshot ATM put IV + hv20 for every tracked symbol. Idempotent
    per (symbol, day); safe to re-run. Returns honest counters."""
    from app.database import db
    from app.market_data import indicators as ind

    syms = symbols or _universe()
    bars_by_sym = _close_histories(syms)

    def _one(sym: str) -> tuple[str, str, Optional[tuple]]:
        bars = bars_by_sym.get(sym) or []
        hv = ind.realized_vol(bars, 20) if bars else None
        spot = float(bars[-1].close) if bars else None
        if hv is None:
            return sym, "no_hv", None
        iv = _atm_put_iv(sym, spot)
        if iv is None:
            return sym, "no_live_iv", None
        return sym, "ok", (iv, hv)

    written = no_live_iv = no_hv = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for sym, status, res in pool.map(_one, syms):
            if status == "no_hv":
                no_hv += 1
                continue
            if status == "no_live_iv":
                no_live_iv += 1
                continue
            iv, hv = res
            try:
                db.execute_update(
                    "INSERT INTO iv_snapshots (symbol, as_of, atm_iv,"
                    " hv20, iv_hv) VALUES (:s, CURRENT_DATE, :iv, :hv,"
                    " :r) ON CONFLICT (symbol, as_of) DO UPDATE SET"
                    " atm_iv=EXCLUDED.atm_iv, hv20=EXCLUDED.hv20,"
                    " iv_hv=EXCLUDED.iv_hv",
                    {"s": sym, "iv": round(iv, 5), "hv": round(hv, 5),
                     "r": round(iv / hv, 3)})
                written += 1
            except Exception as exc:
                logger.warning("iv upsert %s: %s", sym, exc)

    return {"symbols": len(syms), "written": written,
            "no_live_iv": no_live_iv, "no_hv": no_hv,
            "as_of": str(date.today())}
