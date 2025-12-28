#!/usr/bin/env python3
"""
Test case: Pull news for any stock symbol using Yahoo provider.
"""

import sys
import os
from datetime import datetime

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.providers.yahoo_finance.client import YahooFinanceClient
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.observability.logging import get_logger

logger = get_logger("test_yahoo_news")

def test_yahoo_news(symbol: str, limit: int = 10):
    print(f"🔍 Fetching latest {limit} news articles for {symbol} via Yahoo\n")
    client = YahooFinanceClient.from_settings()
    source = YahooFinanceSource()

    # Direct via provider client
    print("--- Via YahooFinanceClient (provider) ---")
    try:
        news = client.fetch_news(symbol, limit=limit)
        if news:
            print(f"✅ Fetched {len(news)} articles")
            for i, article in enumerate(news[:5], 1):
                print(f"\n[{i}] Raw article keys: {list(article.keys())}")
                title = article.get("title", "No title")
                publisher = article.get("publisher", "Unknown")
                pub_time = article.get("published")
                pub_str = datetime.fromtimestamp(pub_time).strftime("%Y-%m-%d %H:%M") if pub_time else "Unknown"
                summary = article.get("summary", "No summary")
                link = article.get("link", "")
                print(f"    Title: {title}")
                print(f"    Publisher: {publisher} | {pub_str}")
                print(f"    Summary: {summary}")
                if link:
                    print(f"    Link: {link}")
        else:
            print("❌ No news returned")
    except Exception as e:
        print(f"❌ Provider error: {e}")

    # Via thin adapter
    print("\n--- Via YahooFinanceSource (thin adapter) ---")
    try:
        news_adapter = source.fetch_news(symbol, limit=limit)
        if news_adapter:
            print(f"✅ Adapter fetched {len(news_adapter)} articles")
        else:
            print("❌ No news returned via adapter")
    except Exception as e:
        print(f"❌ Adapter error: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch Yahoo news for a stock symbol")
    parser.add_argument("symbol", help="Stock symbol (e.g., CIEN)")
    parser.add_argument("--limit", type=int, default=10, help="Number of articles to fetch")
    args = parser.parse_args()
    test_yahoo_news(args.symbol, args.limit)
