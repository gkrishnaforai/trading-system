"""Relative strength — the leadership flag.

IBD-style RS: a weighted blend of 3m/6m/12m returns, percentile-ranked
across the tracked universe, plus the RS-line-new-high signal — the
single strongest 'leader in a correction' tell:

    rs_line = sym_close / bench_close
    rs_nh   = rs_line at a 60-bar high WHILE the market corrects

A higher-low on an 85th-percentile RS name is a different trade than
the same pattern on a 30th-percentile laggard — the former is a leader
resting, the latter is just weak. Computed from canonical daily_bars —
zero extra provider calls.

Resilience layer — the day-level pattern the point-in-time score can't
see: does the name defend REPEATEDLY on red benchmark days, then
out-perform on green ones? Hit-rates, not capture ratios — one outlier
day wrecks a mean; a fraction-of-days read can't be gamed by a single
session:

    down_cap  = P(stock beats bench | bench day <= -0.4%), ~60d window
    up_cap    = P(stock beats bench | bench day >= +0.4%)
    rebound_x = median(stock_ret - bench_ret) on green days

Benchmark is the finest applicable: industry theme ETF (semis → SMH,
software → IGV), else the GICS sector ETF, else SPY — 'leader of the
group' is a sector-relative question, and a semi holding up vs SMH
says more than holding up vs SPY.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_RED, _GREEN = -0.004, 0.004      # benchmark day classification band
_RS_WIN = 60                      # sessions the pattern is judged on
_MIN_RED, _MIN_GREEN = 5, 5       # min days for a non-vacuous hit-rate


def _ret(closes: list[float], days: int) -> Optional[float]:
    if len(closes) < days + 1:
        return None
    base = closes[-1 - days]
    return closes[-1] / base - 1 if base else None


def _daily_rets(bars) -> dict[str, float]:
    """date → simple return."""
    out: dict[str, float] = {}
    prev = None
    for b in bars:
        if prev and prev > 0:
            out[str(b.date)] = b.close / prev - 1
        prev = b.close
    return out


def _resilience(sym_rets: dict[str, float],
                bench_rets: dict[str, float]) -> dict[str, Any]:
    """Down-day defense + rebound-day offense vs the benchmark, as
    hit-rates over the last ~60 shared sessions."""
    days = sorted(set(sym_rets) & set(bench_rets))[-_RS_WIN:]
    red = [(sym_rets[d], bench_rets[d]) for d in days
           if bench_rets[d] <= _RED]
    green = [(sym_rets[d], bench_rets[d]) for d in days
             if bench_rets[d] >= _GREEN]
    out: dict[str, Any] = {
        "down_n": len(red), "up_n": len(green),
        "down_cap": None, "up_cap": None, "rebound_x": None}
    if len(red) >= _MIN_RED:
        out["down_cap"] = round(
            sum(1 for s, b in red if s > b) / len(red), 2)
    if len(green) >= _MIN_GREEN:
        out["up_cap"] = round(
            sum(1 for s, b in green if s > b) / len(green), 2)
        xs = sorted(s - b for s, b in green)
        out["rebound_x"] = round(xs[len(xs) // 2], 4)
    return out


def _quality_bucket(rs_pct: Optional[int],
                    res: dict) -> Optional[str]:
    """Named resilience class — 'resilient' = defends repeatedly AND
    rebounds harder; 'fragile' = can't defend red days; 'leader' needs
    the rank to back it. Selection-context vocabulary, not a score."""
    if res.get("down_cap") is None:
        return None
    if (res["down_cap"] >= 0.6
            and (res.get("rebound_x") or 0) > 0
            and (rs_pct or 0) >= 50):
        return "resilient"
    if res["down_cap"] < 0.4:
        return "fragile"
    return "neutral"


def _bench_map(symbols: list[str]) -> dict[str, str]:
    """symbol → benchmark ticker: industry theme ETF where the mapping
    fires, else GICS sector ETF, else SPY."""
    from app.database import db
    from app.market_regime.rotation import (
        _SECTOR_TO_ETF, _INDUSTRY_TO_THEME_ETF)
    try:
        rows = db.execute_query(
            "SELECT symbol, sector, industry FROM stocks"
            " WHERE symbol = ANY(:s)", {"s": list(symbols)})
    except Exception:
        rows = []
    out = {}
    for r in rows:
        ind = (r.get("industry") or "").lower()
        bench = None
        for pat, etf in _INDUSTRY_TO_THEME_ETF:
            if pat in ind:
                bench = etf
                break
        if bench is None:
            bench = _SECTOR_TO_ETF.get((r.get("sector") or "").lower())
        out[r["symbol"].upper()] = bench or "SPY"
    return out


def compute_universe_rs(books: dict[str, list],
                        spy_bars=None) -> dict[str, dict[str, Any]]:
    """{symbol: {rs_pct, rs_score, rs_nh, ret_3m, rs_bench, down_cap,
    down_n, up_cap, up_n, rebound_x, rs_quality}} — one pass over
    loaded bars. books already carries sector/theme ETF bars from the
    momentum refresh; ETFs are benchmarks, never scored."""
    # RS line needs a benchmark; load SPY once if the caller's book lacks it
    spy = books.get("SPY") or spy_bars
    if spy is None:
        try:
            from app.market_data import bars as bars_mod
            spy = bars_mod.load(["SPY"], days=260).get("SPY")
        except Exception:
            spy = None
    spy_close = {str(b.date): b.close for b in (spy or [])}

    from app.market_regime.rotation import SECTOR_NAMES, THEME_ETFS
    _ETF = set(SECTOR_NAMES) | set(THEME_ETFS) | {
        "SPY", "^VIX", "SOXX", "SOXL", "SOXS"}
    stock_syms = [s for s in books if s not in _ETF]
    bench_map = _bench_map(stock_syms)
    bench_rets: dict[str, dict[str, float]] = {}

    raw: dict[str, dict[str, Any]] = {}
    for sym in stock_syms:
        bars = books.get(sym) or []
        if not bars or len(bars) < 70:
            continue
        closes = [b.close for b in bars]
        r3, r6, r12 = (_ret(closes, 63), _ret(closes, 126),
                       _ret(closes, 252))
        # IBD-weighted: recent action counts most
        parts = [(0.5, r3), (0.3, r6), (0.2, r12)]
        num = den = 0.0
        for w, r in parts:
            if r is not None:
                num += w * r
                den += w
        score = num / den if den else None
        rs_nh = None
        if spy_close:
            line = [b.close / spy_close[str(b.date)]
                    for b in bars[-61:] if str(b.date) in spy_close]
            if len(line) >= 40:
                rs_nh = line[-1] >= max(line[:-1])
        # resilience vs the group benchmark — theme/sector ETF where
        # known + bars loaded, SPY otherwise
        bench = bench_map.get(sym, "SPY")
        bbars = books.get(bench) or spy
        if not bbars or len(bbars) < 70:
            bench, bbars = "SPY", spy
        if bench not in bench_rets:
            bench_rets[bench] = _daily_rets(bbars or [])
        res = _resilience(_daily_rets(bars),
                          bench_rets.get(bench) or {})
        entry: dict[str, Any] = {
            "rs_score": round(score, 4) if score is not None else None,
            "rs_nh": bool(rs_nh) if rs_nh is not None else None,
            "ret_3m": round(r3, 4) if r3 is not None else None,
            "rs_bench": bench}
        entry.update(res)
        raw[sym] = entry

    # percentile rank across the universe (rank 1-99)
    ranked = sorted((v["rs_score"], s) for s, v in raw.items()
                    if v["rs_score"] is not None)
    n = len(ranked)
    for i, (_, sym) in enumerate(ranked):
        raw[sym]["rs_pct"] = round(100 * i / max(1, n - 1))
    for sym, v in raw.items():
        v["rs_quality"] = _quality_bucket(v.get("rs_pct"), v)
    return raw


def merge_into_momentum_detail(rs: dict[str, dict]) -> int:
    """jsonb-merge rs fields into stocks.momentum_detail — keeps ONE
    detail blob per symbol instead of a parallel store."""
    from app.database import db
    import json
    n = 0
    for sym, v in rs.items():
        try:
            db.execute_query(
                "UPDATE stocks SET momentum_detail = COALESCE(momentum_detail,"
                " '{}'::jsonb) || CAST(:patch AS jsonb), updated_at = now()"
                " WHERE symbol = :sym",
                {"patch": json.dumps(v), "sym": sym})
            n += 1
        except Exception as exc:
            logger.debug("rs merge %s: %s", sym, exc)
    return n
