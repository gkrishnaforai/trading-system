"""Price-target watch — catches analyst repricing early, for swing entries.

FMP's grades/ratings endpoints are 404 on this plan, but
price-target-summary works. The signal: lastMonthAvgPriceTarget pulling
away from lastQuarterAvgPriceTarget while fresh PTs keep printing
(lastMonthCount) = analysts are actively re-rating the name. Snapshots
persist daily so deltas and clusters are queryable, and significant moves
fire a `pt_repricing` alert into the actionable inbox.

Thresholds: momentum >= +5% month-vs-quarter with >=2 fresh PTs this month
= MODERATE; >= +10% with >=3 = HIGH (a repricing wave, not one note).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

PT_MOMENTUM_ALERT = 0.05      # month avg vs quarter avg
PT_MOMENTUM_HIGH = 0.10
PT_MIN_FRESH = 2              # lastMonthCount — new PTs printing
PT_MIN_FRESH_HIGH = 3

_state: dict[str, Any] = {
    "running": False, "last_run_at": None, "scanned": 0, "error": None}


def pt_watch_status() -> dict[str, Any]:
    return dict(_state)


def _universe_symbols() -> dict[str, dict]:
    """Alert universe (portfolio ∪ watchlist) + sector/theme candidate
    pools — upgrades matter most on names we don't hold yet."""
    from app.alerts import scanner as alert_scanner
    from app.screener.sector_candidates import SECTOR_POOLS, THEME_BASKETS
    scope = alert_scanner.universe()
    pool_syms = {s for pool in SECTOR_POOLS.values() for s in pool}
    pool_syms |= {s for t in THEME_BASKETS.values() for s in t["members"]}
    for s in pool_syms:
        scope.setdefault(s, {})
    return scope


def _fetch(fmp, symbol: str) -> Optional[dict]:
    try:
        summary = fmp.get_price_target_summary(symbol) or []
        cons = fmp.get_price_target_consensus(symbol) or []
        s = summary[0] if summary else {}
        c = cons[0] if cons else {}
        if not s and not c:
            return None
        return {
            "month_avg": s.get("lastMonthAvgPriceTarget"),
            "month_count": s.get("lastMonthCount"),
            "quarter_avg": s.get("lastQuarterAvgPriceTarget"),
            "quarter_count": s.get("lastQuarterCount"),
            "year_avg": s.get("lastYearAvgPriceTarget"),
            "year_count": s.get("lastYearCount"),
            "consensus": c.get("targetConsensus"),
            "median": c.get("targetMedian"),
            "high": c.get("targetHigh"),
            "low": c.get("targetLow"),
        }
    except Exception as exc:
        logger.debug("pt fetch failed %s: %s", symbol, exc)
        return None


async def run_pt_watch(svc=None) -> dict[str, Any]:
    """Snapshot PT data for the universe; alert on repricing waves."""
    from app.alerts import scanner as alert_scanner
    from app.alerts.models import AlertItem
    from app.database import db
    from app.market_data import MarketDataService
    from app.providers.financial_modeling_prep.client import EnhancedFMPClient

    if _state["running"]:
        return {"status": "already_running"}
    _state.update(running=True, error=None)
    try:
        svc = svc or MarketDataService()
        fmp = EnhancedFMPClient.from_settings()
        scope = _universe_symbols()
        sem = asyncio.Semaphore(6)
        today = date.today()

        async def _one(sym: str):
            async with sem:
                try:
                    return sym, await asyncio.wait_for(
                        asyncio.to_thread(_fetch, fmp, sym), timeout=20)
                except Exception:
                    return sym, None

        results = await asyncio.gather(*(_one(s) for s in sorted(scope)))
        alerts: list[AlertItem] = []
        scanned = 0
        for sym, d in results:
            if not d:
                continue
            scanned += 1
            price = None
            try:
                bars = await asyncio.wait_for(
                    svc.get_ohlcv(sym, period="5d"), timeout=15)
                price = bars[-1].close if bars else None
            except Exception:
                pass
            db.execute_update(
                """
                INSERT INTO pt_snapshots
                    (symbol, as_of, month_avg, month_count, quarter_avg,
                     quarter_count, year_avg, year_count, consensus, median,
                     high, low, price)
                VALUES (:s, :d, :ma, :mc, :qa, :qc, :ya, :yc, :c, :m, :h, :l, :p)
                ON CONFLICT (symbol, as_of) DO UPDATE SET
                    month_avg=EXCLUDED.month_avg, month_count=EXCLUDED.month_count,
                    quarter_avg=EXCLUDED.quarter_avg,
                    quarter_count=EXCLUDED.quarter_count,
                    year_avg=EXCLUDED.year_avg, year_count=EXCLUDED.year_count,
                    consensus=EXCLUDED.consensus, median=EXCLUDED.median,
                    high=EXCLUDED.high, low=EXCLUDED.low, price=EXCLUDED.price
                """,
                {"s": sym, "d": today, "ma": d.get("month_avg"),
                 "mc": d.get("month_count"), "qa": d.get("quarter_avg"),
                 "qc": d.get("quarter_count"), "ya": d.get("year_avg"),
                 "yc": d.get("year_count"), "c": d.get("consensus"),
                 "m": d.get("median"), "h": d.get("high"),
                 "l": d.get("low"), "p": price})

            mom = (d["month_avg"] / d["quarter_avg"] - 1
                   if d.get("month_avg") and d.get("quarter_avg") else None)
            fresh = d.get("month_count") or 0
            if mom is None or abs(mom) < PT_MOMENTUM_ALERT or fresh < PT_MIN_FRESH:
                continue
            direction = "POSITIVE" if mom > 0 else "NEGATIVE"
            high = abs(mom) >= PT_MOMENTUM_HIGH and fresh >= PT_MIN_FRESH_HIGH
            flags = scope.get(sym) or {}
            upside = (d["consensus"] / price - 1
                      if d.get("consensus") and price else None)
            alerts.append(AlertItem(
                symbol=sym, event_type="pt_repricing",
                direction=direction,
                materiality="HIGH" if high else "MODERATE",
                title=(f"PT repricing: month avg ${d['month_avg']:.0f} vs "
                       f"quarter ${d['quarter_avg']:.0f} ({mom:+.0%}), "
                       f"{fresh} fresh PTs this month"),
                detail={
                    "bucket": "actionable", "kind": "analyst",
                    "month_avg": d.get("month_avg"),
                    "month_count": fresh,
                    "quarter_avg": d.get("quarter_avg"),
                    "momentum_pct": round(mom * 100, 1),
                    "consensus": d.get("consensus"),
                    "consensus_upside_pct": round(upside * 100, 1)
                    if upside is not None else None,
                    "price": price,
                    "note": "FMP grades feed is 404 on this plan — PT "
                            "repricing is the live upgrade signal",
                },
                fingerprint=("ptrep:" + hashlib.sha1(
                    f"{sym}|{today}|{fresh}|{d['month_avg']}".encode()
                ).hexdigest()[:16]),
                source="pt_watch",
                source_timestamp=datetime.now(timezone.utc),
                in_portfolio=bool(flags.get("in_portfolio")),
                in_watchlist=bool(flags.get("in_watchlist")),
                priority_score=None,
            ))

        for a in alerts:
            a.priority_score = alert_scanner.priority_score(a)
        inserted, skipped = alert_scanner.persist(alerts)
        _state.update(scanned=scanned,
                      last_run_at=datetime.now(timezone.utc).isoformat())
        return {"status": "completed", "scanned": scanned,
                "alerts": inserted, "skipped": skipped}
    except Exception as exc:
        logger.error("pt watch failed: %s", exc, exc_info=True)
        _state["error"] = str(exc)
        return {"status": "error", "error": str(exc)}
    finally:
        _state["running"] = False


def pt_watch_board(limit: int = 60) -> dict[str, Any]:
    """Latest snapshot per symbol with the repricing read."""
    from app.database import db
    rows = db.execute_query(
        """
        SELECT DISTINCT ON (symbol) *
        FROM pt_snapshots ORDER BY symbol, as_of DESC
        """)
    try:
        scope = _universe_symbols()
    except Exception:
        scope = {}
    board = []
    for r in rows:
        ma, qa = r.get("month_avg"), r.get("quarter_avg")
        mom = (float(ma) / float(qa) - 1) if ma and qa else None
        cons, price = r.get("consensus"), r.get("price")
        upside = float(cons) / float(price) - 1 if cons and price else None
        board.append({
            "symbol": r["symbol"], "as_of": str(r["as_of"]),
            "month_avg": float(ma) if ma else None,
            "month_count": r.get("month_count"),
            "quarter_avg": float(qa) if qa else None,
            "pt_momentum_pct": round(mom * 100, 1) if mom is not None else None,
            "consensus": float(cons) if cons else None,
            "upside_pct": round(upside * 100, 1) if upside is not None else None,
            "price": float(price) if price else None,
            "in_portfolio": bool((scope.get(r["symbol"]) or {})
                                 .get("in_portfolio")),
            "in_watchlist": bool((scope.get(r["symbol"]) or {})
                                 .get("in_watchlist")),
        })
    board.sort(key=lambda r: -(r["pt_momentum_pct"] or -99))
    return {"symbols": board[:limit],
            "as_of": str(date.today()), "scanned": len(board)}
