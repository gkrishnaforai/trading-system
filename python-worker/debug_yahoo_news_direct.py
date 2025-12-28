#!/usr/bin/env python3
"""
Direct test of yfinance news using your exact pattern.
"""

import yfinance as yf

def test_yahoo_news_direct(symbol):
    print(f"Testing direct yfinance news for {symbol}\n")
    ticker = yf.Ticker(symbol)
    news_articles = ticker.news

    if not news_articles:
        print("No news articles returned.")
        return

    print(f"Latest news for {symbol} ({len(news_articles)} articles):")
    for i, article in enumerate(news_articles[:5], 1):
        print(f"\n[{i}] Raw article keys: {list(article.keys())}")
        print(f"* Title: {article.get('title', 'MISSING')}")
        print(f"  Link: {article.get('link', 'MISSING')}")
        print(f"  Publisher: {article.get('publisher', 'MISSING')}")
        print(f"  Published: {article.get('providerPublishTime', 'MISSING')}")
        print(f"  Summary: {article.get('summary', 'MISSING')}")
        print("-" * 40)

if __name__ == "__main__":
    test_yahoo_news_direct("AAPL")
