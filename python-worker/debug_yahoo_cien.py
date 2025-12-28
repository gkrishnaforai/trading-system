#!/usr/bin/env python3
"""
Quick manual test: fetch Yahoo historical data for CIEN using the compliant provider stack.
"""

import sys
import os
from datetime import datetime, timedelta

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.providers.yahoo_finance.client import YahooFinanceClient
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.observability.logging import get_logger

logger = get_logger("debug_yahoo_cien")

def main():
    symbol = "CIEN"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    print(f"🔍 Fetching Yahoo historical data for {symbol} (last 30 days)")

    # 1) Direct via provider client
    print("\n--- Via YahooFinanceClient (provider) ---")
    client = YahooFinanceClient.from_settings()
    try:
        df = client.fetch_price_data(symbol, start=start_date, end=end_date)
        if df is not None and not df.empty:
            print(f"✅ Provider returned {len(df)} rows")
            print(df.head())
        else:
            print("❌ Provider returned None/empty")
    except Exception as e:
        print(f"❌ Provider error: {e}")

    # 2) Via thin adapter (data source)
    print("\n--- Via YahooFinanceSource (thin adapter) ---")
    source = YahooFinanceSource()
    try:
        df2 = source.fetch_price_data(symbol, start=start_date, end=end_date, period="1mo")
        if df2 is not None and not df2.empty:
            print(f"✅ Thin adapter returned {len(df2)} rows")
            print(df2.head())
        else:
            print("❌ Thin adapter returned None/empty")
    except Exception as e:
        print(f"❌ Thin adapter error: {e}")

if __name__ == "__main__":
    main()
