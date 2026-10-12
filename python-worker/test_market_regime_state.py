"""
Market regime state test — builds the exact MarketState the LLM agent needs:

    SPY price, EMA20, SMA50, SMA200, RSI14, volume ratio, breadth %, VIX

All from the routed market-data layer. Breadth is approximated as the % of
the 11 sector SPDRs trading above their SMA50 (provider-agnostic; a real
advance/decline feed can replace it later).

Run:  ./venv/bin/python test_market_regime_state.py
"""
import asyncio
import sys
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, ".")

from app.market_data import MarketDataService, indicators

SPY = "SPY"
VIX_SYMBOL = "^VIX"
SECTOR_ETFS = [
    "XLK", "XLF", "XLE", "XLV", "XLY", "XLP",
    "XLI", "XLU", "XLRE", "XLB", "XLC",
]


@dataclass
class MarketState:
    spy_price: float
    ema20: Optional[float]
    sma50: Optional[float]
    sma200: Optional[float]
    rsi: Optional[float]
    volume_ratio: Optional[float]
    breadth_pct: Optional[float]
    vix: Optional[float]


async def build_market_state(svc: MarketDataService) -> MarketState:
    md = await svc.get_market_data(SPY, period="1y", min_bars=200)
    assert md and md.bars, "no SPY bars"

    spy_price = md.bars[-1].close
    quote = await svc.get_quote(SPY)
    if quote and quote.price:
        spy_price = quote.price

    # VIX via the same router — FMP or Yahoo, whichever answers
    vix = None
    vix_quote = await svc.get_quote(VIX_SYMBOL)
    if vix_quote:
        vix = vix_quote.price

    # Breadth proxy: % of sector SPDRs above SMA50
    breadth = await _breadth_above_sma50(svc)

    return MarketState(
        spy_price=spy_price,
        ema20=indicators.ema(md.bars, 20),
        sma50=indicators.sma(md.bars, 50),
        sma200=indicators.sma(md.bars, 200),
        rsi=indicators.rsi(md.bars, 14),
        volume_ratio=indicators.volume_ratio(md.bars, 20),
        breadth_pct=breadth,
        vix=vix,
    )


async def _breadth_above_sma50(svc: MarketDataService) -> Optional[float]:
    above = 0
    total = 0
    for etf in SECTOR_ETFS:
        try:
            bars = await svc.get_ohlcv(etf, period="3mo", interval="1d")
            s50 = indicators.sma(bars, 50)
            if s50 is not None and bars:
                total += 1
                if bars[-1].close > s50:
                    above += 1
        except Exception as e:
            print(f"  breadth: {etf} skipped ({e})")
    return round(above / total * 100, 1) if total else None


async def main():
    svc = MarketDataService()
    print(f"providers: {svc.providers}\n")

    state = await build_market_state(svc)

    required = {
        "spy_price": state.spy_price,
        "ema20": state.ema20,
        "sma50": state.sma50,
        "sma200": state.sma200,
        "rsi": state.rsi,
        "volume_ratio": state.volume_ratio,
        "breadth_pct": state.breadth_pct,
        "vix": state.vix,
    }
    print("=== MarketState ===")
    missing = []
    for k, v in required.items():
        ok = v is not None
        if not ok:
            missing.append(k)
        shown = f"{v:.2f}" if isinstance(v, float) else v
        print(f"  [{'PASS' if ok else 'MISS'}] {k:<13} = {shown}")

    # The exact prompt payload the LLM agent would receive
    print("\n=== LLM prompt payload ===")
    print(f"""    Market state:
    SPY: {state.spy_price}
    EMA20: {state.ema20}
    SMA50: {state.sma50}
    SMA200: {state.sma200}
    RSI: {state.rsi}
    Volume Ratio: {state.volume_ratio}
    Breadth: {state.breadth_pct}%
    VIX: {state.vix}""")

    # provider provenance for the Langfuse layer
    print("\n=== attempts ===")
    for a in svc.attempts:
        print(f"  {a.provider}/{a.capability}: "
              f"{'ok' if a.ok else a.error_type} {a.latency_ms:.0f}ms")

    if missing:
        print(f"\nMISSING FIELDS: {missing}")
        sys.exit(1)
    print("\nALL MARKET STATE FIELDS POPULATED")


if __name__ == "__main__":
    asyncio.run(main())
