"""LEAPS position book — the memory layer for sequential convexity.

The signal engine (leaps.py / leaps_backtest._phase) is deliberately
stateless: it answers "which side of convexity NOW". This module owns
everything that needs memory — entry level, the pre-stall 60d high a
put dies on, which ladder tiers already fired, and the post-failure
cooldown that stops bounce-whipsaw re-entries.

Human-in-the-loop: rows are recorded decisions (entered via the
Options page), never auto-executed orders. mark_book() reprices open
positions and evaluates exit rules → `exit_alert` is the actionable
"do something NOW" field the UI banners.

Exit doctrine (validated on the 6-name replay):
  CALL  +50%/+100% unrealized   → take-profit tiers (ladder)
        climax / stall phase    → "sell the calls" — momentum stall at
                                  extension IS the engine's exit
        decisive SMA200 break   → thesis_broken → cut + 20d cooldown
        180d & <+10%            → time_stop
  PUT   spot −15/−25/−35%       → ladder tiers (fire once each)
        S > pre-stall 60d high  → invalidated (the stall failed)
        RSI ≤ 40 / −20%         → capitulation — sell remaining
        90d                     → time_stop — roll or exit
"""
from __future__ import annotations

import logging
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Any, Optional

from app.database import db
from app.options.leaps import _technicals, _macd_hist_prev, RISK_FREE
from app.options.leaps_backtest import _phase, _price

logger = logging.getLogger(__name__)

CALL_TP = [(0.50, "tp50"), (1.00, "tp100")]          # unrealized tiers
PUT_LADDER = [(0.15, "tp15"), (0.25, "tp25"), (0.35, "tp35")]  # spot decline
CALL_TIME_STOP = 180
PUT_TIME_STOP = 90
COOLDOWN_DAYS = 28            # ~20 trading days after a failed thesis


# ---------------------------------------------------------------- book CRUD

def open_position(p: dict) -> dict:
    """Record a position the human decided to take. Required keys:
    symbol, side, expiry, strike. Marks enrich it later."""
    sym = p["symbol"].upper().strip()
    db.execute_update(
        """INSERT INTO leaps_positions
           (stock_symbol, side, expiry, strike, contracts,
            entry_mid, entry_spot, entry_delta, entry_iv, entry_hv,
            capital, thesis_stage, gap_score_at_entry, cyclical,
            entry_hi_60d, entry_lo_60d, notes, meta)
           VALUES (:s, :side, :exp, :k, :n, :mid, :spot, :d, :iv, :hv,
                   :cap, :stage, :gap, :cyc, :hi, :lo, :notes,
                   CAST(:meta AS jsonb))""",
        {"s": sym, "side": p["side"].upper(), "exp": p["expiry"],
         "k": p["strike"], "n": p.get("contracts", 1),
         "mid": p.get("entry_mid"), "spot": p.get("entry_spot"),
         "d": p.get("entry_delta"), "iv": p.get("entry_iv"),
         "hv": p.get("entry_hv"),
         "cap": p.get("capital") or (
             (p.get("entry_mid") or 0) * 100
             * (p.get("contracts") or 1) or None),
         "stage": p.get("thesis_stage"), "gap": p.get("gap_score"),
         "cyc": p.get("cyclical"), "hi": p.get("entry_hi_60d"),
         "lo": p.get("entry_lo_60d"), "notes": p.get("notes"),
         "meta": __import__("json").dumps(p.get("meta") or {})})
    row = db.execute_query(
        "SELECT * FROM leaps_positions WHERE stock_symbol=:s "
        "ORDER BY id DESC LIMIT 1", {"s": sym})
    return row[0] if row else {}


def close_position(pos_id: int, close_mid: Optional[float] = None,
                   reason: str = "manual") -> dict:
    rows = db.execute_query(
        "SELECT * FROM leaps_positions WHERE id=:i", {"i": pos_id})
    if not rows:
        return {"error": "position not found"}
    pos = rows[0]
    if pos["status"] == "CLOSED":
        return {"error": "already closed", "position": pos}
    if close_mid is None:
        close_mid = pos.get("mark_mid")
    realized = None
    if close_mid is not None and pos.get("entry_mid"):
        realized = round((float(close_mid) / float(pos["entry_mid"])
                          - 1) * 100, 1)
    db.execute_update(
        """UPDATE leaps_positions SET status='CLOSED',
           closed_at=now(), close_mid=:m, close_reason=:r,
           realized_pct=:p, updated_at=now() WHERE id=:i""",
        {"m": close_mid, "r": reason, "p": realized, "i": pos_id})
    return {"closed": pos_id, "realized_pct": realized,
            "reason": reason}


# ------------------------------------------------------------- mark & rules

def _chain_mid(sym: str, expiry: date, strike: float,
               call: bool, spot: float | None = None) -> tuple:
    """Live mid for the exact contract + the chain's median near-ATM
    IV — the iv_snapshot print piggybacks on the fetch that's already
    happening. Returns (mid, atm_iv); either may be None."""
    try:
        import yfinance as yf
        chain = yf.Ticker(sym).option_chain(str(expiry))
        df = chain.calls if call else chain.puts
        atm_iv = None
        if spot:
            try:
                import pandas as _pd
                band = df[(df["strike"] > spot * 0.9)
                          & (df["strike"] < spot * 1.1)]
                ivs = _pd.to_numeric(band["impliedVolatility"],
                                     errors="coerce").dropna()
                if len(ivs):
                    atm_iv = float(ivs.median())
            except Exception:
                pass
        hit = df[df["strike"].round(2) == round(float(strike), 2)]
        if hit.empty:
            return None, atm_iv
        b, a = float(hit.iloc[0].get("bid") or 0), \
            float(hit.iloc[0].get("ask") or 0)
        last = float(hit.iloc[0].get("lastPrice") or 0)
        mid = round((b + a) / 2, 3) if b > 0 and a > 0 else \
            (last or None)
        return mid, atm_iv
    except Exception:
        return None, None


def _eval_exits(pos: dict, phase: str, tech: dict, S: float,
                mark: float) -> tuple[Optional[str], list]:
    """(alert, newly_fired_ladder_tiers). Ladder tiers fire once each;
    alerts are overwritten every mark — they're 'act now', not log."""
    pnl = mark / float(pos["entry_mid"]) - 1 \
        if pos.get("entry_mid") and mark else None
    held = (date.today() - pos["entry_date"]).days \
        if pos.get("entry_date") else 0
    fired: list = []
    if pos["side"] == "CALL":
        if pnl is not None:
            for lvl, tag in CALL_TP:
                if pnl >= lvl and tag not in (pos["ladder_fired"] or []):
                    fired.append(tag)
                    return (f"🎯 take profit — contract +{pnl*100:.0f}% "
                            f"(tier {tag}); ladder out 25-50%"), fired
        if phase in ("climax", "stale_stall", "extended_stall",
                     "climax_structural"):
            return ("⚠ momentum stall at extension — the 'sell the "
                    "calls' signal; trim/exit into strength"), fired
        s200 = tech.get("sma200") or S
        if phase == "falling_knife" or S < s200 * 0.97:
            return ("🔴 thesis broken — decisive trend break; cut the "
                    "calls (20d cooldown will follow)"), fired
        if held >= CALL_TIME_STOP and (pnl or 0) < 0.10:
            return ("⏰ 180d time-stop — thesis stalled; recycle "
                    "capital"), fired
        if pnl is not None and pnl <= -0.40:
            return ("🔴 −40% floor — cut; don't martyr to theta"), fired
    else:  # PUT
        spot_down = (float(pos["entry_spot"]) / S - 1) \
            if pos.get("entry_spot") and S else 0
        for lvl, tag in PUT_LADDER:
            if spot_down >= lvl and tag not in (pos["ladder_fired"]
                                                or []):
                fired.append(tag)
                return (f"🎯 put ladder {tag} — stock "
                        f"{spot_down*100:.0f}% below entry; sell 25% "
                        f"of the position"), fired
        if pos.get("entry_hi_60d") and S > float(pos["entry_hi_60d"]):
            return ("🔴 invalidated — new high above the pre-stall "
                    "level; the crack failed, exit"), fired
        if phase == "accumulation" \
                or (tech.get("rsi14") or 50) <= 40 or spot_down >= 0.20:
            return ("🎯 capitulation — harvest remaining puts; "
                    "rotate proceeds into calls if fundamentals "
                    "intact"), fired
        if held >= PUT_TIME_STOP:
            return ("⏰ 90d time-stop — the stall didn't break; "
                    "roll or exit, don't bleed theta"), fired
    return None, fired


def mark_book() -> dict:
    """Reprice all OPEN positions + evaluate exit rules. One batched
    price fetch, per-symbol chains only where a position needs its
    exact contract."""
    open_pos = db.execute_query(
        "SELECT * FROM leaps_positions WHERE status='OPEN' "
        "ORDER BY stock_symbol")
    if not open_pos:
        return {"marked": 0, "alerts": []}
    symbols = sorted({p["stock_symbol"] for p in open_pos})
    bars_by_sym: dict = {}
    try:
        import yfinance as yf
        from types import SimpleNamespace
        px = yf.download(" ".join(symbols), period="2y",
                         interval="1d", group_by="ticker",
                         progress=False, threads=True,
                         auto_adjust=True)
        for s in symbols:
            # group_by="ticker" → MultiIndex (px[s]); a flat frame
            # (single ticker, auto group) needs the bare frame
            try:
                sub = px[s]
            except (KeyError, TypeError):
                sub = px
            df = sub.dropna(subset=["Close"])
            bars_by_sym[s] = [SimpleNamespace(
                timestamp=i.to_pydatetime(), date=i.date(),
                open=float(r.Open), high=float(r.High),
                low=float(r.Low), close=float(r.Close),
                adj_close=None,
                volume=float(r.Volume) if pd.notna(r.Volume) else 0)
                for i, r in df.iterrows()]
    except Exception as e:
        logger.warning("leaps book bar fetch failed: %s", e)

    alerts = []
    iv_written: set = set()
    for pos in open_pos:
        sym = pos["stock_symbol"]
        bars = bars_by_sym.get(sym)
        if not bars:
            continue
        tech = _technicals(bars)
        if not tech:
            continue
        S = tech["price"]
        phase = _phase(tech, _macd_hist_prev(bars),
                       bool(pos.get("cyclical")))
        hv = tech.get("hv60") or tech.get("hv20") or 0.45
        is_call = pos["side"] == "CALL"
        mark, atm_iv = _chain_mid(sym, pos["expiry"],
                                  float(pos["strike"]), is_call, S)
        mark_src = "chain"
        if atm_iv and sym not in iv_written:
            try:                            # daily IV print → IV rank
                db.execute_update(
                    "INSERT INTO iv_snapshots (symbol, as_of, atm_iv,"
                    " hv20, iv_hv) VALUES (:s, CURRENT_DATE, :iv, :hv,"
                    " :r) ON CONFLICT (symbol, as_of) DO UPDATE SET"
                    " atm_iv=EXCLUDED.atm_iv, hv20=EXCLUDED.hv20,"
                    " iv_hv=EXCLUDED.iv_hv",
                    {"s": sym, "iv": round(atm_iv, 5),
                     "hv": round(hv, 5), "r": round(atm_iv / hv, 3)})
                iv_written.add(sym)
            except Exception:
                pass
        if mark is None:
            dte = (pos["expiry"] - date.today()).days
            mark = _price(S, float(pos["strike"]), dte, RISK_FREE, hv,
                          is_call)
            mark_src = "bs_model"
        pnl = round((mark / float(pos["entry_mid"]) - 1) * 100, 1) \
            if pos.get("entry_mid") and mark else None
        alert, fired = _eval_exits(pos, phase, tech, S, mark or 0)
        ladder = sorted(set(pos["ladder_fired"] or []) | set(fired))
        ladder_lit = "ARRAY[" + ",".join(f"'{t}'" for t in ladder) \
            + "]::text[]" if ladder else "'{}'::text[]"
        db.execute_update(
            f"""UPDATE leaps_positions SET mark_mid=:m, mark_spot=:s,
               mark_at=now(), unrealized_pct=:p, exit_alert=:a,
               exit_alert_at=CASE WHEN :a IS NOT NULL THEN now()
                                  ELSE exit_alert_at END,
               ladder_fired = {ladder_lit},
               meta = meta || CAST(:src AS jsonb),
               updated_at=now() WHERE id=:i""",
            {"m": mark, "s": S, "p": pnl, "a": alert, "i": pos["id"],
             "src": __import__("json").dumps(
                 {"mark_src": mark_src, "phase": phase})})
        if alert:
            alerts.append({"symbol": sym, "side": pos["side"],
                           "alert": alert, "pnl_pct": pnl,
                           "phase": phase})
    return {"marked": len(open_pos), "alerts": alerts}


def get_book() -> dict:
    """Open + recent closed positions, cooldown state per symbol
    (the book's memory of failed theses)."""
    open_pos = db.execute_query(
        "SELECT * FROM leaps_positions WHERE status='OPEN' "
        "ORDER BY entry_date DESC")
    closed = db.execute_query(
        "SELECT * FROM leaps_positions WHERE status='CLOSED' "
        "ORDER BY closed_at DESC LIMIT 25")
    # cooldown: last failure per symbol within the window → suppress
    cooldown_rows = db.execute_query(
        """SELECT DISTINCT ON (stock_symbol) stock_symbol, closed_at,
                  close_reason, mark_spot
           FROM leaps_positions
           WHERE status='CLOSED'
             AND close_reason IN ('thesis_broken','invalidated',
                                  'time_stop')
             AND closed_at > now() - interval %s
           ORDER BY stock_symbol, closed_at DESC"""
        % f"'{COOLDOWN_DAYS} days'")
    cooldowns = {r["stock_symbol"]: {
        "until": str(r["closed_at"].date() + timedelta(
            days=COOLDOWN_DAYS)) if r.get("closed_at") else None,
        "reason": r["close_reason"], "fail_spot":
            float(r["mark_spot"]) if r.get("mark_spot") else None}
        for r in cooldown_rows}
    realized = [float(p["realized_pct"]) for p in closed
                if p.get("realized_pct") is not None]
    return {"open": open_pos, "closed": closed,
            "cooldowns": cooldowns,
            "stats": {"open": len(open_pos),
                      "closed": len(closed),
                      "win_rate": round(len([x for x in realized
                                             if x > 0]) / len(realized)
                                        * 100) if realized else None,
                      "avg_realized": round(sum(realized)
                                            / len(realized), 1)
                      if realized else None}}
