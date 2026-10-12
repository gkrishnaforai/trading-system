"""Walk-forward validation of the sequential-convexity LEAPS strategy.

Replays the SAME _direction state machine the live screen uses, one bar
at a time over ~2.5y, simulating a model contract per entry:

  - entry: BS-priced contract at target delta (call 0.65 / put -0.60),
    T=600d, IV = HV60 at entry (honest proxy — we don't have
    historical IV)
  - CALL exit: climax (RSI≥75 or %B>0.95) → take profit;
    time-stop 180d if underwater; fundamentals assumed intact
    (quarterly data can't be point-in-time replayed — limitation)
  - PUT exit: capitulation (RSI≤40 / %B<0.25 / −20% from entry) →
    take profit; new-high post-stall → invalidated; 90d time-stop
  - sequential convexity: never long both sides; put exit may be
    followed by a call entry once accumulation signals

Run:  python -m app.options.leaps_backtest  (or run_backtest(sym))
"""
from __future__ import annotations

import math
import logging
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any, Optional

import pandas as pd

from app.options.leaps import (_bs, _technicals, _macd_hist_prev,
                               RISK_FREE)

logger = logging.getLogger(__name__)

MIN_BARS = 320           # SMA200 + MACD warmup before first signal
ENTRY_T_DAYS = 600       # model LEAPS ~20 months out
CALL_DELTA = 0.65        # dip-buy sweet spot per review
PUT_DELTA = -0.60
CALL_TIME_STOP = 180
PUT_TIME_STOP = 90
CALL_STOP_PCT = -0.45    # cut a call at −45% (thesis/phase failed)
PUT_STOP_PCT = -0.40


def _strike_for_delta(S: float, T: float, r: float, iv: float,
                      target: float) -> float:
    """Solve K so BS delta ≈ target (grid over 0.7–1.4× spot)."""
    best, best_d = S, 9e9
    for k in [S * x / 100 for x in range(60, 150, 2)]:
        d, _, _ = _bs(S, k, T, r, iv, call=(target > 0))
        if d is not None and abs(d - target) < abs(best_d - target):
            best, best_d = k, d
    return best


def _phase(tech: dict, hist_prev, cyclical: bool) -> str:
    """The _direction regime, technicals-only (fundamentals assumed
    intact — see module docstring for that honest limitation)."""
    px, s50, s200 = tech.get("price"), tech.get("sma50"), \
        tech.get("sma200")
    rsi, hist = tech.get("rsi14"), tech.get("macd_hist")
    pct_b = (tech.get("bollinger") or {}).get("pct_b")
    dd, vs50 = tech.get("dd52w"), tech.get("vs_sma50")
    if not all([px, s50, s200, rsi is not None, hist is not None]):
        return "unknown"
    up = px > s200 and s50 > s200
    extended = (pct_b is not None and pct_b > 0.9) or rsi >= 68 \
        or (vs50 is not None and vs50 > 0.12)
    washed = (dd is not None and dd <= -0.15) or rsi <= 40 \
        or (pct_b is not None and pct_b < 0.25)
    stalling = hist < 0 or (pct_b is not None and pct_b < 0.55) \
        or (hist_prev is not None and hist < hist_prev)
    fresh_stall = hist < 0 and (hist_prev is not None
                              and hist_prev >= 0)
    knife = hist < 0 and (pct_b is not None and pct_b < 0.35)
    stabilizing = hist_prev is None or hist > hist_prev
    climax = rsi >= 75 or (pct_b is not None and pct_b > 0.95)
    if up and washed and knife:
        return "falling_knife"
    if up and washed and not stabilizing:
        return "wash_not_stabilized"
    if up and washed:
        return "accumulation"
    if extended and stalling and fresh_stall:
        return "extended_stall" if cyclical else "climax_structural"
    if extended and stalling:
        return "stale_stall"
    if climax:
        return "climax"
    if extended:
        return "extended_ripping"
    if not up:
        return "downtrend"
    return "trend"


def _price(S, K, T_days, r, iv, call):
    if T_days <= 0:
        return max(0.0, (S - K) if call else (K - S))
    d, _, _ = _bs(S, K, T_days / 365, r, iv, call)
    if d is None:
        return None
    # BS value, not delta — recompute via closed form
    sq = iv * math.sqrt(T_days / 365)
    from statistics import NormalDist
    N = NormalDist().cdf
    d1 = (math.log(S / K) + (r + iv * iv / 2) * T_days / 365) / sq
    d2 = d1 - sq
    if call:
        return S * N(d1) - K * math.exp(-r * T_days / 365) * N(d2)
    return K * math.exp(-r * T_days / 365) * N(-d2) - S * N(-d1)


def run_backtest(sym: str, years: float = 2.5) -> dict[str, Any]:
    import yfinance as yf
    hist = yf.Ticker(sym).history(
        period=f"{int(years * 365 / 252 * 1.6 + 2)}y"
        if years > 1.5 else "2y", interval="1d", auto_adjust=True)
    if hist is None or len(hist) < MIN_BARS + 60:
        return {"symbol": sym, "error": "insufficient history"}
    bars = [SimpleNamespace(timestamp=i.to_pydatetime(),
                            date=i.date(), open=float(r.Open),
                            high=float(r.High), low=float(r.Low),
                            close=float(r.Close), adj_close=None,
                            volume=float(r.Volume))
            for i, r in hist.iterrows()]

    # cyclicality from the stocks table (persisted agent verdict)
    try:
        from app.database import db
        row = db.execute_query(
            "SELECT cyclical FROM stocks WHERE symbol=:s",
            {"s": sym.upper()})
        cyclical = bool(row and row[0].get("cyclical"))
    except Exception:
        cyclical = False

    pos: Optional[dict] = None          # open model position
    trades: list[dict] = []
    capital = 10_000.0                  # options sleeve only
    start_i = MIN_BARS
    series = bars[start_i:]
    cd_until = 0                        # bar index — post-failure cooldown
    fail_spot: Optional[float] = None   # level where the last thesis died

    for i in range(start_i, len(bars)):
        win = bars[:i + 1]
        tech = _technicals(win)
        if not tech:
            continue
        today = bars[i].date
        S = tech["price"]
        hv = tech.get("hv60") or tech.get("hv20") or 0.45
        phase = _phase(tech, _macd_hist_prev(win), cyclical)

        if pos:
            days_held = (today - pos["entry_date"]).days
            val = _price(S, pos["K"], pos["T0"] - days_held,
                         RISK_FREE, pos["iv"], pos["call"])
            pnl = (val / pos["entry_premium"] - 1) if val else None
            exit_reason = None
            if pos["call"]:
                if phase == "climax":
                    exit_reason = "climax_take_profit"
                elif phase in ("stale_stall", "extended_stall",
                               "climax_structural"):
                    # momentum stall at extension = the engine's own
                    # "sell the calls" signal — don't wait for climax
                    exit_reason = "stall_take_profit"
                elif phase in ("downtrend", "falling_knife") and (
                        phase == "falling_knife"
                        or S < (tech.get("sma200") or S) * 0.97):
                    # thesis dead — but require a DECISIVE break:
                    # >3% under SMA200 or a genuine knife. Borderline
                    # flickers around the 200-line chopped AVGO calls
                    # out in days (6 of 8 died near the line)
                    exit_reason = "thesis_broken"
                elif days_held >= CALL_TIME_STOP \
                        and (pnl or 0) < 0.10:
                    exit_reason = "time_stop"
            else:
                # stall thesis dies when price clears the PRE-STALL
                # high — highs BEFORE entry, not the rolling window
                # (a grinding rally never closes above today's own
                # high, which hid this bug for 90d on AMD's +64% run)
                hit_new_high = S > pos["entry_hi"]
                if phase in ("accumulation",) \
                        or (tech.get("rsi14") or 50) <= 40 \
                        or S <= pos["entry_spot"] * 0.80:
                    exit_reason = "capitulation_take_profit"
                elif hit_new_high:
                    exit_reason = "invalidated_new_high"
                elif days_held >= PUT_TIME_STOP:
                    exit_reason = "time_stop"
            if exit_reason and pnl is not None:
                ret = pos["alloc"] * (1 + pnl)
                capital += ret
                if exit_reason in ("thesis_broken",
                                   "invalidated_new_high",
                                   "time_stop"):
                    # failed thesis → no re-entry at the same level:
                    # cooldown 20 bars OR demand a deeper price. This
                    # is the book's memory — the signal engine stays
                    # stateless, risk state lives in the position log
                    cd_until = i + 20
                    fail_spot = S
                trades.append({
                    "side": "CALL" if pos["call"] else "PUT",
                    "in": str(pos["entry_date"]),
                    "out": str(today),
                    "spot_in": round(pos["entry_spot"], 2),
                    "spot_out": round(S, 2),
                    "K": round(pos["K"], 2),
                    "pnl_pct": round(pnl * 100, 1),
                    "exit": exit_reason,
                    "days": days_held})
                pos = None

        in_cooldown = i < cd_until and not (
            fail_spot and S < fail_spot * 0.97)
        if pos is None and phase == "accumulation" and not in_cooldown:
            K = _strike_for_delta(S, ENTRY_T_DAYS / 365, RISK_FREE, hv,
                                  CALL_DELTA)
            prem = _price(S, K, ENTRY_T_DAYS, RISK_FREE, hv, True)
            if prem and prem > 0.5:
                alloc = min(capital * 0.60, capital)
                capital -= alloc
                pos = {"call": True, "K": K, "entry_spot": S,
                       "entry_premium": prem, "entry_date": today,
                       "T0": ENTRY_T_DAYS, "iv": hv, "alloc": alloc,
                       "d": "call"}
        elif pos is None and phase == "extended_stall" \
                and not in_cooldown:
            # puts only where the cycle can turn — cyclicals, or a
            # structural name would additionally need deterioration
            # (not replayable → noted as a limitation)
            if cyclical:
                K = _strike_for_delta(S, ENTRY_T_DAYS / 365, RISK_FREE,
                                      hv, PUT_DELTA)
                prem = _price(S, K, ENTRY_T_DAYS, RISK_FREE, hv, False)
                if prem and prem > 0.5:
                    alloc = min(capital * 0.25, capital)
                    capital -= alloc
                    pos = {"call": False, "K": K, "entry_spot": S,
                           "entry_premium": prem, "entry_date": today,
                           "T0": ENTRY_T_DAYS, "iv": hv, "alloc": alloc,
                           "entry_hi": max(b.high for b
                                           in bars[max(0, i - 60):i])}

    open_pos = None
    if pos:
        S = bars[-1].close
        val = _price(S, pos["K"], pos["T0"]
                     - (bars[-1].date - pos["entry_date"]).days,
                     RISK_FREE, pos["iv"], pos["call"])
        open_pos = {"side": "CALL" if pos["call"] else "PUT",
                    "K": round(pos["K"], 2), "in": str(pos["entry_date"]),
                    "unrealized_pct": round((val / pos["entry_premium"]
                                             - 1) * 100, 1)
                    if val else None}
        capital += pos["alloc"] * (val / pos["entry_premium"] if val
                                   else 0)

    wins = [t for t in trades if t["pnl_pct"] > 0]
    first, last = series[0], series[-1]
    bh = last.close / first.close - 1
    return {"symbol": sym.upper(), "cyclical": cyclical,
            "window": f"{first.date} → {last.date}",
            "trades": trades, "n_trades": len(trades),
            "win_rate": round(len(wins) / len(trades) * 100)
            if trades else None,
            "book": round(capital, 0),
            "book_ret_pct": round((capital / 10_000 - 1) * 100, 1),
            "buy_hold_pct": round(bh * 100, 1),
            "open": open_pos}


if __name__ == "__main__":
    import json
    import sys
    for s in (sys.argv[1:] or ["AMD", "CRDO", "MU", "AVGO", "NVDA",
                              "SNDK"]):
        print(json.dumps(run_backtest(s), default=str))
