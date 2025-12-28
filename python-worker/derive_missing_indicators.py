#!/usr/bin/env python3
"""
Derive missing indicators/metrics from existing Yahoo provider data for CIEN.
"""

import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from app.providers.yahoo_finance.client import YahooFinanceClient
from app.indicators.moving_averages import calculate_sma, calculate_ema
from app.indicators.momentum import calculate_rsi, calculate_macd

def main():
    symbol = "CIEN"
    client = YahooFinanceClient.from_settings()

    # Fetch 1-year price data
    df = client.fetch_price_data(symbol, period="1y")
    if df is None or df.empty:
        print("❌ No price data")
        return

    # Compute technical indicators
    df["sma20"] = calculate_sma(df["close"], 20)
    df["sma200"] = calculate_sma(df["close"], 200)
    df["ema20"] = calculate_ema(df["close"], 20)
    df["ema50"] = calculate_ema(df["close"], 50)
    df["rsi"] = calculate_rsi(df["close"], 14)
    macd_line, macd_signal, macd_hist = calculate_macd(df["close"])
    df["macd"] = macd_line
    df["macd_signal"] = macd_signal
    df["volume_ma"] = df["volume"].rolling(20).mean()
    df["volume_trend"] = df["volume"] / df["volume_ma"]

    # Show latest values
    latest = df.iloc[-1]
    print(f"Latest technical indicators for {symbol}:")
    print(f"  Price: {latest['close']:.2f}")
    print(f"  SMA20: {latest['sma20']:.2f}")
    print(f"  SMA200: {latest['sma200']:.2f}")
    print(f"  EMA20: {latest['ema20']:.2f}")
    print(f"  EMA50: {latest['ema50']:.2f}")
    print(f"  RSI: {latest['rsi']:.2f}")
    print(f"  MACD: {latest['macd']:.4f}")
    print(f"  Volume trend (ratio): {latest['volume_trend']:.2f}")

    # Financial strength metrics from fundamentals
    fundamentals = client.fetch_fundamentals(symbol)
    if fundamentals:
        print("\nFinancial strength from fundamentals:")
        for k in ["debt_to_equity", "return_on_equity", "return_on_assets", "profit_margin", "operating_margin", "current_ratio"]:
            v = fundamentals.get(k)
            print(f"  {k}: {v}")

    # Valuation metrics
    print("\nValuation from fundamentals:")
    for k in ["pe_ratio", "pb_ratio", "price_to_sales", "forward_pe", "enterprise_value", "eps"]:
        v = fundamentals.get(k)
        print(f"  {k}: {v}")

    # Note: EV/EBITDA can be derived if EBITDA is available
    ev = fundamentals.get("enterprise_value")
    if ev and fundamentals.get("operating_income"):
        ebitda = fundamentals.get("operating_income")  # proxy
        if ebitda:
            print(f"  EV/EBITDA (proxy): {ev / ebitda:.2f}")

if __name__ == "__main__":
    main()
