"""Intraday tape classifier — is today's move buyers gaining control,
sellers regaining, or unconfirmed chop?

Deliberately separate from posture (daily: how aggressive can we be)
and from every stock score. This answers ONE question at 15-minute
resolution during RTH: what is the session's tape actually doing —
so a same-day entry isn't a buy into a bounce that was already dying.

Readings (all deterministic):
  index vs session VWAP     reclaimed-and-holding / rejected / crossing
  opening range             above OR high / inside / below OR low
  VIX trend                 vs day open and 15 min ago
  leadership                SMH-vs-QQQ-vs-IWM intraday spreads
                            (AI-led rebound vs broad vs defensive)
  macro leg                 ^TNX + CL=F intraday direction — rate/oil
                            pressure on growth
  book breadth              % of tracked names above today's open —
                            via ONE batched yf.download (not market-
                            wide adv/dec, which needs a paid feed)

States (first-match):
  buyers_in_control    above VWAP + breadth healthy + VIX falling
  sellers_regaining    lost VWAP + breadth deteriorating + VIX rising
  narrow_fragile       index green but breadth thin or VIX climbing —
                       mega-cap bounce hiding weakness
  sellers_exhausting   index red but breadth improving, VIX stalled
  chop_unconfirmed     everything else — VWAP crossings, mixed reads

Every eval journals to intraday_evals. The learning loop grades
"did state X at time T actually hold to the close" — the state names
earn trust from outcomes, not from looking plausible.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, time as dtime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.observability.logging import get_logger

logger = get_logger("intraday_pulse")

_ET = ZoneInfo("America/New_York")

# index/vol/macro proxies — every one verified live on the Yahoo path
_INDEX = ["SPY", "QQQ", "SMH", "IWM"]
_VOL = ["^VIX"]
_MACRO = ["^TNX", "CL=F"]

RTH_OPEN = dtime(9, 30)
RTH_LAST_EVAL = dtime(15, 45)          # last eval before the close print


def market_open_now() -> bool:
    now = datetime.now(_ET)
    return now.weekday() < 5 and RTH_OPEN <= now.time() <= RTH_LAST_EVAL


# ------------------------------ bars -----------------------------------

async def _bars(svc, symbol: str) -> list[dict]:
    try:
        raw = await svc.get_ohlcv(symbol, period="1d", interval="5m")
    except Exception as e:                                  # noqa: BLE001
        logger.debug("bars %s: %s", symbol, e)
        return []
    today = date.today()
    out = []
    for b in raw or []:
        ts = b.timestamp
        d = ts.date() if hasattr(ts, "date") else None
        if d == today and b.close is not None:
            out.append({"ts": ts, "o": float(b.open or b.close),
                        "h": float(b.high or b.close),
                        "l": float(b.low or b.close),
                        "c": float(b.close),
                        "v": float(b.volume or 0)})
    return out


def _vwap(bars: list[dict]) -> Optional[float]:
    pv = sum(((b["h"] + b["l"] + b["c"]) / 3) * b["v"] for b in bars)
    tv = sum(b["v"] for b in bars)
    return pv / tv if tv > 0 else None


def _day_stats(bars: list[dict]) -> dict[str, Any]:
    if not bars:
        return {}
    first = bars[0]["o"]
    last = bars[-1]["c"]
    vw = _vwap(bars)
    or_bars = [b for b in bars[:6]]               # first ~30 min
    or_hi = max(b["h"] for b in or_bars)
    or_lo = min(b["l"] for b in or_bars)
    chg_open = last / first - 1 if first else None
    prev_close_proxy = bars[0]["o"]               # day-open reference
    # VWAP relation — reclaim-hold needs the last few bars above, not
    # just the last print
    above = vw is not None and last > vw
    held = (above and len(bars) >= 4
            and all(b["l"] > vw * 0.998 for b in bars[-3:]))
    crosses = 0
    if vw:
        for i in range(1, len(bars)):
            if (bars[i - 1]["c"] - vw) * (bars[i]["c"] - vw) < 0:
                crosses += 1
    # first-30-min direction vs now → the morning-down→green pattern
    early = or_bars[-1]["c"]
    return {"last": last, "vwap": vw, "above_vwap": above,
            "vwap_held": held, "vwap_crosses": crosses,
            "or_hi": or_hi, "or_lo": or_lo,
            "above_or": last > or_hi, "below_or": last < or_lo,
            "chg_open": chg_open,
            "morning_down_now_green": early < prev_close_proxy
            and last > prev_close_proxy,
            "n_bars": len(bars)}


def _trend(bars: list[dict], lookback: int = 3) -> Optional[float]:
    """last vs N bars ago, as a fraction — the 15-min drift."""
    if len(bars) <= lookback:
        return None
    a = bars[-1 - lookback]["c"]
    return bars[-1]["c"] / a - 1 if a else None


# ------------------------------ breadth ---------------------------------

def _book_breadth() -> dict[str, Any]:
    """% of active-tier names above today's open — ONE batched
    download, not market-wide adv/dec (that needs a paid snapshot
    feed)."""
    try:
        import yfinance as yf
        from app.database import db
        from app.signals import symbol_tiers
        syms = [r["symbol"] for r in db.execute_query(
            f"SELECT t.symbol FROM ({symbol_tiers._active_sql()}) t"
            " JOIN stocks s ON s.symbol = t.symbol"
            " ORDER BY s.market_cap DESC NULLS LAST LIMIT 250")]
        if not syms:
            return {"available": False}
        df = yf.download(" ".join(syms), period="1d",
                         group_by="column", threads=True,
                         progress=False)
        if df is None or df.empty:
            return {"available": False}
        # some tickers emit NaN spacer rows — ffill then read the last
        opens = df["Open"].ffill().iloc[-1] if "Open" in df else None
        closes = df["Close"].ffill().iloc[-1] if "Close" in df else None
        if opens is None or closes is None:
            return {"available": False}
        pairs = [(o, c) for o, c in zip(opens, closes)
                 if o == o and c == c and o > 0]
        if len(pairs) < 20:
            return {"available": False}
        adv = sum(1 for o, c in pairs if c > o)
        return {"available": True, "n": len(pairs),
                "adv_pct": round(adv / len(pairs) * 100, 1)}
    except Exception as e:                                  # noqa: BLE001
        logger.debug("book breadth: %s", e)
        return {"available": False}


# ------------------------------ evaluate --------------------------------

def _fetch_all() -> dict[str, list[dict]]:
    from app.market_data import MarketDataService
    svc = MarketDataService()

    async def go():
        out = {}
        for s in _INDEX + _VOL + _MACRO:
            out[s] = await _bars(svc, s)
        return out
    return asyncio.run(go())


def evaluate(persist: bool = True) -> dict[str, Any]:
    from app.database import db
    raw = _fetch_all()
    qqq = _day_stats(raw.get("QQQ") or [])
    spy = _day_stats(raw.get("SPY") or [])
    vix_bars = raw.get("^VIX") or []
    smh, iwm = _day_stats(raw.get("SMH") or []), _day_stats(raw.get("IWM") or [])
    tnx, clf = _day_stats(raw.get("^TNX") or []), _day_stats(raw.get("CL=F") or [])
    if not qqq.get("last"):
        return {"state": "no_data", "evidence": ["no QQQ bars today"]}

    ev: list[str] = []
    # VIX direction — vs open and last ~15 min
    vix_last = vix_bars[-1]["c"] if vix_bars else None
    vix_open = vix_bars[0]["o"] if vix_bars else None
    vix_trend = _trend(vix_bars)
    vix_rising = (vix_trend or 0) > 0.005 or \
        (vix_last and vix_open and vix_last > vix_open * 1.02)
    vix_falling = (vix_trend or 0) < -0.005 or \
        (vix_last and vix_open and vix_last < vix_open * 0.98)

    br = _book_breadth()
    adv = br.get("adv_pct")
    breadth_ok = adv is not None and adv >= 55
    breadth_thin = adv is not None and adv < 40

    # leadership spread — AI-led vs broad vs defensive
    lead = None
    if smh.get("chg_open") is not None and iwm.get("chg_open") is not None:
        spread = smh["chg_open"] - iwm["chg_open"]
        lead = ("ai_led" if spread > 0.004 else
                "broad" if abs(spread) <= 0.004 else "defensive_led")
        ev.append(f"leadership {lead}: SMH {smh['chg_open'] * 100:+.1f}% "
                  f"vs IWM {iwm['chg_open'] * 100:+.1f}% vs open")

    # macro pressure — yields AND oil rising = headwind on growth
    macro_press = bool(
        tnx.get("chg_open") and tnx["chg_open"] > 0.005 and
        clf.get("chg_open") and clf["chg_open"] > 0.005)
    if tnx.get("chg_open") is not None:
        ev.append(f"TNX {tnx['chg_open'] * 100:+.2f}% · "
                  f"CL {((clf.get('chg_open') or 0) * 100):+.1f}%"
                  + (" — macro pressing growth" if macro_press else ""))

    q = qqq
    ev.append(f"QQQ {((q.get('chg_open') or 0) * 100):+.2f}% vs open · "
              f"{'above' if q['above_vwap'] else 'below'} VWAP"
              f"{' held' if q['vwap_held'] else ''}"
              f" · {q['vwap_crosses']} crosses")
    if q.get("above_or"):
        ev.append("above opening range")
    elif q.get("below_or"):
        ev.append("below opening range")
    if q.get("morning_down_now_green"):
        ev.append("morning-down → green recovery pattern")
    if vix_last:
        ev.append(f"VIX {vix_last:.1f} "
                  f"{'rising' if vix_rising else 'falling' if vix_falling else 'flat'}")
    if adv is not None:
        ev.append(f"book breadth {adv:.0f}% of {br['n']} names green vs open")

    # ------------------- state — first match -------------------
    green = (q.get("chg_open") or 0) > 0.002
    red = (q.get("chg_open") or 0) < -0.002
    if q["above_vwap"] and q["vwap_held"] and breadth_ok and vix_falling:
        state = "buyers_in_control"
    elif not q["above_vwap"] and (breadth_thin or vix_rising) and red:
        state = "sellers_regaining"
    elif green and (breadth_thin or (vix_rising and not vix_falling)):
        state = "narrow_fragile"
    elif red and not breadth_thin and not vix_rising and \
            adv is not None and adv >= 45:
        state = "sellers_exhausting"
    else:
        state = "chop_unconfirmed"
    if macro_press and state == "buyers_in_control":
        state = "narrow_fragile"            # rate/oil pressure caps it
        ev.append("macro pressure downgrades the read")

    out = {"ts": datetime.now(_ET).isoformat(timespec="seconds"),
           "state": state, "green": green,
           "qqq_chg_open": round(q.get("chg_open") or 0, 4),
           "spy_chg_open": round(spy.get("chg_open") or 0, 4),
           "above_vwap": q["above_vwap"], "vwap_held": q["vwap_held"],
           "vwap_crosses": q["vwap_crosses"],
           "above_or": q.get("above_or"), "below_or": q.get("below_or"),
           "morning_recovery": q.get("morning_down_now_green"),
           "vix": round(vix_last, 2) if vix_last else None,
           "vix_rising": vix_rising, "vix_falling": vix_falling,
           "leadership": lead, "macro_pressure": macro_press,
           "breadth_adv_pct": adv, "breadth_n": br.get("n"),
           "evidence": ev}
    if persist:
        _persist(out)
    return out


def _persist(o: dict[str, Any]) -> None:
    from app.database import db
    db.execute_update(
        "INSERT INTO intraday_evals (ts, state, readings)"
        " VALUES (:ts, :st, CAST(:r AS jsonb))",
        {"ts": o["ts"], "st": o["state"],
         "r": json.dumps(o, default=str)})


# ------------------------------ reads -----------------------------------

def latest() -> dict[str, Any]:
    """Most recent eval + today's state timeline, for the board card."""
    from app.database import db
    rows = db.execute_query(
        "SELECT ts, state, readings FROM intraday_evals"
        " WHERE ts::date = CURRENT_DATE ORDER BY ts DESC LIMIT 48")
    if not rows:
        return {"state": "no_evals_today", "timeline": []}
    latest_eval = rows[0]["readings"] or {}
    return {"state": rows[0]["state"], "ts": str(rows[0]["ts"]),
            "eval": latest_eval,
            "timeline": [{"ts": str(r["ts"]), "state": r["state"]}
                         for r in reversed(rows)]}


def grade() -> dict[str, int]:
    """Forward-grade journaled evals: did the state at time T match the
    session close? buyers_in_control should see green closes; sellers_*
    should see the bounce fade. Writes outcome into the row."""
    from app.database import db
    rows = db.execute_query(
        "SELECT id, ts, state, readings FROM intraday_evals"
        " WHERE outcome IS NULL AND ts::date < CURRENT_DATE"
        " LIMIT 200")
    graded = 0
    for r in rows:
        d = r["ts"].date() if hasattr(r["ts"], "date") else None
        if not d:
            continue
        bar = db.execute_query(
            "SELECT open, close FROM daily_bars WHERE symbol='QQQ'"
            " AND date=:d", {"d": d})
        if not bar:
            continue
        day_ret = bar[0]["close"] / bar[0]["open"] - 1
        st = r["state"]
        hit = (st == "buyers_in_control" and day_ret > 0) or \
              (st in ("sellers_regaining", "narrow_fragile")
               and day_ret < 0) or \
              (st == "sellers_exhausting" and day_ret > 0)
        db.execute_update(
            "UPDATE intraday_evals SET outcome=:o, day_ret=:dr"
            " WHERE id=:i",
            {"o": "hit" if hit else "miss", "dr": round(day_ret, 4),
             "i": r["id"]})
        graded += 1
    return {"graded": graded}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "grade":
        print(grade())
    else:
        print(json.dumps(evaluate(persist=False), indent=1, default=str))
