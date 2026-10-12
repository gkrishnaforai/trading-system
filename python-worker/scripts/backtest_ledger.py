"""Ledger backtest: replay the engine day-by-day and book trades into the
`trades` ledger under a separate user_id — so simulated fills and exits
accumulate realized P&L alongside (but separate from) real trades.

Entry : setup qualifies (not no_setup/knife, score >= --min-score,
        env permission != disabled) and no open trade on the symbol.
        Entry at close, stop = 2xATR, T1 = 2R, T2 = 3R,
        shares = --risk-dollars / (entry - stop).
Exits : stop hit -> 'stop' (checked first on ambiguous bars).
        T1 hit   -> sell 1/3 at 't1', raise stop to breakeven.
        T2 hit   -> exit remainder at 't2'.
        >=20 bars held and r < 0.5 -> 'time' at close.
        window end -> 'backtest_end' at last close.

Usage:
    python -m scripts.backtest_ledger NBIS NVDA MRVL AVGO TSLA \
        --start 2026-01-01 --end 2026-08-31 --user-id backtest-2026H1 --reset
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, ".")

from app.market_data import MarketDataService
from app.swing_opportunity.engine import analyze_stock, detect_setup
from app.swing_opportunity.models import SetupType
from app.trades import service as trades
from scripts.backtest_patterns import _neutral_regime, _regime_env

MIN_HISTORY = 200
TIME_STOP_BARS = 20


async def backtest_symbol(symbol: str, start: date, end: date, user_id: str,
                          min_score: float, risk_dollars: float, svc,
                          practice_only: bool = False,
                          skip_killzone: bool = False,
                          no_disabled_stock: bool = False,
                          drop_pullback: bool = False,
                          mr_bounce_exit: bool = False,
                          use_size_mult: bool = False):
    bars = await svc.get_ohlcv(symbol, start=start - timedelta(days=400),
                               end=end, interval="1d")
    spy = await svc.get_ohlcv("SPY", start=start - timedelta(days=400),
                              end=end, interval="1d")
    if len(bars) < MIN_HISTORY + 5:
        print(f"{symbol}: only {len(bars)} bars — skipped")
        return []

    regime = _neutral_regime()
    open_trade = None          # {"id", "stop", "t1", "t2", "entry", "trimmed", "entry_i", "type"}
    last_episode = None
    closed = []

    for i in range(MIN_HISTORY, len(bars)):
        d = bars[i].timestamp.date()
        if d < start:
            continue
        window = bars[:i + 1]
        spy_window = [b for b in spy if b.timestamp <= bars[i].timestamp]
        env = _regime_env(spy_window)
        stock = analyze_stock(symbol, window, spy_window)
        setup = detect_setup(stock, regime, env)

        # --- manage open trade first (exits evaluated on today's bar) ---
        if open_trade:
            b = bars[i]
            held = i - open_trade["entry_i"]
            exit_reason, exit_px = None, None
            is_mr = mr_bounce_exit and open_trade["type"] == "mean_reversion"
            if b.low <= open_trade["stop"]:
                exit_reason, exit_px = "stop", open_trade["stop"]
            elif is_mr:
                # mean-reversion uses its real exit: bounce (close > prior
                # bar high) or ~5 bars max — not the swing 2R/20-bar structure
                if i > 0 and b.close > bars[i - 1].high and held >= 1:
                    exit_reason, exit_px = "bounce", b.close
                elif held >= 5:
                    exit_reason, exit_px = "mr_time", b.close
            elif not open_trade["trimmed"] and b.high >= open_trade["t1"]:
                exit_reason, exit_px = "t1", open_trade["t1"]
            elif b.high >= open_trade["t2"]:
                exit_reason, exit_px = "t2", open_trade["t2"]
            elif held >= TIME_STOP_BARS and \
                    (b.close - open_trade["entry"]) < 0.5 * (open_trade["entry"] - open_trade["orig_stop"]):
                exit_reason, exit_px = "time", b.close

            if exit_reason == "t1":
                qty = open_trade["qty"] / 3
                trades.record_exit(open_trade["id"], exit_px, qty,
                                   reason="t1", exit_date=d.isoformat())
                open_trade["trimmed"] = True
                open_trade["qty"] -= qty
                open_trade["stop"] = open_trade["entry"]  # breakeven after T1
            elif exit_reason:
                trades.record_exit(open_trade["id"], exit_px, open_trade["qty"],
                                   reason=exit_reason, exit_date=d.isoformat())
                r = (exit_px - open_trade["entry"]) / (open_trade["entry"] - open_trade["orig_stop"])
                closed.append({"symbol": symbol, "type": open_trade["type"],
                               "r": r, "reason": exit_reason,
                               "entry_d": open_trade["entry_d"], "exit_d": d.isoformat(),
                               "entry": open_trade["entry"], "exit": exit_px})
                open_trade = None
            if open_trade:
                continue  # one position per symbol — no new entries while open

        # --- entry ---
        if setup.type == SetupType.NO_SETUP or setup.falling_knife:
            last_episode = None
            continue
        if setup.type.value == last_episode:
            continue
        last_episode = setup.type.value
        if env.long_permission == "disabled" or setup.score < min_score:
            continue
        if practice_only and setup.type.value not in {"first_pullback", "mean_reversion"}:
            continue
        if drop_pullback and setup.type.value == "pullback":
            continue
        # kill-zone: stock weak + index weak together — the −0.71R cell
        if skip_killzone and \
                setup.stock_permission in {"limited", "restricted", "disabled"} \
                and env.long_permission in {"limited", "restricted", "disabled"} \
                and setup.type.value != "mean_reversion":
            continue
        # never trend-trade a stock below its own 200-day (MR exempt)
        if no_disabled_stock and \
                setup.stock_permission in {"restricted", "disabled"} \
                and setup.type.value != "mean_reversion":
            continue
        t = stock.technicals
        entry = t.price
        atr = (t.atr_pct or 0.02) * entry
        stop = entry - 2 * atr
        t1 = entry + 2 * (entry - stop)
        t2 = entry + 3 * (entry - stop)
        risk = entry - stop
        mult = env.size_multiplier if use_size_mult else 1.0
        shares = round(risk_dollars * mult / risk, 2) if risk > 0 else 0
        if shares <= 0:
            continue
        res = trades.log_trade({
            "symbol": symbol, "trade_type": "swing",
            "entry_date": d.isoformat(), "entry_price": round(entry, 2),
            "shares": shares, "initial_stop": round(stop, 2),
            "target_1": round(t1, 2), "target_2": round(t2, 2),
            "setup_type": setup.type.value,
            "regime_snapshot": {
                "stock_permission": setup.stock_permission,
                "market_permission": env.long_permission,
                "score": round(setup.score, 1)},
            "user_id": user_id,
        })
        open_trade = {"id": res["id"], "entry": entry, "orig_stop": stop,
                      "stop": stop, "t1": t1, "t2": t2, "qty": shares,
                      "trimmed": False, "entry_i": i, "entry_d": d.isoformat(),
                      "type": setup.type.value}

    # force-close anything still open at window end
    if open_trade:
        last = bars[-1]
        trades.record_exit(open_trade["id"], last.close, open_trade["qty"],
                           reason="backtest_end", exit_date=last.timestamp.date().isoformat())
        r = (last.close - open_trade["entry"]) / (open_trade["entry"] - open_trade["orig_stop"])
        closed.append({"symbol": symbol, "type": open_trade["type"], "r": r,
                       "reason": "backtest_end", "entry_d": open_trade["entry_d"],
                       "exit_d": last.timestamp.date().isoformat(),
                       "entry": open_trade["entry"], "exit": last.close})
    return closed


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--user-id", default="backtest")
    ap.add_argument("--min-score", type=float, default=60)
    ap.add_argument("--risk-dollars", type=float, default=500)
    ap.add_argument("--practice-only", action="store_true",
                    help="enter only first_pullback / mean_reversion setups")
    ap.add_argument("--skip-killzone", action="store_true",
                    help="skip entries when stock weak + index weak together")
    ap.add_argument("--no-disabled-stock", action="store_true",
                    help="skip trend setups when stock_permission restricted/disabled")
    ap.add_argument("--drop-pullback", action="store_true",
                    help="skip generic pullback setups (worst performer)")
    ap.add_argument("--mr-bounce-exit", action="store_true",
                    help="mean_reversion exits on bounce (close>prior high) or 5 bars")
    ap.add_argument("--use-size-mult", action="store_true",
                    help="size positions by env.size_multiplier (limited=0.5x etc.)")
    ap.add_argument("--reset", action="store_true",
                    help="delete existing ledger rows for this user_id first")
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)

    if args.reset:
        n = trades.db.execute_update(
            "DELETE FROM trades WHERE user_id = :u", {"u": args.user_id})
        print(f"reset: deleted {n} ledger rows for user_id={args.user_id}")

    svc = MarketDataService()
    all_closed = []
    for sym in args.symbols:
        closed = await backtest_symbol(sym.upper(), start, end, args.user_id,
                                       args.min_score, args.risk_dollars, svc,
                                       practice_only=args.practice_only,
                                       skip_killzone=args.skip_killzone,
                                       no_disabled_stock=args.no_disabled_stock,
                                       drop_pullback=args.drop_pullback,
                                       mr_bounce_exit=args.mr_bounce_exit,
                                       use_size_mult=args.use_size_mult)
        all_closed.extend(closed)
        by_type = defaultdict(list)
        for c in closed:
            by_type[c["type"]].append(c)
        wins = sum(1 for c in closed if c["r"] > 0)
        tot_r = sum(c["r"] for c in closed)
        print(f"\n=== {sym.upper()} — {len(closed)} trades, "
              f"win {wins}/{len(closed)}, totalR {tot_r:+.2f} ===")
        for stype, rows in sorted(by_type.items()):
            w = sum(1 for c in rows if c["r"] > 0)
            print(f"  {stype:20s} n={len(rows):2d} win={w/len(rows):5.0%} "
                  f"avgR={sum(c['r'] for c in rows)/len(rows):+.2f}")
        for c in closed:
            print(f"    {c['entry_d']}→{c['exit_d']} {c['type']:18s} "
                  f"${c['entry']:.2f}→${c['exit']:.2f} r={c['r']:+.2f} ({c['reason']})")

    if all_closed:
        wins = sum(1 for c in all_closed if c["r"] > 0)
        tot_r = sum(c["r"] for c in all_closed)
        print(f"\n=== COMBINED — {len(all_closed)} trades · win "
              f"{wins/len(all_closed):.0%} · totalR {tot_r:+.2f} ===")
        summ = trades.summary(user_id=args.user_id)
        print(f"ledger ({args.user_id}): realized P&L ${summ['realized_pl']:,.0f} "
              f"· win rate {(summ['win_rate'] or 0)*100:.0f}% "
              f"· {summ['closed_n']} closed")


if __name__ == "__main__":
    asyncio.run(main())
