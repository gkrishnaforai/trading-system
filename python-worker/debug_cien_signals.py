#!/usr/bin/env python3
"""
End-to-end test: fetch 1-year CIEN data from Yahoo provider, compute indicators, and generate signals.
"""

import sys
import os
from datetime import datetime, timedelta

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.providers.yahoo_finance.client import YahooFinanceClient
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.indicators.moving_averages import calculate_sma, calculate_ema, calculate_sma50, calculate_ema20, calculate_sma200
from app.indicators.momentum import calculate_rsi, calculate_macd
from app.indicators.signals import generate_signal
from app.observability.logging import get_logger

logger = get_logger("debug_cien_signals")

def main():
    symbol = "CIEN"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    print(f"🔍 Fetching 1-year Yahoo historical data for {symbol}")

    # Fetch via thin adapter (compliant path)
    source = YahooFinanceSource()
    try:
        df = source.fetch_price_data(symbol, start=start_date, end=end_date, period="1y")
        if df is None or df.empty:
            print("❌ No data returned from Yahoo source")
            return
        print(f"✅ Fetched {len(df)} rows for {symbol}")
        print(df.head())
        print(df.tail())
    except Exception as e:
        print(f"❌ Fetch error: {e}")
        return

    # Generate technical indicators in-memory
    print("\n--- Generating technical indicators (in-memory) ---")
    try:
        # Moving averages
        df["sma20"] = calculate_sma(df["close"], 20)
        df["ema20"] = calculate_ema(df["close"], 20)
        df["sma50"] = calculate_sma(df["close"], 50)
        df["ema50"] = calculate_ema(df["close"], 50)
        df["sma200"] = calculate_sma(df["close"], 200)

        # Momentum
        df["rsi"] = calculate_rsi(df["close"], 14)
        macd_line, macd_signal, macd_hist = calculate_macd(df["close"])
        df["macd"] = macd_line
        df["macd_signal"] = macd_signal
        df["macd_histogram"] = macd_hist

        print(f"✅ Indicators added, columns: {list(df.columns)}")
    except Exception as e:
        print(f"❌ Indicators error: {e}")
        return

    # Generate signals
    print("\n--- Generating buy/sell/hold signals ---")
    try:
        # Additional required inputs for signal generation
        df["volume_ma"] = df["volume"].rolling(window=20).mean()
        # Simple trend classification based on price vs SMAs
        df["trend_long"] = df.apply(lambda row: 'bullish' if row['close'] > row['sma200'] else 'bearish', axis=1)
        df["trend_medium"] = df.apply(lambda row: 'bullish' if row['ema20'] > row['sma50'] else 'bearish', axis=1)

        signals_series = generate_signal(
            price=df["close"],
            ema20=df["ema20"],
            ema50=df["ema50"],
            sma200=df["sma200"],
            macd_line=df["macd"],
            macd_signal=df["macd_signal"],
            macd_histogram=df["macd_histogram"],
            rsi=df["rsi"],
            volume=df["volume"],
            volume_ma=df["volume_ma"],
            long_term_trend=df["trend_long"],
            medium_term_trend=df["trend_medium"]
        )
        if signals_series is None or signals_series.empty:
            print("❌ No signals generated")
            return
        # Attach signals and confidence back to original df for display
        df["signal"] = signals_series
        # Simple confidence proxy based on signal strength (placeholder)
        df["confidence"] = df["signal"].map({'buy': 0.8, 'sell': 0.8, 'hold': 0.5})
        print(f"✅ Signals generated for {len(df)} periods")
        # Show recent signals with confidence
        recent = df.tail(10)[["date", "signal", "confidence"]].copy()
        print(recent.to_string(index=False))
    except Exception as e:
        print(f"❌ Signal generation error: {e}")
        return

if __name__ == "__main__":
    main()
