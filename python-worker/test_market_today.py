"""
Daily direction check: what the market-data layer CAN and CANNOT answer.

CAN:   is SPY green/red right now (live quote vs previous close)
CAN:   regime prior (weak lean, not a prediction)
CANNOT: reliably predict today's close from EOD bars alone.
        For that you'd wire in overnight futures / premarket gap / VIX.

Run:  ./venv/bin/python test_market_today.py
"""
import asyncio
import sys

sys.path.insert(0, ".")

from app.market_data import MarketDataService


async def main():
    svc = MarketDataService()

    # --- Q1: is it green or red right now? ---
    q = await svc.get_quote("SPY")
    if q is None:
        print("no quote available")
        return

    state = "GREEN" if (q.change or 0) > 0 else "RED" if (q.change or 0) < 0 else "FLAT"
    print(f"SPY now     : {q.price:.2f}  ({q.change:+.2f}, {q.change_percent:+.2f}%)  -> {state}")
    print(f"quote as_of : {q.as_of}  provider={q.provider}")

    # --- Q2: regime prior (a lean, not a call) ---
    md = await svc.get_market_data("SPY", period="1y", min_bars=200)
    closes = [b.adj_close or b.close for b in md.bars]
    sma200 = sum(closes[-200:]) / 200
    above = closes[-1] > sma200
    print(f"regime prior: {'bull' if above else 'bear'} "
          f"(close {closes[-1]:.2f} vs SMA200 {sma200:.2f}) — "
          f"base-rate green-day odds ~{'55%' if above else '50%'}")

    # --- what you'd need for a real prediction ---
    print("\nTo actually call today's direction you'd add:")
    print("  - overnight/premarket gap (ES futures or premarket quote)")
    print("  - VIX level + change")
    print("  - prior-day close vs overnight session")
    print("Quote polling during the session is observation, not prediction.")


if __name__ == "__main__":
    asyncio.run(main())
