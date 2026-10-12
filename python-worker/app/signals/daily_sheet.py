"""Daily Sheet — the expression layer.

Every engine says WHICH names; this says HOW to act on them tonight:
  STOCK ZONE  — conviction deploy name, entry at the swing-structure
                band (avwap .. swing_low), trigger = confirm_level
  CALL LEAP   — deploy name AND the LEAPS direction engine says CALL
                (washed pullback inside uptrend) → the priced contract
  PUT LEAP    — hedge-journal name in PUT WINDOW (extended + fresh
                stall) AND the direction engine agrees → priced put
  PUT WATCH   — window armed but the direction engine wants the
                stall confirmed → tomorrow's candidate

Journaled nightly and graded like the other engines: did the zone
touch, and what did the underlying do at +5d/+20d vs SPY.
Advisory — the sheet proposes; you decide and place the trade.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

ENGINE_VERSION = "sheet_v1"


def _j(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return {}
    return v or {}


def _candidates() -> dict[str, dict]:
    """Latest conviction deploys + hedge PUT-WINDOW names →
    {symbol: {src, lane, score, future_score, hedge_setup}}."""
    from app.database import db
    out: dict[str, dict] = {}
    conv = db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, snap_date, rank, score,"
        " lane, future_score FROM conviction_snapshots"
        " WHERE snap_date = (SELECT MAX(snap_date) FROM"
        "                      conviction_snapshots)"
        " ORDER BY symbol, snap_date DESC")
    for r in conv:
        if r["lane"] == "deploy" and (r["rank"] or 99) <= 12:
            out[r["symbol"]] = {
                "src": "conviction", "lane": "deploy",
                "score": r["score"], "future_score": r["future_score"]}
        elif r["lane"] == "watch" and (r["future_score"] or 0) >= 50:
            out.setdefault(r["symbol"], {
                "src": "conviction", "lane": "watch",
                "score": r["score"], "future_score": r["future_score"]})
    hedge = db.execute_query(
        "SELECT symbol, setup, score, tier, put FROM"
        " hedge_universe_snapshots WHERE snap_date ="
        " (SELECT MAX(snap_date) FROM hedge_universe_snapshots)")
    for r in hedge:
        if r.get("setup") == "PUT WINDOW":
            cur = out.setdefault(r["symbol"], {"src": ""})
            cur["src"] = (cur["src"] + "+hedge").lstrip("+")
            cur.update({"hedge_setup": "PUT WINDOW",
                        "hedge_score": r["score"],
                        "hedge_tier": r["tier"],
                        "hedge_put": _j(r.get("put"))})
    return out


def _zone(sym: str, tech: dict) -> dict[str, Optional[float]]:
    """Entry zone from persisted swing structure, falling back to the
    LEAPS screen's own technicals (SMA50 band)."""
    from app.database import db
    r = db.execute_query(
        "SELECT momentum_detail FROM stocks WHERE symbol=:s",
        {"s": sym})
    det = _j(r[0]["momentum_detail"]) if r else {}
    sw = det.get("swing") or {}
    atr = (det.get("atr_pct") or 0.02) * (tech.get("price") or 0)
    lo = sw.get("swing_low") or sw.get("support_px")
    hi = sw.get("avwap") or tech.get("sma20") or tech.get("sma50")
    if hi and lo and lo > hi:
        lo, hi = hi, lo
    if lo is None:
        # no pullback structure persisted (climax / mid-range) — the
        # zone is the mean-reversion band around SMA50 (±0.5 ATR),
        # where the next pullback would actually be a buy
        s50 = tech.get("sma50")
        if s50 and atr:
            lo, hi = s50 - 0.5 * atr, s50 + 0.5 * atr
        elif s50:
            lo = hi = s50
    stop_src = sw.get("prior_low") or lo
    return {
        "zone_lo": round(lo, 2) if lo else None,
        "zone_hi": round(hi, 2) if hi else None,
        "trigger": (round(sw["confirm_level"], 2)
                    if sw.get("confirm_level") else None),
        "stop": (round(stop_src - atr, 2)
                 if stop_src and atr else None),
        "dip_phase": det.get("dip_phase"),
    }


def _pick_contract(screen: dict, kind: str) -> tuple[Optional[dict],
                                                   Optional[dict]]:
    """Contract = longest-DTE expiry's named pick. Calls prefer
    safe (deep-ITM stock replacement), alt = flip (the 1-2mo swing
    pick). Puts = top-scored of the same expiry."""
    exps = sorted((screen.get("expiries") or []),
                  key=lambda e: -(e.get("dte") or 0))
    if not exps:
        return None, None
    ex = exps[0]
    if kind == "call":
        return (ex.get("safe_pick_call") or (ex.get("calls") or [None])[0],
                ex.get("flip_pick_call"))
    puts = ex.get("puts") or []
    return (puts[0] if puts else None, None)


def _fv(sym: str, spot: Optional[float]) -> tuple[Optional[float],
                                                 Optional[str]]:
    """(fv_upside_pct, as_of) — the value model's read plus its
    staleness, so a week-old -37% reads differently than fresh."""
    try:
        from app.database import db
        r = db.execute_query(
            "SELECT fair_value, as_of FROM symbol_fair_values"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1",
            {"s": sym})
        if not r or not spot:
            return None, None
        fv, as_of = r[0]["fair_value"], r[0]["as_of"]
        up = (fv - spot) / spot * 100 if fv else None
        return (round(up, 1) if up is not None else None,
                str(as_of)[:10] if as_of else None)
    except Exception:
        return None, None


async def run() -> dict[str, Any]:
    from app.options.leaps import leaps_screen
    today = date.today()
    pool = _candidates()
    rows: list[dict[str, Any]] = []

    for sym, meta in sorted(pool.items()):
        try:
            scr = await leaps_screen(sym)
        except Exception as exc:
            logger.debug("sheet: screen %s failed: %s", sym, exc)
            continue
        verdict, stage = scr.get("verdict"), scr.get("cycle_stage")
        tech = scr.get("technicals") or {}
        spot = scr.get("spot")
        zone = _zone(sym, tech)
        fv_up, fv_as_of = await asyncio.to_thread(_fv, sym, spot)
        lane = meta.get("lane") or "hedge"
        in_window = meta.get("hedge_setup") == "PUT WINDOW"

        section, contract, alt, why = None, None, None, None
        if verdict == "CALL":
            c, alt = _pick_contract(scr, "call")
            if c:
                section, contract = "call_leap", c
                why = ("washed pullback inside uptrend — the "
                       "pull-back-and-rally entry")
            else:
                section, why = "stock_zone", ("CALL verdict but chain "
                                              "empty/dead — express "
                                              "via stock at the zone")
        elif verdict == "PUT":
            p, _ = _pick_contract(scr, "put")
            if in_window and p:
                section, contract = "put_leap", p
                why = ("hedge-journal PUT WINDOW + direction engine "
                       "agrees — extended with a fresh stall")
            elif p:
                section, contract = "put_leap", p
                why = ("direction engine PUT — extended + stalling "
                       "(not in hedge window: check correlation case)")
            else:
                section, why = "put_watch", ("PUT signal but no "
                                             "liquid contract")
        elif verdict == "WAIT" and lane == "deploy":
            section = "stock_zone"
            why = {"wash_not_stabilized":
                   "pullback not finished — zone armed, wait for the "
                   "momentum tick",
                   "falling_knife":
                   "knife zone — armed but do NOT front-run",
                   "extended_no_stall":
                   "extended, no stall yet — euphoria trim zone, not "
                   "an entry"}.get(stage, f"wait ({stage}) — zone armed")
        elif verdict == "WAIT" and in_window:
            section, why = "put_watch", ("in hedge PUT WINDOW; "
                                         "direction engine wants the "
                                         "stall confirmed")
        elif verdict == "SKIP":
            why = None  # disqualified fundamentals — drop entirely

        if not section:
            continue
        # valuation conflict is surfaced, never hidden — the momentum
        # verdict doesn't consult fair value, so a CALL LEAP on a
        # deeply-stretched name gets the flag inline. NB: fv model has
        # known ADR-unit artifacts (TSM fv/5 ≈ spot) → flag, not gate.
        reasons = ([why] if why else [])
        if fv_up is not None and fv_up <= -20:
            reasons.append(
                f"⚠ value model says {fv_up:+.0f}% vs fair "
                f"(as of {fv_as_of or '?'}) — momentum trade, not a "
                "value trade; LEAP amplifies a stretched name — "
                "prefer deep-ITM (intrinsic-heavy), tighter discipline")
        elif fv_up is not None and fv_up >= 15:
            reasons.append(
                f"value model agrees — {fv_up:+.0f}% upside "
                f"(as of {fv_as_of or '?'})")
        reasons += (scr.get("actions") or [])[:2]
        rows.append({
            "symbol": sym, "section": section, "lane": lane,
            "verdict": verdict, "cycle_stage": stage,
            "conv_score": meta.get("score"),
            "future_score": meta.get("future_score"),
            "hedge_score": meta.get("hedge_score"),
            "spot": spot, **zone,
            "contract": contract, "alt": alt,
            "iv_rank": scr.get("iv_rank"),
            "iv_elevated": scr.get("iv_elevated"),
            "fv_upside_pct": fv_up,
            "reasons": reasons,
        })

    _journal(today, rows)
    graded = await asyncio.to_thread(_grade)
    return {"snap_date": str(today), "pool": len(pool),
            "rows": len(rows),
            "by_section": {s: sum(1 for r in rows if r["section"] == s)
                           for s in ("stock_zone", "call_leap",
                                     "put_leap", "put_watch")},
            "graded": graded}


def _journal(today: date, rows: list[dict]) -> None:
    from app.database import db
    db.execute_update(
        "DELETE FROM daily_sheet_snapshots WHERE snap_date=:d",
        {"d": today})
    for r in rows:
        db.execute_update(
            "INSERT INTO daily_sheet_snapshots"
            " (snap_date, symbol, section, lane, verdict, cycle_stage,"
            "  conv_score, future_score, hedge_score, spot, zone_lo,"
            "  zone_hi, trigger_px, stop_px, dip_phase, contract, alt,"
            "  iv_rank, iv_elevated, fv_upside_pct, reasons,"
            "  engine_version)"
            " VALUES (:d, :s, :sec, :lane, :v, :cs, :cv, :fs, :hs, :sp,"
            "  :zl, :zh, :tg, :st, :dp, CAST(:c AS jsonb),"
            "  CAST(:a AS jsonb), :ir, :ie, :fv, CAST(:rs AS jsonb),"
            "  :ev)",
            {"d": today, "s": r["symbol"], "sec": r["section"],
             "lane": r["lane"], "v": r["verdict"],
             "cs": r["cycle_stage"], "cv": r.get("conv_score"),
             "fs": r.get("future_score"),
             "hs": r.get("hedge_score"), "sp": r.get("spot"),
             "zl": r.get("zone_lo"), "zh": r.get("zone_hi"),
             "tg": r.get("trigger"), "st": r.get("stop"),
             "dp": r.get("dip_phase"),
             "c": json.dumps(r.get("contract") or {}),
             "a": json.dumps(r.get("alt") or {}),
             "ir": r.get("iv_rank"),
             "ie": r.get("iv_elevated"),
             "fv": r.get("fv_upside_pct"),
             "rs": json.dumps(r.get("reasons") or []),
             "ev": ENGINE_VERSION})


def _grade() -> int:
    """Fill ret_5d/ret_20d/vs_spy_20d/zone_hit once rows mature —
    from the journaled daily_bars table (same path conviction uses).
    zone_hit = a low inside the armed band within 5 sessions — the
    sheet's honest 'would the zone have filled you' answer."""
    from app.database import db
    rows = db.execute_query(
        "SELECT id, symbol, snap_date, spot, zone_hi FROM"
        " daily_sheet_snapshots WHERE snap_date <= :cutoff"
        " AND ret_5d IS NULL AND spot IS NOT NULL",
        {"cutoff": date.today() - timedelta(days=8)})
    n = 0
    for r in rows:
        try:
            fwd = db.execute_query(
                "SELECT date, close, low FROM daily_bars"
                " WHERE symbol=:s AND date > :d ORDER BY date"
                " LIMIT 20", {"s": r["symbol"], "d": r["snap_date"]})
            if len(fwd) < 5:
                continue
            r5 = fwd[4]["close"] / r["spot"] - 1
            r20 = (fwd[19]["close"] / r["spot"] - 1
                   if len(fwd) >= 20 else None)
            vs = None
            if r20 is not None:
                sf = db.execute_query(
                    "SELECT close FROM daily_bars WHERE symbol='SPY'"
                    " AND date > :d ORDER BY date LIMIT 20",
                    {"d": r["snap_date"]})
                sb = db.execute_query(
                    "SELECT close FROM daily_bars WHERE symbol='SPY'"
                    " AND date <= :d ORDER BY date DESC LIMIT 1",
                    {"d": r["snap_date"]})
                if sb and len(sf) >= 20:
                    vs = r20 - (sf[19]["close"] / sb[0]["close"] - 1)
            zhit = (any(b["low"] <= r["zone_hi"] for b in fwd[:5])
                    if r.get("zone_hi") else None)
            db.execute_update(
                "UPDATE daily_sheet_snapshots SET ret_5d=:r5,"
                " ret_20d=:r20, vs_spy_20d=:vs, zone_hit=:zh"
                " WHERE id=:id",
                {"r5": round(r5, 4),
                 "r20": round(r20, 4) if r20 is not None else None,
                 "vs": round(vs, 4) if vs is not None else None,
                 "zh": zhit, "id": r["id"]})
            n += 1
        except Exception as exc:
            logger.debug("sheet grade %s: %s", r["symbol"], exc)
    return n


def latest() -> dict[str, Any]:
    """Most recent sheet, grouped by section + the env context."""
    from app.database import db
    rows = db.execute_query(
        "SELECT * FROM daily_sheet_snapshots WHERE snap_date ="
        " (SELECT MAX(snap_date) FROM daily_sheet_snapshots)"
        " ORDER BY section, conv_score DESC NULLS LAST")
    for r in rows:
        r["contract"] = _j(r.get("contract"))
        r["alt"] = _j(r.get("alt"))
        r["reasons"] = (json.loads(r["reasons"])
                        if isinstance(r.get("reasons"), str)
                        else (r.get("reasons") or []))
        for k in ("snap_date", "created_at"):
            if r.get(k) is not None:
                r[k] = str(r[k])
    env = {}
    try:
        from app.screener import service
        e, _ = service._current_env()
        env = {"long_permission": e.long_permission,
               "size_multiplier": e.size_multiplier}
    except Exception:
        pass
    return {"snap_date": rows[0]["snap_date"] if rows else None,
            "env": env, "rows": rows}


def performance() -> dict[str, Any]:
    from app.database import db
    by_sec = db.execute_query(
        "SELECT section, COUNT(*) n, AVG(ret_5d) r5, AVG(ret_20d) r20,"
        " AVG(vs_spy_20d) vs, AVG(zone_hit::int) zone_hit_rate"
        " FROM daily_sheet_snapshots WHERE ret_5d IS NOT NULL"
        " GROUP BY section ORDER BY section")
    top = db.execute_query(
        "SELECT symbol, COUNT(*) n, AVG(ret_20d) r20,"
        " AVG(vs_spy_20d) vs FROM daily_sheet_snapshots"
        " WHERE ret_5d IS NOT NULL GROUP BY symbol"
        " ORDER BY AVG(vs_spy_20d) DESC NULLS LAST LIMIT 15")
    for r in by_sec + top:
        for k in ("r5", "r20", "vs", "zone_hit_rate"):
            if r.get(k) is not None:
                r[k] = round(float(r[k]), 4)
    return {"by_section": by_sec, "symbols": top}
