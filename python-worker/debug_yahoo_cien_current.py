#!/usr/bin/env python3
"""
Quick test: fetch current stock data for CIEN using the compliant Yahoo provider stack.
"""

import sys
import os

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.providers.yahoo_finance.client import YahooFinanceClient
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.observability.logging import get_logger

logger = get_logger("debug_yahoo_cien_current")

def main():
    symbol = "CIEN"
    print(f"🔍 Fetching current stock data for {symbol}")

    # 1) Direct via provider client
    print("\n--- Via YahooFinanceClient (provider) ---")
    client = YahooFinanceClient.from_settings()
    try:
        current_price = client.fetch_current_price(symbol)
        print(f"✅ Current price: {current_price}")
    except Exception as e:
        print(f"❌ Provider error: {e}")

    # 2) Via thin adapter (data source)
    print("\n--- Via YahooFinanceSource (thin adapter) ---")
    source = YahooFinanceSource()
    try:
        current_price_adapter = source.fetch_current_price(symbol)
        print(f"✅ Current price via adapter: {current_price_adapter}")
    except Exception as e:
        print(f"❌ Adapter error: {e}")

    # 3) Fetch symbol details for more context
    print("\n--- Symbol details via adapter ---")
    try:
        details = source.fetch_symbol_details(symbol)
        if details:
            print("✅ Symbol details:")
            for k, v in details.items():
                print(f"  {k}: {v}")
        else:
            print("❌ No details returned")
    except Exception as e:
        print(f"❌ Details error: {e}")

if __name__ == "__main__":
    main()
