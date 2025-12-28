#!/usr/bin/env python3
"""
Show how Yahoo Finance classifies a symbol into sector/industry.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import yfinance as yf

def show_classification(symbol):
    print(f"Yahoo Finance classification for {symbol}:\n")
    ticker = yf.Ticker(symbol)
    info = ticker.info
    
    print(f"Symbol: {symbol}")
    print(f"Sector: {info.get('sector', 'N/A')}")
    print(f"Industry: {info.get('industry', 'N/A')}")
    print(f"Full business summary: {info.get('longBusinessSummary', 'N/A')[:300]}...")
    print("\nAll available info keys (first 20):")
    for i, key in enumerate(list(info.keys())[:20]):
        print(f"  {key}: {info.get(key, 'N/A')}")

if __name__ == "__main__":
    show_classification("IREN")
