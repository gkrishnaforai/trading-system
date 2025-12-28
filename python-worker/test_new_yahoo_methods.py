#!/usr/bin/env python3
"""
Test new Yahoo provider methods: quarterly earnings history and analyst recommendations (Finnhub fallback) for CIEN.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.providers.yahoo_finance.client import YahooFinanceClient
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.observability.logging import get_logger

logger = get_logger("test_new_yahoo_methods")

def main():
    symbol = "CIEN"
    print(f"🔍 Testing new Yahoo provider methods for {symbol}\n")

    client = YahooFinanceClient.from_settings()
    source = YahooFinanceSource()

    # Quarterly earnings history
    print("--- Quarterly earnings history (Yahoo income_stmt/cash_flow) ---")
    try:
        earnings = client.fetch_quarterly_earnings_history(symbol)
        if earnings:
            print(f"✅ Fetched {len(earnings)} quarters")
            for q in earnings[:4]:
                print(f"  Period: {q['period']}")
                print(f"    Revenue: {q['revenue']}")
                print(f"    Net income: {q['net_income']}")
                print(f"    EPS (diluted): {q['eps_diluted']}")
                print(f"    Operating cash flow: {q.get('operating_cash_flow')}")
        else:
            print("❌ No earnings history returned")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Analyst recommendations (Finnhub fallback)
    print("\n--- Analyst recommendations (Finnhub fallback) ---")
    try:
        recs = client.fetch_analyst_recommendations(symbol)
        if recs:
            print(f"✅ Fetched {len(recs)} recommendation periods")
            for r in recs[:3]:
                print(f"  Period: {r['period']}")
                print(f"    Strong buy: {r['strong_buy']}, Buy: {r['buy']}, Hold: {r['hold']}, Sell: {r['sell']}, Strong sell: {r['strong_sell']}")
        else:
            print("❌ No analyst recommendations returned (check FINNHUB_API_KEY)")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Via thin adapter
    print("\n--- Via thin adapter (YahooFinanceSource) ---")
    try:
        earnings_adapter = source.fetch_quarterly_earnings_history(symbol)
        recs_adapter = source.fetch_analyst_recommendations(symbol)
        print(f"✅ Adapter earnings: {len(earnings_adapter)} quarters")
        print(f"✅ Adapter recommendations: {len(recs_adapter)} periods")
    except Exception as e:
        print(f"❌ Adapter error: {e}")

if __name__ == "__main__":
    main()
