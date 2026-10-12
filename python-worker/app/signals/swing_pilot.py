"""Swing pilot — the paper-trading engine that TESTS the flag system.

Separate from flag generation by design: flags describe the tape, the
pilot trades them and keeps score. Its trade journal is the ground
truth that feeds back into the flag engine via `engine_weights` —
the learning loop:

    flags → pilot entry policy → paper trade → exit on plan or
    momentum decay → P&L by pattern → learned weights → flags adjust

Entry policy (v1 — deliberately close to the board's buy side so the
journal grades what the board actually says):
  tape       pullback | recovery entry (basing excluded — a wait-state)
  company    fund_state NOT IN {declining, deteriorating}
  phase gate turning_up → buy; stabilizing → needs prior hit≥0.55;
             still_falling/none → needs PER-SYMBOL prior hit≥0.60
             (the backtest lesson: hypervol names resolve fast)
  vetoes     learned gate weight off · NEGATIVE/HIGH recent alert
  limits     ≤12 open · ≤3 new entries/day

Exit policy — checked daily, first hit wins:
  stop   entry − 1.5×ATR (4-10% band)      → 'stop'
  target entry + 2R                      → 'target'
  decay  state → rolling_over/knife/      → 'momentum_decay'
         breakdown/downtrend
  euphoria state → climax                 → 'climax' (pay yourself)
  time   15 trading days                  → 'timeout'
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

BUY_STATES = {"pullback", "recovery"}
DECAY_STATES = {"rolling_over", "knife", "breakdown", "downtrend"}
FUND_VETO = {"declining", "deteriorating", "pressured"}
MAX_OPEN, MAX_NEW = 12, 3
MAX_HOLD_TD = 15                    # ~3 weeks of trading days


def _bars_yf(syms: list[str], period: str = "3mo"):
    """Canonical bars via daily_bars — no re-download (DRY). 'period'
    maps to stored-bar depth; thin symbols live-top-up in load()."""
    from app.market_data import bars as bars_mod
    days = {"1mo": 30, "3mo": 90, "6mo": 140, "1y": 260,
            "2y": 510}.get(period, 90)
    return bars_mod.load(syms, days=days)


def weight(key: str, default: Any = None) -> Any:
    """Read a learned weight — the flag engine's correction layer."""
    from app.database import db
    rows = db.execute_query(
        "SELECT value FROM engine_weights WHERE key=:k", {"k": key})
    if rows:
        v = rows[0]["value"]
        return (v or {}).get("value", v) if isinstance(v, dict) else v
    return default


def manage_exits(today: date) -> dict[str, Any]:
    """Mark open trades vs today's tape; close on plan or decay."""
    from app.database import db
    open_rows = db.execute_query(
        "SELECT * FROM swing_pilot_trades WHERE status='open'")
    if not open_rows:
        return {"closed": 0}
    states = {r["symbol"]: r for r in db.execute_query(
        "SELECT symbol, momentum_state FROM stocks")}
    books = _bars_yf([r["symbol"] for r in open_rows])
    closed = []
    for t in open_rows:
        sym = t["symbol"]
        bars = books.get(sym) or []
        if not bars:
            continue
        b = bars[-1]
        px, hi, lo = b.close, b.high, b.low
        mfe = max(t["mfe_pct"] or 0, hi / t["entry_px"] - 1)
        mae = min(t["mae_pct"] or 0, lo / t["entry_px"] - 1)
        td = sum(1 for x in bars if x.date > t["entry_date"])
        reason, exit_px = None, None
        st = (states.get(sym) or {}).get("momentum_state")
        if lo <= t["stop_px"]:
            reason, exit_px = "stop", t["stop_px"]
        elif hi >= t["target_px"]:
            reason, exit_px = "target", t["target_px"]
        elif st in DECAY_STATES:
            reason, exit_px = "momentum_decay", px
        elif st == "climax":
            reason, exit_px = "climax", px
        elif td >= MAX_HOLD_TD:
            reason, exit_px = "timeout", px
        if reason:
            ret = exit_px / t["entry_px"] - 1
            db.execute_update(
                "UPDATE swing_pilot_trades SET status='closed',"
                " exit_date=:d, exit_px=:x, exit_reason=:r,"
                " ret_pct=:ret, mfe_pct=:f, mae_pct=:a, hold_days=:h"
                " WHERE id=:i",
                {"d": today, "x": exit_px, "r": reason, "ret": ret,
                 "f": mfe, "a": mae, "h": td, "i": t["id"]})
            closed.append(f"{sym} {reason} {ret * 100:+.1f}%")
        else:
            db.execute_update(
                "UPDATE swing_pilot_trades SET mfe_pct=:f, mae_pct=:a,"
                " hold_days=:h WHERE id=:i",
                {"f": mfe, "a": mae, "h": td, "i": t["id"]})
    return {"closed": len(closed), "detail": closed}


def scan_entries(today: date) -> dict[str, Any]:
    """Generate today's paper entries from the flag stack."""
    from app.database import db
    from app.signals.pattern_priors import prior_for
    n_open = db.execute_query(
        "SELECT count(*) c FROM swing_pilot_trades "
        "WHERE status='open'")[0]["c"]
    room = min(MAX_OPEN - n_open, MAX_NEW)
    if room <= 0:
        return {"opened": 0}
    rows = db.execute_query(
        "SELECT s.symbol, s.momentum_state, s.momentum_detail,"
        " s.fundamental_state"
        " FROM stocks s WHERE s.momentum_state = ANY(:bs)"
        " AND COALESCE(s.fundamental_state,'unknown') != ALL(:fv)"
        " ORDER BY s.symbol",
        {"bs": list(BUY_STATES), "fv": list(FUND_VETO)})
    held = {r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM swing_pilot_trades WHERE status='open'")}
    neg_alerts = {r["symbol"] for r in db.execute_query(
        "SELECT DISTINCT symbol FROM alert_items"
        " WHERE direction='NEGATIVE' AND materiality='HIGH'"
        " AND created_at > now() - interval '5 days'")} \
        if _tbl("alert_items") else set()
    gates = {r["key"]: r["value"] for r in db.execute_query(
        "SELECT key, value FROM engine_weights WHERE key LIKE 'gate:%'")}

    cands = []
    for r in rows:
        sym = r["symbol"]
        if sym in held or sym in neg_alerts:
            continue
        det = r.get("momentum_detail") or {}
        phase = det.get("dip_phase") or "none"
        key = f"{r['momentum_state']}|{phase}"
        g = gates.get(f"gate:{key}")
        if g and g.get("enabled") is False:
            continue                       # learned veto — pilot's
                                         # journal says this gate loses
        prior = prior_for(sym, key)
        ok = (phase == "turning_up"
              or (phase == "stabilizing" and prior
                  and prior["hit_rate_10d"] >= 0.55)
              or (prior and prior["scope"] == "symbol"
                  and prior["hit_rate_10d"] >= 0.60))
        if not ok:
            continue
        atr = det.get("atr_pct") or 0.04
        px = _last_close(sym)
        if not px:
            continue
        stop = px * (1 - min(0.10, max(0.04, 1.5 * atr)))
        tgt = px + 2 * (px - stop)
        cands.append({
            "sym": sym, "px": px, "stop": stop,
            "tgt": min(tgt, px * 1.20), "key": key,
            "ev": {"state": r["momentum_state"], "dip_phase": phase,
                   "dip_health": det.get("dip_health"),
                   "fund": r.get("fundamental_state"),
                   "prior": {k: prior[k] for k in
                             ("n", "hit_rate_10d", "med_ret_10d",
                              "scope")} if prior else None,
                   "atr_pct": atr}})
        # rank: own-history priors first, then turning_up, then score
    cands.sort(key=lambda c: -(
        (c["ev"]["prior"] or {}).get("hit_rate_10d", 0.4) * 100
        + (5 if c["ev"]["dip_phase"] == "turning_up" else 0)))
    opened = []
    for c in cands[:room]:
        import json
        db.execute_update(
            "INSERT INTO swing_pilot_trades"
            " (symbol, entry_date, entry_px, stop_px, target_px,"
            "  pattern_key, evidence, mfe_pct, mae_pct, hold_days)"
            " VALUES (:s,:d,:p,:sp,:tp,:k,CAST(:e AS jsonb),0,0,0)",
            {"s": c["sym"], "d": today, "p": c["px"], "sp": c["stop"],
             "tp": c["tgt"], "k": c["key"],
             "e": json.dumps(c["ev"])})
        opened.append(f"{c['sym']} {c['key']} @ {c['px']:.2f}")
    return {"opened": len(opened), "detail": opened}


def _tbl(name: str) -> bool:
    from app.database import db
    return bool(db.execute_query(
        "SELECT 1 FROM information_schema.tables"
        " WHERE table_name=:t", {"t": name}))


def _last_close(sym: str) -> Optional[float]:
    bars = _bars_yf([sym], "5d").get(sym)
    return bars[-1].close if bars else None


def learn() -> dict[str, Any]:
    """Fold closed-trade P&L back into engine_weights (versioned log).
    This is the feedback into flag generation: gates that lose get
    disabled; phases that win get their penalty softened."""
    from app.database import db
    import json
    written = []

    def put(key: str, value: dict, n: int, win: Optional[float]):
        db.execute_update(
            "INSERT INTO engine_weights (key,value,n,win_rate,"
            " updated_at) VALUES (:k,CAST(:v AS jsonb),:n,:w,now())"
            " ON CONFLICT (key) DO UPDATE SET value=CAST(:v AS jsonb),"
            " n=:n, win_rate=:w, updated_at=now()",
            {"k": key, "v": json.dumps({"value": value}), "n": n,
             "w": win})
        db.execute_update(
            "INSERT INTO engine_weights_log (key,value,n,win_rate)"
            " VALUES (:k,CAST(:v AS jsonb),:n,:w)",
            {"k": key, "v": json.dumps({"value": value}), "n": n,
             "w": win})
        written.append(key)

    # per-pattern gates — a pattern that loses money gets switched off
    for r in db.execute_query(
            "SELECT pattern_key, count(*) n,"
            " avg(CASE WHEN ret_pct>0 THEN 1.0 ELSE 0.0 END) win,"
            " avg(ret_pct) ar FROM swing_pilot_trades"
            " WHERE status='closed' GROUP BY pattern_key"
            " HAVING count(*) >= 4"):
        put(f"gate:{r['pattern_key']}",
            {"enabled": bool(r["win"] >= 0.4 or r["ar"] > 0),
             "avg_ret": round(r["ar"], 4)},
            r["n"], round(r["win"], 3))

    # dip-phase penalty — if still_falling/stabilizing entries that
    # were prior-supported keep winning, soften the -8/-2 defaults;
    # if they keep losing, harden them
    for r in db.execute_query(
            "SELECT evidence->>'dip_phase' ph, count(*) n,"
            " avg(CASE WHEN ret_pct>0 THEN 1.0 ELSE 0.0 END) win,"
            " avg(ret_pct) ar FROM swing_pilot_trades"
            " WHERE status='closed' AND evidence->>'dip_phase'"
            " IS NOT NULL GROUP BY 1 HAVING count(*) >= 4"):
        adj = (-4 if r["win"] >= 0.55 else
               -8 if r["win"] >= 0.4 else -12)
        put(f"dip:{r['ph']}", {"adj": adj, "avg_ret": round(r["ar"], 4)},
            r["n"], round(r["win"], 3))

    # stop effectiveness — do stopped trades whipsaw back? if >40% of
    # stopped trades recovered +10% within 10d, the stop is too tight
    stopped = db.execute_query(
        "SELECT symbol, exit_date, entry_px FROM swing_pilot_trades"
        " WHERE exit_reason='stop'")
    if len(stopped) >= 4:
        syms = list({t["symbol"] for t in stopped})
        books = _bars_yf(syms, "6mo")
        whipsaw = 0
        for t in stopped:
            bars = books.get(t["symbol"]) or []
            after = [b for b in bars if b.date > t["exit_date"]][:10]
            if any(b.close / t["entry_px"] - 1 > 0.10 for b in after):
                whipsaw += 1
        put("risk:stop_mult",
            {"mult": 2.0 if whipsaw / len(stopped) > 0.4 else 1.5,
             "whipsaw_rate": round(whipsaw / len(stopped), 3)},
            len(stopped), None)

    return {"weights_written": len(written), "keys": written}


def run_daily() -> dict[str, Any]:
    """The daily pilot pass — exits first (plan before hope), then new
    entries, then fold the journal back into weights."""
    today = date.today()
    out = {"date": str(today)}
    out["exits"] = manage_exits(today)
    out["entries"] = scan_entries(today)
    out["learn"] = learn()
    return out


def report() -> dict[str, Any]:
    """Page payload — open book, closed journal, stats, learned weights."""
    from app.database import db
    open_t = db.execute_query(
        "SELECT t.*, s.momentum_state FROM swing_pilot_trades t"
        " LEFT JOIN stocks s ON s.symbol=t.symbol"
        " WHERE t.status='open' ORDER BY t.entry_date DESC")
    closed = db.execute_query(
        "SELECT * FROM swing_pilot_trades WHERE status='closed'"
        " ORDER BY exit_date DESC LIMIT 60")
    stats = db.execute_query(
        "SELECT count(*) n,"
        " avg(CASE WHEN ret_pct>0 THEN 1.0 ELSE 0.0 END) win,"
        " sum(ret_pct) total, avg(ret_pct) ar,"
        " avg(hold_days) hd FROM swing_pilot_trades WHERE status='closed'")
    by_pat = db.execute_query(
        "SELECT pattern_key, count(*) n,"
        " avg(CASE WHEN ret_pct>0 THEN 1.0 ELSE 0.0 END) win,"
        " sum(ret_pct) total, avg(ret_pct) ar"
        " FROM swing_pilot_trades WHERE status='closed'"
        " GROUP BY pattern_key ORDER BY sum(ret_pct) DESC")
    by_exit = db.execute_query(
        "SELECT exit_reason, count(*) n, avg(ret_pct) ar"
        " FROM swing_pilot_trades WHERE status='closed'"
        " GROUP BY exit_reason ORDER BY 2 DESC")
    weights = db.execute_query(
        "SELECT key, value, n, win_rate, updated_at"
        " FROM engine_weights ORDER BY key")
    return {"open": open_t, "closed": closed,
            "stats": stats[0] if stats else {},
            "by_pattern": by_pat, "by_exit": by_exit,
            "weights": weights}
