"""Extended-hours movers — post-market and pre-market quotes via Yahoo
(FMP's after-market endpoints are 403 on the current plan).

Covers the alert universe plus the movers feed's top gainers so the board
answers both 'what's moving out-of-hours' and 'is anything I hold/watch
moving'. A held or watched name moving >=2% produces an alert — that's the
planning signal (gap vs setup), not a trade trigger.

Two sessions share the same machinery/table (session column):
  post = after-hours board (postMarket* fields vs regular close)
  pre  = pre-market board (preMarket* fields vs previous close)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

ALERT_PCT = 2.0             # held/watch names only
TOP_GAINERS_N = 3
SESSIONS = ("post", "pre")

_states: dict[str, dict[str, Any]] = {
    s: {"running": False, "last_run_at": None, "results": None, "error": None}
    for s in SESSIONS
}


def session_status(session: str = "post") -> dict[str, Any]:
    st_ = _states[session]
    return {"running": st_["running"], "last_run_at": st_["last_run_at"],
            "error": st_["error"]}


# Back-compat names for the post session endpoints.
def afterhours_status() -> dict[str, Any]:
    return session_status("post")


def _session_quote(symbol: str, session: str) -> Optional[dict]:
    """yfinance .info carries live extended-hours quote fields."""
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        if session == "pre":
            pm_price = info.get("preMarketPrice")
            reg = info.get("regularMarketPreviousClose") or \
                info.get("regularMarketPrice")
            pm_pct = info.get("preMarketChangePercent")
            pm_time = info.get("preMarketTime")
        else:
            pm_price = info.get("postMarketPrice")
            reg = info.get("regularMarketPrice") or \
                info.get("regularMarketPreviousClose")
            pm_pct = info.get("postMarketChangePercent")
            pm_time = info.get("postMarketTime")
        if not pm_price or not reg:
            return None
        pct = pm_pct if pm_pct is not None else (pm_price / reg - 1) * 100
        return {"reg_close": float(reg), "ah_price": float(pm_price),
                "ah_pct": round(float(pct), 2), "ah_time": pm_time}
    except Exception:
        return None


def _save_moves(rows: list[dict], session: str) -> None:
    from app.database import db
    for r in rows:
        try:
            db.execute_update(
                """
                INSERT INTO afterhours_moves
                    (symbol, as_of_date, session, reg_close, ah_price, ah_pct,
                     ah_time, in_portfolio, in_watchlist)
                VALUES (:s, :d, :ses, :rc, :ap, :pct, :t, :p, :w)
                ON CONFLICT (symbol, as_of_date, session) DO UPDATE SET
                    reg_close = EXCLUDED.reg_close,
                    ah_price = EXCLUDED.ah_price,
                    ah_pct = EXCLUDED.ah_pct,
                    ah_time = EXCLUDED.ah_time,
                    in_portfolio = EXCLUDED.in_portfolio,
                    in_watchlist = EXCLUDED.in_watchlist,
                    updated_at = now()
                """,
                {"s": r["symbol"], "d": date.today(), "ses": session,
                 "rc": r["reg_close"], "ap": r["ah_price"], "pct": r["ah_pct"],
                 "t": datetime.fromtimestamp(r["ah_time"], tz=timezone.utc)
                 if r.get("ah_time") else None,
                 "p": r["in_portfolio"], "w": r["in_watchlist"]},
            )
        except Exception as exc:
            logger.debug("session move save failed %s: %s", r["symbol"], exc)


def _emit_alerts(rows: list[dict], session: str) -> int:
    """Move >= ±2% on a held/watch name → alert. Fingerprint per day+session."""
    from app.alerts.models import AlertItem
    from app.alerts import scanner as alert_scanner
    tag = "pre-market" if session == "pre" else "after-hours"
    items = []
    for r in rows:
        if not (r["in_portfolio"] or r["in_watchlist"]):
            continue
        if abs(r["ah_pct"]) < ALERT_PCT:
            continue
        direction = "POSITIVE" if r["ah_pct"] > 0 else "NEGATIVE"
        held = "held" if r["in_portfolio"] else "watched"
        items.append(AlertItem(
            symbol=r["symbol"],
            event_type="pre_market" if session == "pre" else "after_hours",
            direction=direction,
            materiality="HIGH" if abs(r["ah_pct"]) >= 4 else "MODERATE",
            title=f"{tag} {r['ah_pct']:+.1f}% → ${r['ah_price']:,.2f} "
                  f"(ref ${r['reg_close']:,.2f})",
            detail={"ah_pct": r["ah_pct"], "ah_price": r["ah_price"],
                    "reg_close": r["reg_close"], "scope": held,
                    "session": session},
            fingerprint=f"{session}:{r['symbol']}:{date.today()}",
            source="afterhours",
            in_portfolio=r["in_portfolio"], in_watchlist=r["in_watchlist"],
        ))
    if items:
        try:
            inserted, _ = alert_scanner.persist(items)
            return inserted
        except Exception as exc:
            logger.debug("session alert persist failed: %s", exc)
    return 0


async def run_session_job(session: str = "post") -> dict[str, Any]:
    st_ = _states[session]
    if st_["running"]:
        return {"status": "already_running"}
    st_["running"] = True
    st_["error"] = None
    try:
        from app.alerts import scanner as alert_scanner
        uni = alert_scanner.universe()
        symbols = sorted(uni)
        # top gainers from the last movers feed may sit outside the universe
        try:
            from app.providers.financial_modeling_prep.client import EnhancedFMPClient
            raw = await asyncio.wait_for(asyncio.to_thread(
                EnhancedFMPClient.from_settings().get_market_movers),
                timeout=30) or {}
            for g in (raw.get("gainers") or [])[:15]:
                sym = str(g.get("symbol") or "").upper()
                if sym and sym not in symbols:
                    symbols.append(sym)
        except Exception:
            pass

        sem = asyncio.Semaphore(6)

        async def _one(sym):
            async with sem:
                try:
                    q = await asyncio.wait_for(
                        asyncio.to_thread(_session_quote, sym, session),
                        timeout=20)
                except Exception:
                    return None
                if not q:
                    return None
                flags = uni.get(sym) or {}
                return {"symbol": sym, **q,
                        "in_portfolio": bool(flags.get("in_portfolio")),
                        "in_watchlist": bool(flags.get("in_watchlist"))}

        rows = [r for r in await asyncio.gather(*(_one(s) for s in symbols))
                if r]
        rows.sort(key=lambda r: -r["ah_pct"])
        await asyncio.to_thread(_save_moves, rows, session)
        alerted = await asyncio.to_thread(_emit_alerts, rows, session)

        universe_rows = [r for r in rows
                         if r["in_portfolio"] or r["in_watchlist"]]
        st_["results"] = {
            "as_of": str(date.today()),
            "session": session,
            "top_gainers": rows[:TOP_GAINERS_N],
            "universe_movers": universe_rows,
            "scanned": len(rows),
            "alerts_emitted": alerted,
        }
        return {"status": "completed", "scanned": len(rows),
                "alerts": alerted}
    except Exception as exc:
        logger.error("%s-hours scan failed: %s", session, exc)
        st_["error"] = str(exc)
        return {"status": "error", "error": str(exc)}
    finally:
        st_["running"] = False
        st_["last_run_at"] = datetime.now(timezone.utc).isoformat()


async def run_afterhours_job() -> dict[str, Any]:
    return await run_session_job("post")


def session_results(session: str = "post") -> dict[str, Any]:
    """Latest board — memory first, then the persisted moves table."""
    st_ = _states[session]
    if st_["results"]:
        return st_["results"]
    try:
        from app.database import db
        rows = db.execute_query(
            "SELECT symbol, reg_close, ah_price, ah_pct, in_portfolio, "
            "in_watchlist FROM afterhours_moves "
            "WHERE session = :ses AND as_of_date = "
            "(SELECT max(as_of_date) FROM afterhours_moves "
            " WHERE session = :ses) ORDER BY ah_pct DESC",
            {"ses": session})
        if rows:
            out_rows = [dict(r) for r in rows]
            for r in out_rows:
                for k in ("reg_close", "ah_price", "ah_pct"):
                    r[k] = float(r[k]) if r[k] is not None else None
            return {
                "as_of": "persisted",
                "session": session,
                "top_gainers": out_rows[:TOP_GAINERS_N],
                "universe_movers": [
                    r for r in out_rows
                    if r["in_portfolio"] or r["in_watchlist"]],
                "scanned": len(out_rows),
            }
    except Exception:
        pass
    return {"session": session, "top_gainers": [], "universe_movers": [],
            "scanned": 0}


def afterhours_results() -> dict[str, Any]:
    return session_results("post")
