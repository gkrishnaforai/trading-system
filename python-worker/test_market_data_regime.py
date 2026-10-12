"""
End-to-end test: MarketDataService -> SPY bars -> market regime.

Validates that the new market-data layer returns everything a regime
classifier needs: enough bars, canonical fields, adjustment data,
quality report, and provider provenance.

Run:  ./venv/bin/python test_market_data_regime.py
"""
import asyncio
import math
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from app.market_data import MarketDataService, validate_bars
from app.market_data.validation import DataQualityReport

SYMBOL = "SPY"
PERIOD = "1y"
MIN_BARS = 200


def sma(values, window):
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def realized_vol(closes, window=20):
    """Annualized vol of log returns over the last `window` sessions."""
    if len(closes) < window + 1:
        return None
    rets = [
        math.log(closes[i] / closes[i - 1])
        for i in range(len(closes) - window, len(closes))
        if closes[i - 1] > 0
    ]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(252)


def classify_regime(close, sma50, sma200, vol20, dd_from_high):
    """Simple regime: trend x volatility x drawdown."""
    if close is None or sma200 is None:
        return "unknown"
    if close > sma200 and (sma50 or 0) > sma200:
        trend = "bull"
    elif close > sma200:
        trend = "bull_correcting"
    elif dd_from_high <= -0.20:
        trend = "bear"
    else:
        trend = "correction"
    if vol20 is not None and vol20 > 0.30:
        return f"{trend}_high_vol"
    return f"{trend}_low_vol"


async def main():
    svc = MarketDataService()
    print(f"providers: {svc.providers}")
    print(f"ohlcv chain: {svc.chain_for('ohlcv')}")

    md = await svc.get_market_data(
        SYMBOL, period=PERIOD, min_bars=MIN_BARS, validate=True
    )
    assert md is not None, "get_market_data returned None"

    failures = []

    def check(name, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] {name}{(' — ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    print(f"\n=== payload checks ({SYMBOL}, {PERIOD}) ===")
    check("bars returned", len(md.bars) >= MIN_BARS, f"{len(md.bars)} bars")
    check("provider recorded", md.provider in ("fmp", "yahoo_finance", "massive"), md.provider)
    check("symbol echoed", md.symbol == SYMBOL)
    check("quality report present", isinstance(md.quality, dict))
    if md.quality:
        rep = DataQualityReport.model_validate(md.quality)
        check("quality ok (no error-severity issues)", rep.ok,
              "; ".join(i.message for i in rep.errors) or "clean")
        if rep.warnings:
            for w in rep.warnings:
                print(f"       warning: [{w.code}] {w.message}")

    b0, bN = md.bars[0], md.bars[-1]
    check("bars sorted", all(
        a.timestamp < b.timestamp for a, b in zip(md.bars, md.bars[1:])
    ))
    check("timestamps tz-aware UTC", bN.timestamp.tzinfo is not None)
    check("OHLC fields populated",
          all(b.open and b.high and b.low and b.close for b in md.bars))
    check("volume populated", all(b.volume is not None for b in md.bars))
    n_adj = sum(1 for b in md.bars if b.adj_close is not None)
    n_vwap = sum(1 for b in md.bars if b.vwap is not None)
    print(f"       adj_close coverage: {n_adj}/{len(md.bars)} bars, "
          f"vwap coverage: {n_vwap}/{len(md.bars)} (provider-dependent)")

    # --- regime classification (what the quant layer would do) ---
    closes = [b.adj_close or b.close for b in md.bars]
    raws = [b.close for b in md.bars]
    close = closes[-1]
    s50, s200 = sma(closes, 50), sma(closes, 200)
    vol20 = realized_vol(closes, 20)
    hi52 = max(b.high for b in md.bars)
    dd = close / hi52 - 1
    regime = classify_regime(close, s50, s200, vol20, dd)

    print(f"\n=== regime inputs (computable from payload) ===")
    check("SMA200 computable", s200 is not None, f"{s200:.2f}" if s200 else "")
    check("SMA50 computable", s50 is not None, f"{s50:.2f}" if s50 else "")
    check("20d realized vol computable", vol20 is not None,
          f"{vol20:.1%}" if vol20 else "")
    check("52w high computable", hi52 > 0, f"{hi52:.2f}")

    print(f"\n=== result ===")
    print(f"  SPY close       : {close:.2f} (raw {raws[-1]:.2f})")
    print(f"  SMA50 / SMA200  : {s50:.2f} / {s200:.2f}")
    print(f"  20d vol (ann.)  : {vol20:.1%}")
    print(f"  drawdown vs 52wH: {dd:.1%}")
    print(f"  REGIME          : {regime}")
    print(f"  served by       : {md.provider} "
          f"({len(svc.attempts)} attempt(s): "
          + ", ".join(f"{a.provider}={'ok' if a.ok else a.error_type}"
                      for a in svc.attempts) + ")")

    if failures:
        print(f"\nFAILED: {failures}")
        sys.exit(1)
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
