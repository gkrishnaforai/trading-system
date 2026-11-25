"""Market stability engine — are buyers actually returning TODAY?

Separate from liquidity_forward by design: that engine asks whether
financial conditions will be supportive in 4–12 weeks; this asks
whether risk assets are being bought and held intraday, right now.

Reviewer-mandated rules baked in:

  raw over composite   every observation journaled as its own field —
                       minutes-above-VWAP, failed reclaims, breadth
                       progression, stable-session count. The derived
                       stability_label is computed FROM the raws but
                       the raws are what a false-signal audit needs.

  fixed marks          snapshots at named session marks (30m, 60m,
                       midday, close) — a transient VWAP reclaim at
                       10:05 reads differently from holding it to
                       the close; the journal keeps them separate.

  non-override both    a strong stability read must NOT override a
                       severe liquidity/credit warning; a poor 8w
                       outlook must NOT block a tactical recovery
                       entry when the tape and the stock confirm.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time as dtime
from typing import Any, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# AI-leadership basket — the names whose RS tells you whether the
# selloff's leadership is actually coming back (per spec §6)
_AI_LEADERS = ("NVDA", "AMD", "AVGO", "SMH")
_CREDIT_ETFS = ("HYG", "LQD")

# fixed session marks (ET) — the journaled mark column
_MARKS = [(dtime(10, 0), "30m"), (dtime(10, 30), "60m"),
          (dtime(12, 30), "midday"), (dtime(15, 45), "close")]


def _mark(now: datetime) -> str:
    t = now.time()
    name = "open"
    for thr, m in _MARKS:
        if t >= thr:
            name = m
    return name


def _minutes_above(bars: list[dict], vwap: Optional[float]) -> dict:
    """Minutes spent above VWAP + failed-reclaim count — the raw
    persistence reading the spec demands, not just 'above: bool'."""
    if not bars or not vwap:
        return {"minutes_above_vwap": None, "failed_reclaims": None}
    above_min = sum(5 for b in bars if b["c"] > vwap)
    # a failed reclaim: crossed above VWAP then closed back below
    fails, was_above = 0, bars[0]["c"] > vwap
    for b in bars[1:]:
        now_above = b["c"] > vwap
        if now_above and not was_above:
            was_above = True
        elif was_above and not now_above:
            fails += 1
            was_above = False
    return {"minutes_above_vwap": above_min,
            "failed_reclaims": fails}


def _day_structure() -> dict[str, Any]:
    """Higher lows + closing location — multi-day structure, not
    just today's tape. From stored daily bars, journaled raw."""
    try:
        from app.database import db
        rows = db.execute_query(
            "SELECT date, open, high, low, close FROM daily_bars"
            " WHERE symbol='QQQ' ORDER BY date DESC LIMIT 5")
    except Exception as exc:
        logger.debug("stability structure: %s", exc)
        return {}
    if len(rows) < 3:
        return {}
    rows = list(reversed(rows))
    lows = [float(r["low"]) for r in rows]
    today = rows[-1]
    hi, lo, cl = (float(today["high"]), float(today["low"]),
                  float(today["close"]))
    close_loc = (cl - lo) / (hi - lo) if hi > lo else None
    return {
        "higher_low": lows[-1] > lows[-2] if len(lows) >= 2 else None,
        "consecutive_higher_lows":
            sum(1 for a, b in zip(lows, lows[1:]) if b > a),
        "close_location": round(close_loc, 2)
        if close_loc is not None else None,
    }


def _ai_leadership(raw: dict[str, list[dict]]) -> dict[str, Any]:
    """RS of the AI basket vs open — NVDA/AMD/AVGO/SMH. Journaled
    per-name, not just a summary label."""
    out: dict[str, Any] = {"names": {}}
    from app.signals.intraday_pulse import _day_stats
    vals = []
    for s in _AI_LEADERS:
        st = _day_stats(raw.get(s) or [])
        chg = st.get("chg_open")
        if chg is not None:
            out["names"][s] = round(chg * 100, 2)
            vals.append(chg)
    if vals:
        out["mean_chg_open"] = round(sum(vals) / len(vals) * 100, 2)
        out["pct_green"] = round(
            sum(1 for v in vals if v > 0) / len(vals) * 100, 0)
    return out


def _stable_sessions() -> dict[str, Any]:
    """Consecutive sessions whose EOD stability read was 'stable' —
    persistence ACROSS days, the reviewer's session-persistence leg."""
    try:
        from app.database import db
        rows = db.execute_query(
            "SELECT DISTINCT ON (session_date) session_date, readings"
            " FROM market_stability_snapshots"
            " WHERE session_date < CURRENT_DATE"
            " ORDER BY session_date DESC, ts DESC LIMIT 5")
    except Exception as exc:
        logger.debug("stability sessions: %s", exc)
        return {"stable_sessions": None}
    n = 0
    for r in rows:
        rd = r.get("readings") or {}
        if isinstance(rd, str):
            try:
                rd = json.loads(rd)
            except Exception:
                rd = {}
        if rd.get("stability_label") in ("stable", "stabilizing"):
            n += 1
        else:
            break
    return {"stable_sessions": n}


def _fetch_extended() -> dict[str, list[dict]]:
    """intraday_pulse's symbol set + AI leaders + credit ETFs —
    one batched fetch, same service."""
    import asyncio
    from app.signals import intraday_pulse as ip
    syms = (ip._INDEX + ip._VOL + ip._MACRO
            + [s for s in _AI_LEADERS if s not in ip._INDEX]
            + list(_CREDIT_ETFS))
    from app.market_data import MarketDataService
    svc = MarketDataService()

    async def go():
        return {s: await ip._bars(svc, s) for s in syms}
    return asyncio.run(go())


def evaluate() -> dict[str, Any]:
    """One intraday stability read — raws first, label derived."""
    from app.signals import intraday_pulse as ip
    raw = _fetch_extended()
    qqq = ip._day_stats(raw.get("QQQ") or [])
    smh = ip._day_stats(raw.get("SMH") or [])
    vix_bars = raw.get("^VIX") or []
    if not qqq.get("last"):
        return {"state": "no_data", "mark": _mark(datetime.now(_ET))}

    br = ip._book_breadth()
    vix_last = vix_bars[-1]["c"] if vix_bars else None
    vix_open = vix_bars[0]["o"] if vix_bars else None
    vix_tr = ip._trend(vix_bars)

    # credit confirmation — HYG/LQD intraday tone, not a FRED lag
    credit = {}
    for s in _CREDIT_ETFS:
        st = ip._day_stats(raw.get(s) or [])
        if st.get("chg_open") is not None:
            credit[s] = round(st["chg_open"] * 100, 2)

    q_persist = _minutes_above(raw.get("QQQ") or [], qqq.get("vwap"))
    s_persist = _minutes_above(raw.get("SMH") or [], smh.get("vwap"))
    ai = _ai_leadership(raw)
    struct = _day_structure()
    sess = _stable_sessions()

    readings: dict[str, Any] = {
        "ts": datetime.now(_ET).isoformat(timespec="seconds"),
        "mark": _mark(datetime.now(_ET)),
        # QQQ VWAP persistence — minutes + failed reclaims, raw
        "qqq_last": qqq.get("last"),
        "qqq_vwap": qqq.get("vwap"),
        "qqq_above_vwap": qqq.get("above_vwap"),
        "qqq_vwap_held": qqq.get("vwap_held"),
        "qqq_minutes_above_vwap": q_persist["minutes_above_vwap"],
        "qqq_failed_reclaims": q_persist["failed_reclaims"],
        "qqq_chg_open_pct": (round(qqq["chg_open"] * 100, 2)
                             if qqq.get("chg_open") is not None
                             else None),
        # SMH — the sector whose reclaim matters most for this book
        "smh_above_vwap": smh.get("above_vwap"),
        "smh_minutes_above_vwap": s_persist["minutes_above_vwap"],
        "smh_failed_reclaims": s_persist["failed_reclaims"],
        "smh_chg_open_pct": (round(smh["chg_open"] * 100, 2)
                             if smh.get("chg_open") is not None
                             else None),
        # VIX — level, direction, intraday trend (raw three values)
        "vix": round(vix_last, 1) if vix_last else None,
        "vix_chg_open_pct": (
            round((vix_last / vix_open - 1) * 100, 1)
            if vix_last and vix_open else None),
        "vix_intraday_trend_pct": (
            round(vix_tr * 100, 2) if vix_tr is not None else None),
        # breadth — % of book advancing vs open
        "breadth_adv_pct": br.get("adv_pct"),
        "breadth_n": br.get("n"),
        # AI leadership — per-name RS + basket summary
        "ai_leadership": ai,
        # credit confirmation — ETF intraday tone
        "credit_etfs_chg_open_pct": credit or None,
        # daily structure — higher lows, close location
        **struct,
        # session persistence — consecutive stable days
        **sess,
    }

    # ---- derived label — computed FROM the raws, journaled with them
    met = []
    if q_persist.get("minutes_above_vwap") is not None:
        met.append(("qqq_vwap_persistence",
                    q_persist["minutes_above_vwap"] >= 60))
    if readings.get("vix_chg_open_pct") is not None:
        met.append(("vix_falling", readings["vix_chg_open_pct"] < -2))
    if readings.get("breadth_adv_pct") is not None:
        met.append(("breadth", readings["breadth_adv_pct"] >= 55))
    if ai.get("pct_green") is not None:
        met.append(("ai_leadership", ai["pct_green"] >= 60))
    if struct.get("close_location") is not None:
        met.append(("close_location", struct["close_location"] >= 0.6))
    readings["stability_checks"] = met
    n_met = sum(1 for _, m in met if m)
    readings["checks_met"] = n_met
    readings["stability_label"] = (
        "stable" if n_met >= 4 else
        "stabilizing" if n_met >= 3 else
        "unstable" if n_met <= 1 else "mixed")
    # recovery_status — multi-session view, conservative
    if sess.get("stable_sessions") is not None:
        readings["recovery_status"] = (
            "confirmed" if sess["stable_sessions"] >= 3
            and readings["stability_label"] in ("stable",
                                                "stabilizing") else
            "attempt" if readings["stability_label"] in
            ("stable", "stabilizing") else
            "insufficient_evidence")
    else:
        readings["recovery_status"] = "insufficient_evidence"
    return readings


def _candidate_bars(syms: list[str]) -> dict[str, list[dict]]:
    """5m bars for the selloff candidates — same service as
    _fetch_extended, fetched only when the journal says these names
    are today's dislocations."""
    import asyncio
    from app.signals import intraday_pulse as ip
    from app.market_data import MarketDataService
    svc = MarketDataService()

    async def go():
        return {s: await ip._bars(svc, s) for s in syms}
    try:
        return asyncio.run(go())
    except Exception as exc:
        logger.debug("stability cand bars: %s", exc)
        return {}


def run() -> dict[str, Any]:
    """Compute + journal at the current session mark. ON CONFLICT on
    (session_date, mark) keeps the LATEST snapshot per mark — a 10:35
    run updates the 30m mark, a second 30m run replaces it."""
    from app.database import db
    r = evaluate()
    if r.get("state") == "no_data":
        return r
    # session entries — score the journaled selloff candidates
    # against today's tape: who is ACCUMULATING vs just bouncing.
    # The SBD journal supplies the fundamental leg; this adds the
    # per-stock tape the candidates page can't see.
    try:
        cands = db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, fund, decision,"
            " classification FROM selloff_candidates"
            " ORDER BY symbol, as_of DESC LIMIT 30")
        top = [c for c in cands
               if c.get("decision") not in ("reject",)]
        top = top[:12]                     # fetch budget bound
        if top:
            # selloff journal → the fields stock_accumulation needs
            for c in top:
                f = c.get("fund") or {}
                if isinstance(f, str):
                    f = json.loads(f)
                c["sbd"] = f.get("sbd")
                c["dimensions"] = f.get("dimensions")
                c["business_bucket"] = f.get("business_bucket")
            raw = _fetch_extended()
            raw.update(_candidate_bars(
                [c["symbol"] for c in top
                 if c["symbol"] not in raw]))
            from app.signals import session_entry as se
            r["session_entries"] = se.evaluate_candidates(
                top, raw, r)
    except Exception as exc:
        logger.debug("stability session entries: %s", exc)
    try:
        db.execute_update(
            "INSERT INTO market_stability_snapshots"
            " (session_date, mark, ts, readings)"
            " VALUES (:d, :m, now(), CAST(:r AS jsonb))"
            " ON CONFLICT (session_date, mark) DO UPDATE SET"
            " ts=EXCLUDED.ts, readings=EXCLUDED.readings",
            {"d": date.today(), "m": r["mark"],
             "r": json.dumps(r, default=str)})
    except Exception as exc:
        logger.warning("stability journal: %s", exc)
        r["journal_error"] = str(exc)[:120]
    return r


def read() -> Optional[dict[str, Any]]:
    """Latest journaled stability state — the card + synthesis read."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT session_date, mark, readings"
            " FROM market_stability_snapshots"
            " ORDER BY ts DESC LIMIT 1")
        if not rows:
            return None
        rd = rows[0].get("readings") or {}
        if isinstance(rd, str):
            rd = json.loads(rd)
        rd["session_date"] = str(rows[0]["session_date"])
        rd["journaled_mark"] = rows[0]["mark"]
        return rd
    except Exception:
        return None
