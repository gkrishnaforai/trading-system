"""Walk-forward backtest for the swing setup detectors.

Replays daily bars through analyze_stock + detect_setup for each trading day,
records every detected pattern, and measures the forward outcome using the
same stop/target/horizon math as app.pattern_learning.evaluate_outcomes.

Usage:
    python -m scripts.backtest_patterns NVDA AAPL --years 3 --horizon 10
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

sys.path.insert(0, ".")

from app.market_data import MarketDataService
from app.market_regime.models import MarketPermissions, MarketRegime, RegimeLabel
from app.strategy_environment.models import (
    EnvironmentQuality, StrategyEnvironment, StrategyHorizon,
)
from app.swing_opportunity.engine import analyze_stock, detect_setup
from app.swing_opportunity.models import SetupType

MIN_HISTORY = 200


def _neutral_regime() -> MarketRegime:
    return MarketRegime(
        regime=RegimeLabel.BULL_LOW_VOL, direction="bullish", condition="trend",
        confidence=0.8, trend_score=0.5, deterioration_score=0.2,
        market_permissions=MarketPermissions(
            normal_long=True, dip_buying=True,
            breakout_buying="allowed", size_multiplier=1.0),
    )


def _open_environment() -> StrategyEnvironment:
    return StrategyEnvironment(
        horizon=StrategyHorizon.SWING, quality=EnvironmentQuality.MEDIUM,
        score=65, confidence=0.8, long_permission="allowed",
        breakout_permission="allowed", pullback_permission="allowed",
        size_multiplier=1.0, data_sufficient=True,
    )


def _regime_env(spy_bars) -> StrategyEnvironment:
    """Deterministic SPY-based regime proxy for backtesting.

    Faithful to the real 4-level vocabulary
    (allowed | limited | restricted | disabled). The real engine also uses
    breadth/VIX/participation — this proxy sees index trend only.
      disabled   : SPY < SMA200, or < SMA50 with 20d return < -3%
      restricted : SPY < SMA50 and 20d return < 0
      limited    : SPY < SMA50, or ret20 < 0, or 20d drawdown < -5%
      allowed    : otherwise
    """
    from app.market_data import indicators as ind
    bars = list(spy_bars)
    close = ind.closes(bars).iloc[-1] if bars else None
    sma50 = ind.sma(bars, 50)
    sma200 = ind.sma(bars, 200)
    ret20 = ind.returns(bars, 20)
    dd20 = ind.drawdown_from_high(bars, 20)
    if close is None:
        return _open_environment()
    if (sma200 is not None and close < sma200) or (
            sma50 is not None and close < sma50 and (ret20 or 0) < -0.03):
        perm, mult, breakout, pb = "disabled", 0.0, "restricted", "restricted"
    elif sma50 is not None and close < sma50 and (ret20 or 0) < 0:
        perm, mult, breakout, pb = "restricted", 0.25, "restricted", "limited"
    elif (sma50 is not None and close < sma50) or (ret20 or 0) < 0 \
            or (dd20 or 0) < -0.05:
        perm, mult, breakout, pb = "limited", 0.5, "limited", "allowed"
    else:
        perm, mult, breakout, pb = "allowed", 1.0, "allowed", "allowed"
    return StrategyEnvironment(
        horizon=StrategyHorizon.SWING, quality=EnvironmentQuality.MEDIUM,
        score=60, confidence=0.7, long_permission=perm,
        breakout_permission=breakout, pullback_permission=pb,
        size_multiplier=mult, data_sufficient=True,
    )


def _forward_outcome(entry, stop, target, forward, horizon):
    """Same math as pattern_learning.evaluate_outcomes."""
    if not forward or entry is None or stop is None or entry <= stop:
        return None
    risk = entry - stop
    window = forward[:horizon]
    if len(window) < min(horizon, 3):
        return None
    mfe = max((b.high - entry) / entry for b in window)
    mae = min((b.low - entry) / entry for b in window)
    reason, exit_price, held = "horizon_close", window[-1].close, len(window)
    for i, b in enumerate(window):
        if b.low <= stop:
            reason, exit_price, held = "stop", stop, i + 1
            break
        if target and b.high >= target:
            reason, exit_price, held = "target", target, i + 1
            break
    return {"reason": reason, "r": (exit_price - entry) / risk,
            "mfe": mfe, "mae": mae, "held": held}


async def backtest_symbol(symbol: str, years: float, horizon: int,
                          since: Optional[date] = None,
                          regime_gate: bool = False):
    svc = MarketDataService()
    end = date.today()
    # when --since is set, fetch enough history before it for the 200-bar warmup
    start = (since - timedelta(days=400)) if since else end - timedelta(days=int(years * 365))
    bars = await svc.get_ohlcv(symbol, start=start, end=end, interval="1d")
    spy = await svc.get_ohlcv("SPY", start=start, end=end, interval="1d")
    if len(bars) < MIN_HISTORY + horizon + 5:
        print(f"{symbol}: only {len(bars)} bars — skipped")
        return []

    regime = _neutral_regime()
    signals = []
    suppressed = 0
    last_episode_type = None
    for i in range(MIN_HISTORY, len(bars) - horizon):
        window = bars[:i + 1]
        spy_window = [b for b in spy if b.timestamp <= window[-1].timestamp]
        env = _regime_env(spy_window) if regime_gate else _open_environment()
        stock_env = _regime_env(window) if regime_gate else _open_environment()
        stock = analyze_stock(symbol, window, spy_window)
        setup = detect_setup(stock, regime, env)
        if setup.type == SetupType.NO_SETUP or setup.falling_knife:
            last_episode_type = None
            continue
        # dedup: one signal per consecutive episode of the same setup type
        if setup.type.value == last_episode_type:
            continue
        last_episode_type = setup.type.value
        # only 'disabled' suppresses entirely — 'limited'/'restricted' keep
        # the signal (engine: limited = half size, restricted = −15 score)
        if regime_gate and env.long_permission == "disabled":
            suppressed += 1
            continue
        if since and bars[i].timestamp.date() < since:
            continue
        t = stock.technicals
        entry = t.price
        atr = (t.atr_pct or 0.02) * entry
        stop = entry - 2 * atr
        target = entry + 2 * (entry - stop)
        fwd = bars[i + 1: i + 1 + horizon]
        out = _forward_outcome(entry, stop, target, fwd, horizon)
        if not out:
            continue
        signals.append({
            "date": bars[i].timestamp.date().isoformat(),
            "type": setup.type.value,
            "patterns": setup.detected_patterns,
            "score": setup.score,
            "env_permission": env.long_permission,
            "stock_permission": stock_env.long_permission,
            "entry": entry, "stop": stop, "target": target, **out,
        })
    return signals, suppressed


def report(symbol: str, signals: list, horizon: int, suppressed: int = 0):
    by_type = defaultdict(list)
    for s in signals:
        by_type[s["type"]].append(s)
    print(f"\n=== {symbol} — {len(signals)} setup episodes "
          f"({suppressed} suppressed by regime gate), {horizon}-bar horizon ===")
    for stype, rows in sorted(by_type.items()):
        wins = sum(1 for r in rows if r["r"] > 0)
        stops = sum(1 for r in rows if r["reason"] == "stop")
        targets = sum(1 for r in rows if r["reason"] == "target")
        avg_r = sum(r["r"] for r in rows) / len(rows)
        print(f"  {stype:20s} n={len(rows):3d}  win={wins / len(rows):6.1%}  "
              f"avgR={avg_r:+.2f}  target={targets}  stop={stops}  "
              f"mfe_avg={sum(r['mfe'] for r in rows) / len(rows):+.1%}  "
              f"mae_avg={sum(r['mae'] for r in rows) / len(rows):+.1%}")
    by_perm = defaultdict(list)
    for s in signals:
        by_perm[s.get("env_permission", "allowed")].append(s)
    if len(by_perm) > 1:
        print("  -- by SPY regime permission --")
        for perm, rows in sorted(by_perm.items()):
            wins = sum(1 for r in rows if r["r"] > 0)
            avg_r = sum(r["r"] for r in rows) / len(rows)
            print(f"    {perm:12s} n={len(rows):3d}  win={wins / len(rows):6.1%}  avgR={avg_r:+.2f}")
    # the key matrix: stock's own regime vs index regime
    matrix = defaultdict(list)
    for s in signals:
        matrix[(s.get("stock_permission", "?"),
                s.get("env_permission", "?"))].append(s)
    if any(k[0] != k[1] for k in matrix) or len(matrix) > 1:
        print("  -- stock regime vs SPY regime (stock | spy) --")
        for (sp, ip), rows in sorted(matrix.items()):
            wins = sum(1 for r in rows if r["r"] > 0)
            avg_r = sum(r["r"] for r in rows) / len(rows)
            print(f"    {sp:10s} | {ip:10s}  n={len(rows):3d}  "
                  f"win={wins / len(rows):6.1%}  avgR={avg_r:+.2f}")
    return by_type


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--years", type=float, default=3)
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--since", default=None,
                    help="only report signals on/after this date (YYYY-MM-DD)")
    ap.add_argument("--regime-gate", action="store_true",
                    help="apply SPY-based regime proxy (blocked → suppressed)")
    args = ap.parse_args()
    since = date.fromisoformat(args.since) if args.since else None

    totals = defaultdict(list)
    for sym in args.symbols:
        sigs, suppressed = await backtest_symbol(
            sym.upper(), args.years, args.horizon,
            since=since, regime_gate=args.regime_gate)
        for stype, rows in report(sym.upper(), sigs, args.horizon,
                                  suppressed).items():
            totals[stype].extend(rows)
        for s in sigs:
            perm = f" [{s.get('env_permission', '')}]" if args.regime_gate else ""
            print(f"    {s['date']} {s['type']:18s} score={s['score']:.0f} "
                  f"entry=${s['entry']:.2f} r={s['r']:+.2f} "
                  f"({s['reason']}, {s['held']} bars){perm}")

    print(f"\n=== COMBINED across {len(args.symbols)} symbols ===")
    for stype, rows in sorted(totals.items()):
        wins = sum(1 for r in rows if r["r"] > 0)
        avg_r = sum(r["r"] for r in rows) / len(rows)
        print(f"  {stype:20s} n={len(rows):3d}  win={wins / len(rows):6.1%}  avgR={avg_r:+.2f}")


if __name__ == "__main__":
    asyncio.run(main())
