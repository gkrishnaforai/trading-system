"""Sector momentum + rotation board — which sector leads the tape and where
fresh capital is arriving before the crowd.

Fund-flow data isn't available on the current plan, so "funding" is proxied
the way desks read it: price × volume action on the sector ETFs. Up moves on
expanding volume = inflow; down moves on expanding volume = outflow; a strong
recent week in a still-weak trend = early rotation ("rotating in" — the
sector accumulating before momentum confirms).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from app.market_data import indicators as ind
from app.market_regime.universe import SECTOR_ETFS

logger = logging.getLogger(__name__)

SECTOR_NAMES = {
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
    "XLV": "Health Care", "XLY": "Consumer Disc.", "XLP": "Consumer Staples",
    "XLI": "Industrials", "XLU": "Utilities", "XLRE": "Real Estate",
    "XLB": "Materials", "XLC": "Communication",
}

# Thematic ETFs — the "which theme is getting funded" read that the 11 GICS
# sectors blur: semis vs software vs biotech vs regional banks etc.
THEME_ETFS = {
    "SMH": "Semiconductors", "IGV": "Software", "XBI": "Biotech",
    "KRE": "Regional Banks", "ITA": "Aerospace & Defense",
    "ARKK": "Innovation Growth", "TAN": "Solar", "XRT": "Retail",
}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# fmp_company_profiles.sector -> sector ETF (GICS naming variants)
_SECTOR_TO_ETF = {
    "technology": "XLK", "financial services": "XLF", "financials": "XLF",
    "energy": "XLE", "healthcare": "XLV", "health care": "XLV",
    "consumer cyclical": "XLY", "consumer discretionary": "XLY",
    "consumer defensive": "XLP", "consumer staples": "XLP",
    "industrials": "XLI", "utilities": "XLU", "real estate": "XLRE",
    "basic materials": "XLB", "materials": "XLB",
    "communication services": "XLC", "communication": "XLC",
}


def _action_tag(score: float, r5: Optional[float], flow: str,
                above50: bool) -> str:
    """Two-horizon call: ride confirmed momentum now vs accumulate early
    rotation for the 6-month view."""
    r5 = r5 or 0.0
    if flow == "📉 outflow":
        return "⚠ avoid/trim"
    if flow == "↩ rotating in":
        return "🏦 accumulate 6m"      # capital arriving before the crowd
    if above50 and score >= 55:
        if r5 >= 0.08:
            return "⚡ swing — extended, buy the pullback"
        return "⚡ swing now"
    if above50:
        return "📈 holding trend"
    return "💤 wait"


def _swing_names_by_sector() -> dict[str, list[str]]:
    """Universe symbols per sector ETF that are in uptrend in the latest
    screen run — 'who inside this leading sector is actually buyable'.
    Coverage grows as fmp_company_profiles fills in."""
    try:
        from app.database import db
        profs = db.execute_query(
            "SELECT symbol, sector FROM fmp_company_profiles WHERE sector IS NOT NULL")
        sym_sector = {
            p["symbol"].upper(): _SECTOR_TO_ETF.get(str(p["sector"]).lower())
            for p in profs
        }
        latest = db.execute_query(
            "SELECT results FROM screen_runs ORDER BY ran_at DESC LIMIT 1")
        if not latest:
            return {}
        out: dict[str, list[str]] = {}
        for r in latest[0].get("results") or []:
            etf = sym_sector.get(str(r.get("symbol", "")).upper())
            if (etf and r.get("stock_permission") == "allowed"
                    and (r.get("score") or 0) >= 60):
                out.setdefault(etf, []).append(r["symbol"])
        return out
    except Exception as exc:
        logger.debug("sector swing names unavailable: %s", exc)
        return {}


def _flow_tag(r1: Optional[float], r5: Optional[float], r20: Optional[float],
              volume_ratio: Optional[float], above50: bool) -> str:
    """Capital-flow read from price×volume only — no fund-flow feed needed."""
    r5, r20 = r5 or 0.0, r20 or 0.0
    vol_up = bool(volume_ratio and volume_ratio >= 1.2)
    if r5 > 0.005 and vol_up:
        # volume-backed buying; below SMA50 it's early rotation, above it's
        # confirmed inflow leadership
        return "↩ rotating in" if not above50 else "🔥 inflow"
    if r5 > 0.02 and r20 <= 0.005:
        return "↩ rotating in"      # fresh money into a laggard, quiet tape
    if r5 < -0.005 and vol_up:
        return "📉 outflow"         # distribution — leaving on volume
    if above50 and r20 > 0.01:
        return "📈 leading"
    return "💤 quiet"


def _momentum_score(r5, r20, r60, vs_spy20, above50, above200,
                    volume_ratio, r1) -> float:
    """0-100 blend: trend strength + leadership + 5d acceleration + volume
    participation. Bounded component clamps keep one input from dominating."""
    score = 50.0
    score += _clamp((r20 or 0) * 300, -20, 20)
    score += _clamp((vs_spy20 or 0) * 400, -15, 15)
    accel = (r5 or 0) - (r20 or 0) / 4          # week pace vs month run-rate
    score += _clamp(accel * 500, -15, 15)
    score += 5 if above50 else -5
    score += 5 if above200 else -5
    if volume_ratio is not None and volume_ratio >= 1.2:
        score += 5 if (r1 or 0) > 0 else -5
    return _clamp(score, 0, 100)


async def sector_rotation(max_concurrency: int = 6) -> dict[str, Any]:
    """Momentum + flow board across the 11 GICS sector ETFs and theme ETFs."""
    from app.market_data.service import get_market_data_service

    svc = get_market_data_service()
    spy_bars = await svc.get_ohlcv("SPY", period="1y")
    spy20 = ind.returns(spy_bars, 20) if len(spy_bars) >= 21 else None
    swing_names = _swing_names_by_sector()
    sem = asyncio.Semaphore(max_concurrency)

    async def _one(symbol: str, name: str, group: str) -> Optional[dict]:
        async with sem:
            try:
                bars = await svc.get_ohlcv(symbol, period="1y")
                if len(bars) < 60:
                    return None
                r1 = ind.returns(bars, 1)
                r5 = ind.returns(bars, 5)
                r20 = ind.returns(bars, 20)
                r60 = ind.returns(bars, 60)
                vr = ind.volume_ratio(bars)
                price = ind.closes(bars).iloc[-1]
                s50, s200 = ind.sma(bars, 50), ind.sma(bars, 200)
                above50 = bool(s50 and price > s50)
                above200 = bool(s200 and price > s200)
                vs_spy20 = (r20 - spy20) if (r20 is not None and spy20 is not None) else None
                score = _momentum_score(
                    r5, r20, r60, vs_spy20, above50, above200, vr, r1)
                flow = _flow_tag(r1, r5, r20, vr, above50)
                return {
                    "symbol": symbol, "name": name, "group": group,
                    "price": round(price, 2),
                    "ret1": r1, "ret5": r5, "ret20": r20, "ret60": r60,
                    "vs_spy20": vs_spy20,
                    "volume_ratio": vr,
                    "above_sma50": above50, "above_sma200": above200,
                    "score": round(score, 1),
                    "flow": flow,
                    "action": _action_tag(score, r5, flow, above50),
                    "swing_names": swing_names.get(symbol, []),
                    "as_of": str(bars[-1].timestamp.date()) if bars else None,
                }
            except Exception as exc:
                logger.debug("sector rotation skip %s: %s", symbol, exc)
                return None

    tasks = ([_one(s, n, "sector") for s, n in SECTOR_NAMES.items() if s in SECTOR_ETFS]
             + [_one(s, n, "theme") for s, n in THEME_ETFS.items()])
    rows = [r for r in await asyncio.gather(*tasks) if r]
    sectors = sorted((r for r in rows if r["group"] == "sector"),
                     key=lambda r: -r["score"])
    themes = sorted((r for r in rows if r["group"] == "theme"),
                    key=lambda r: -r["score"])
    return {
        "sectors": sectors,
        "themes": themes,
        "leading": [r["symbol"] for r in sectors[:3]],
        "rotating_in": [r["symbol"] for r in rows if r["flow"] == "↩ rotating in"],
        "outflows": [r["symbol"] for r in rows if r["flow"] == "📉 outflow"],
        "swing_now": [r["symbol"] for r in rows
                      if r["action"].startswith("⚡")],
        "accumulate_6m": [r["symbol"] for r in rows
                          if r["action"] == "🏦 accumulate 6m"],
        "spy": {"ret20": spy20},
        "as_of": rows[0]["as_of"] if rows else None,
    }
