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
                            wide adv/dec, which needs a paid feed, timeout=30)

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


def _bond_market_closed(d: date) -> bool:
    """Cash Treasury (SIFMA) closed while NYSE is open — ^TNX just
    flatlines at the prior close so the rates leg reads stale.
    Only two such days a year: Columbus Day (2nd Mon Oct) and
    Veterans Day (Nov 11, or the observed Friday when it lands Sat)."""
    if d.month == 10 and d.weekday() == 0 and 8 <= d.day <= 14:
        return True                      # Columbus Day
    if (d.month, d.day) == (11, 11) or \
            (d.month == 11 and d.day == 10 and d.weekday() == 4):
        return True                      # Veterans Day (+ Fri-observed)
    return False


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
                         progress=False, timeout=30)
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


# ------------------------------ forecast --------------------------------
# Deterministic heuristic estimates — journaled with every eval so
# the learning loop can grade them like the state labels. Same
# convention as fragility's _trigger_probs: priors earn calibration
# from outcomes, never declare it. Direction and tradeability are
# DIFFERENT questions: a clean trend-down can out-trade chop.

def _clampf(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _forecast(qqq_d: dict, spy_d: dict, adv: Optional[float],
              vix_rising: bool, vix_falling: bool, lead: Optional[str],
              macro_press: bool, state: str) -> dict[str, Any]:
    """prob_close_green + day_type + tradeability + permissions from
    the same readings the state machine consumed — no new fetch."""
    chg = qqq_d.get("chg_open") or 0
    crosses = qqq_d.get("vwap_crosses") or 0
    above, held = qqq_d.get("above_vwap"), qqq_d.get("vwap_held")

    # --- prob QQQ closes above prev close proxy -----------------------
    p = 0.50
    p += 0.10 if above else -0.10
    p += 0.05 if held else 0.0
    if adv is not None:
        p += (0.07 if adv >= 60 else 0.03 if adv >= 50 else
              -0.04 if adv < 40 else 0.0)
    p += 0.05 if vix_falling else (-0.05 if vix_rising else 0.0)
    p += 0.03 if lead == "ai_led" else (-0.02 if lead == "defensive_led"
                                        else 0.0)
    p -= 0.04 if macro_press else 0.0
    p += _clampf(chg * 8, -0.08, 0.08)     # mild continuation prior
    p_green = round(_clampf(p, 0.05, 0.95), 2)

    # --- day-type distribution ----------------------------------------
    decisive = abs(chg) > 0.004 or qqq_d.get("above_or") or         qqq_d.get("below_or")
    orderly = crosses <= 3 and (held or not above)
    trend_up = (0.55 if (decisive and above and orderly) else
                0.25 if above else 0.10)
    trend_dn = (0.55 if (decisive and not above and orderly) else
                0.25 if not above else 0.10)
    choppy = min(0.60, 0.15 + max(0, crosses - 2) * 0.07)
    rng = max(0.05, 1.0 - trend_up - trend_dn - choppy)
    tot = trend_up + trend_dn + rng + choppy
    day_type = {"p_trend_up": round(trend_up / tot, 2),
                "p_trend_down": round(trend_dn / tot, 2),
                "p_range": round(rng / tot, 2),
                "p_choppy": round(choppy / tot, 2)}

    # --- tradeability: orderliness, not bullishness --------------------
    t = 50.0
    t += 12 if (qqq_d.get("above_or") or qqq_d.get("below_or")) else -8
    t += 10 if held else 0
    t -= min(24, crosses * 4)
    if adv is not None:
        t += 10 if adv >= 55 else (-10 if adv < 40 else 0)
    t += 8 if vix_falling else (-12 if vix_rising else 0)
    t -= 8 if state in ("narrow_fragile", "chop_unconfirmed") else 0
    trade = round(_clampf(t, 0, 100))
    trade_cls = ("strongly_favorable" if trade >= 80 else
                 "favorable" if trade >= 65 else
                 "mixed" if trade >= 45 else
                 "poor" if trade >= 25 else "dangerous")

    # --- strategy permissions — state × tradeability -------------------
    perm = {
        "long_breakouts": state == "buyers_in_control" and trade >= 45,
        "long_pullbacks": state in ("buyers_in_control",
                                    "sellers_exhausting") and trade >= 40,
        "short_momentum": state == "sellers_regaining" and trade >= 45,
        "mean_reversion": day_type["p_choppy"] >= 0.4 and trade >= 35,
    }
    return {"prob_close_green": p_green, "day_type": day_type,
            "tradeability": trade, "tradeability_cls": trade_cls,
            "strategy_permissions": perm, "basis": "heuristic_v1"}


def premarket() -> dict[str, Any]:
    """Layer-1 forecast — overnight futures + gap vs ATR + prior regime.
    Runs before the open; the RTH evals supersede it as tape arrives."""
    from app.database import db
    out: dict[str, Any] = {"horizon": "premarket",
                           "ts": datetime.now(_ET).isoformat(
                               timespec="seconds")}
    try:
        import yfinance as yf
        for label, tick in (("es", "ES=F"), ("nq", "NQ=F")):
            df = yf.download(tick, period="2d", interval="1h",
                             progress=False, timeout=30)
            if df is not None and not df.empty:
                last = float(df["Close"].iloc[-1])
                ref = float(df["Close"].iloc[-2]) if len(df) > 1 else last
                out[f"{label}_chg_pct"] = round((last / ref - 1) * 100, 2)
        # gap vs ATR — yesterday close vs futures level
        row = db.execute_query(
            "SELECT close, high, low FROM daily_bars WHERE symbol='SPY'"
            " ORDER BY date DESC LIMIT 15")
        if row and out.get("es_chg_pct") is not None:
            atr = sum(float(r["high"]) - float(r["low"])
                      for r in row[:14]) / 14
            gap_pct = out["es_chg_pct"] / 100
            out["gap_vs_atr"] = round(float(row[0]["close"]) * abs(gap_pct)
                                      / atr, 2) if atr else None
        # prior session state as the stale-est prior
        prev = db.execute_query(
            "SELECT state, readings FROM intraday_evals"
            " ORDER BY ts DESC LIMIT 1")
        if prev:
            out["prior_state"] = prev[0].get("state")
        nq = out.get("nq_chg_pct")
        p = 0.50 + _clampf((nq or 0) / 100 * 20, -0.15, 0.15)
        out["prob_close_green"] = round(_clampf(p, 0.15, 0.85), 2)
        out["basis"] = "premarket_heuristic"
    except Exception as e:
        out["error"] = str(e)[:120]
    return out


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
    if smh.get("above_vwap") is not None:
        ev.append(f"SMH {'above' if smh['above_vwap'] else 'below'} "
                  f"VWAP{' held' if smh.get('vwap_held') else ''} — "
                  f"sector reclaim read")

    # macro pressure — yields AND oil rising = headwind on growth.
    # On a bond-market holiday ^TNX is frozen at the prior close —
    # it can't press, and its flatline isn't a real read.
    bond_closed = _bond_market_closed(date.today())
    macro_press = bool(
        not bond_closed and
        tnx.get("chg_open") and tnx["chg_open"] > 0.005 and
        clf.get("chg_open") and clf["chg_open"] > 0.005)
    if tnx.get("chg_open") is not None:
        ev.append(f"TNX {tnx['chg_open'] * 100:+.2f}% · "
                  f"CL {((clf.get('chg_open') or 0) * 100):+.1f}%"
                  + (" — macro pressing growth" if macro_press else "")
                  + (" — cash Treasury closed: rates read stale"
                     if bond_closed else ""))
    elif bond_closed:
        ev.append("TNX — cash Treasury closed (holiday): "
                  "rates read stale")

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
           "bond_closed": bond_closed,
           "smh_above_vwap": smh.get("above_vwap"),
           "smh_vwap_held": smh.get("vwap_held"),
           "breadth_adv_pct": adv, "breadth_n": br.get("n"),
           "evidence": ev}
    # forecast layer — direction vs conditions vs day-type, journaled
    # for the grading loop (heuristic priors, not a fitted model)
    fc = _forecast(q, spy, adv, vix_rising, vix_falling, lead,
                   macro_press, state)
    out["forecast"] = fc
    out["prob_close_green"] = fc["prob_close_green"]
    out["tradeability"] = fc["tradeability"]
    out["tradeability_cls"] = fc["tradeability_cls"]
    out["day_type"] = fc["day_type"]
    out["strategy_permissions"] = fc["strategy_permissions"]
    if persist:
        _persist(out)
    return out


def _persist(o: dict[str, Any]) -> None:
    from app.database import db
    db.execute_update(
        "INSERT INTO intraday_evals (ts, state, readings)"
        " VALUES (:ts, :st, CAST(:r AS jsonb))"
        " ON CONFLICT (ts) DO NOTHING",          # job + lazy-eval same-second race
        {"ts": o["ts"], "st": o["state"],
         "r": json.dumps(o, default=str)})


# ------------------------------ reads -----------------------------------

def _timeline_row(r: dict) -> dict:
    """One journaled eval as a timeline entry — state plus the readings
    that explain WHY the tape looked that way at that moment, so a
    state transition carries its own evidence (VWAP lost, VIX spiked,
    leadership rotated) instead of just a label."""
    rd = r.get("readings") or {}
    if isinstance(rd, str):
        try:
            rd = json.loads(rd)
        except Exception:
            rd = {}
    return {"ts": str(r["ts"]), "state": r["state"],
            "qqq_chg_open": rd.get("qqq_chg_open"),
            "spy_chg_open": rd.get("spy_chg_open"),
            "above_vwap": rd.get("above_vwap"),
            "vwap_held": rd.get("vwap_held"),
            "vix": rd.get("vix"),
            "vix_rising": rd.get("vix_rising"),
            "vix_falling": rd.get("vix_falling"),
            "breadth_adv_pct": rd.get("breadth_adv_pct"),
            "leadership": rd.get("leadership"),
            "macro_pressure": rd.get("macro_pressure"),
            "smh_above_vwap": rd.get("smh_above_vwap"),
            "smh_vwap_held": rd.get("smh_vwap_held"),
            "evidence": rd.get("evidence")}


def base_rates() -> dict[str, dict]:
    """Conditional session outcomes — the journal's own learnings.

    Per-session signature (the day's most-eval'd tape state) vs
    same-day and next-day QQQ returns. Base rates with n disclosed;
    honest context, never a forecast."""
    from app.database import db
    rows = db.execute_query(
        "SELECT ts::date d, state, day_ret FROM intraday_evals"
        " WHERE outcome IS NOT NULL")
    counts: dict = {}
    day_ret: dict = {}
    for r in rows:
        d = r["d"]
        counts.setdefault(d, {})
        counts[d][r["state"]] = counts[d].get(r["state"], 0) + 1
        if d not in day_ret and r.get("day_ret") is not None:
            day_ret[d] = float(r["day_ret"])
    bars = db.execute_query(
        "SELECT date, close FROM daily_bars WHERE symbol='QQQ'"
        " ORDER BY date")
    closes = {b["date"]: float(b["close"]) for b in bars}
    order = sorted(closes)
    ndx = {order[i]: closes[order[i + 1]] / closes[order[i]] - 1
           for i in range(len(order) - 1)}
    groups: dict = {}
    for d, c in counts.items():
        dom = max(c, key=c.get)
        g = groups.setdefault(dom, {"n": 0, "day": [], "next": []})
        g["n"] += 1
        if d in day_ret:
            g["day"].append(day_ret[d])
        if d in ndx:
            g["next"].append(ndx[d])
    import statistics
    out: dict[str, dict] = {}
    for st, g in groups.items():
        if g["n"] < 3:
            continue
        out[st] = {
            "n": g["n"],
            "day_median": (round(statistics.median(g["day"]), 4)
                           if g["day"] else None),
            "day_red_pct": (round(
                sum(1 for x in g["day"] if x < 0) / len(g["day"]), 2)
                if g["day"] else None),
            "next_median": (round(statistics.median(g["next"]), 4)
                            if g["next"] else None),
            "next_red_pct": (round(
                sum(1 for x in g["next"] if x < 0) / len(g["next"]), 2)
                if g["next"] else None),
        }
    return out


def latest() -> dict[str, Any]:
    """Most recent eval + today's state timeline, for the board card."""
    from app.database import db
    rows = db.execute_query(
        "SELECT ts, state, readings FROM intraday_evals"
        " WHERE ts::date = CURRENT_DATE ORDER BY ts DESC")
    if not rows:
        return {"state": "no_evals_today", "timeline": []}
    latest_eval = rows[0]["readings"] or {}
    # sessions-like-this base rate — the journal's own history
    br = None
    try:
        dom_counts: dict = {}
        for r in rows:
            dom_counts[r["state"]] = dom_counts.get(r["state"], 0) + 1
        dom = max(dom_counts, key=dom_counts.get)
        hist = base_rates().get(dom)
        if hist:
            br = {"state": dom, **hist}
    except Exception:
        pass
    return {"state": rows[0]["state"], "ts": str(rows[0]["ts"]),
            "eval": latest_eval, "base_rate": br,
            "timeline": [_timeline_row(r)
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
