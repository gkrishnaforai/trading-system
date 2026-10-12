"""Relative strength — the leadership flag.

IBD-style RS: a weighted blend of 3m/6m/12m returns, percentile-ranked
across the tracked universe, plus the RS-line-new-high signal — the
single strongest 'leader in a correction' tell:

    rs_line = sym_close / SPY_close
    rs_nh   = rs_line at a 60-bar high WHILE the market corrects

A higher-low on an 85th-percentile RS name is a different trade than
the same pattern on a 30th-percentile laggard — the former is a leader
resting, the latter is just weak. Computed from canonical daily_bars —
zero extra provider calls.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _ret(closes: list[float], days: int) -> Optional[float]:
    if len(closes) < days + 1:
        return None
    base = closes[-1 - days]
    return closes[-1] / base - 1 if base else None


def compute_universe_rs(books: dict[str, list],
                        spy_bars=None) -> dict[str, dict[str, Any]]:
    """{symbol: {rs_pct, rs_score, rs_nh}} — one pass over loaded bars."""
    # RS line needs a benchmark; load SPY once if the caller's book lacks it
    spy = books.get("SPY") or spy_bars
    if spy is None:
        try:
            from app.market_data import bars as bars_mod
            spy = bars_mod.load(["SPY"], days=260).get("SPY")
        except Exception:
            spy = None
    spy_close = {str(b.date): b.close for b in (spy or [])}

    raw: dict[str, dict[str, Any]] = {}
    for sym, bars in books.items():
        if not bars or len(bars) < 70 or sym == "SPY":
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
        raw[sym] = {"rs_score": round(score, 4) if score is not None else None,
                    "rs_nh": bool(rs_nh) if rs_nh is not None else None,
                    "ret_3m": round(r3, 4) if r3 is not None else None}

    # percentile rank across the universe (rank 1-99)
    ranked = sorted((v["rs_score"], s) for s, v in raw.items()
                    if v["rs_score"] is not None)
    n = len(ranked)
    for i, (_, sym) in enumerate(ranked):
        raw[sym]["rs_pct"] = round(100 * i / max(1, n - 1))
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
