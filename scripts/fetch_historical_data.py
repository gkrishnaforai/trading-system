#!/usr/bin/env python3
"""
On-demand historical data fetcher
Can be used to fetch data for specific symbols or backfill historical data
"""
import sys
import os
import argparse
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "python-worker"))

from app.database import init_database
from app.services.data_fetcher import DataFetcher
from app.services.indicator_service import IndicatorService


def main():
    parser = argparse.ArgumentParser(description="Fetch historical data and calculate indicators")
    parser.add_argument("symbol", help="Stock symbol (e.g., AAPL)")
    parser.add_argument("--period", default="1y", help="Period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max")
    parser.add_argument("--no-indicators", action="store_true", help="Skip indicator calculation")
    parser.add_argument("--no-fundamentals", action="store_true", help="Skip fundamental data")
    parser.add_argument("--no-options", action="store_true", help="Skip options data")
    
    args = parser.parse_args()
    
    symbol = args.symbol.upper()
    
    print(f"📥 Fetching historical data for {symbol}...")
    print(f"   Period: {args.period}")
    
    # Initialize database
    init_database()
    
    # Fetch data
    data_fetcher = DataFetcher()
    success = data_fetcher.fetch_and_save_stock(
        symbol,
        period=args.period,
        include_fundamentals=not args.no_fundamentals,
        include_options=not args.no_options
    )
    
    if not success:
        print(f"❌ Failed to fetch data for {symbol}")
        sys.exit(1)
    
    print(f"✅ Data fetched successfully for {symbol}")
    
    # Calculate indicators
    if not args.no_indicators:
        print(f"📊 Calculating indicators for {symbol}...")
        indicator_service = IndicatorService()
        success = indicator_service.calculate_indicators(symbol)
        
        if success:
            print(f"✅ Indicators calculated successfully for {symbol}")
        else:
            print(f"⚠️ Warning: Failed to calculate indicators for {symbol}")
    else:
        print("⏭️  Skipping indicator calculation")
    
    print(f"\n✅ Complete! Data and indicators are now available for {symbol}")


if __name__ == "__main__":
    main()

