#!/usr/bin/env python3
"""
Load 2025 Historical Data Using Direct Data Source
Bypasses DataRefreshManager to load specific date ranges
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any

def load_2025_data_direct():
    """Load 2025 data using direct data source access"""
    
    print("🚀 LOADING 2025 DATA USING DIRECT DATA SOURCE")
    print("=" * 50)
    
    # Symbols to load
    stocks = ['SOFI', 'NVDA', 'AVGO', 'MU', 'GOOGL', 'APLD', 'IREN', 'ZETA', 'NBIS', 'CRWV']
    etfs = ['QQQ', 'SMH']
    all_symbols = stocks + etfs
    
    print(f"📊 Loading 2025 data for {len(stocks)} stocks and {len(etfs)} ETFs")
    print(f"🔤 Symbols: {', '.join(all_symbols)}")
    print(f"📅 Date Range: 2025-01-01 to 2025-12-31")
    print()
    
    try:
        # Import required components
        from app.data_sources import get_data_source
        from app.utils.technical_calculator import TechnicalIndicatorCalculator
        from app.utils.data_converter import DataConverter, SafeDatabaseOperations
        from app.database import db
        from app.repositories.market_data_daily_repository import MarketDataDailyRepository
        from app.repositories.indicators_repository import IndicatorsRepository
        
        print("✅ Components imported successfully")
        
        # Initialize components
        data_source = get_data_source()
        tech_calc = TechnicalIndicatorCalculator()
        converter = DataConverter()
        market_data_repo = MarketDataDailyRepository()
        indicators_repo = IndicatorsRepository()
        
        print("✅ Components initialized")
        print()
        
        # Load data for each symbol
        successful_loads = []
        failed_loads = []
        
        for i, symbol in enumerate(all_symbols, 1):
            print(f"📈 [{i}/{len(all_symbols)}] Loading 2025 data for {symbol}...")
            
            try:
                # Fetch 2025 price data using data source directly
                start_date = datetime(2025, 1, 1)
                end_date = datetime(2025, 12, 31)
                
                print(f"   📡 Fetching price data...")
                price_df = data_source.fetch_price_data(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    interval="1d"
                )
                
                if price_df is None or price_df.empty:
                    print(f"   ❌ No price data available for {symbol}")
                    failed_loads.append(symbol)
                    continue
                
                print(f"   ✅ Price data: {len(price_df)} records")
                
                # Calculate technical indicators
                print(f"   📊 Calculating indicators...")
                indicators_df = tech_calc.calculate_all_indicators(price_df)
                
                if indicators_df is None or indicators_df.empty:
                    print(f"   ❌ Failed to calculate indicators for {symbol}")
                    failed_loads.append(symbol)
                    continue
                
                print(f"   ✅ Indicators calculated: {len(indicators_df)} records")
                
                # Save to database
                print(f"   💾 Saving to database...")
                
                # Save price data
                price_saved = market_data_repo.upsert_data(price_df)
                
                # Save indicators data
                indicators_saved = indicators_repo.upsert_data(indicators_df)
                
                if price_saved and indicators_saved:
                    print(f"   ✅ SUCCESS: Data saved to database")
                    successful_loads.append(symbol)
                else:
                    print(f"   ⚠️  PARTIAL: Some data saved")
                    if price_saved or indicators_saved:
                        successful_loads.append(symbol)
                    else:
                        failed_loads.append(symbol)
                
            except Exception as e:
                print(f"   ❌ FAILED: {e}")
                failed_loads.append(symbol)
            
            print()
        
        # Summary
        print("📋 DATA LOADING SUMMARY")
        print("=" * 40)
        print(f"✅ Successful: {len(successful_loads)}/{len(all_symbols)} symbols")
        print(f"❌ Failed: {len(failed_loads)}/{len(all_symbols)} symbols")
        print()
        
        if successful_loads:
            print("✅ Successfully loaded 2025 data for:")
            for symbol in successful_loads:
                print(f"   • {symbol}")
        
        if failed_loads:
            print()
            print("❌ Failed to load 2025 data for:")
            for symbol in failed_loads:
                print(f"   • {symbol}")
        
        # Next steps
        if successful_loads:
            print()
            print("🎉 2025 DATA LOADING COMPLETE!")
            print()
            print("🚀 Next steps:")
            print("1. Test the swing engines with 2025 data:")
            print(f"   python test_swing_engines_multiple_symbols.py")
            print("2. Analyze signal performance:")
            print(f"   python simple_data_loader.py")
            print("3. Compare engine performance:")
            print(f"   python load_historical_data_multiple_symbols.py")
        
        if failed_loads:
            print()
            print("🔧 TROUBLESHOOTING:")
            print("1. Check data source availability")
            print("2. Verify symbol validity")
            print("3. Check network connectivity")
            print("4. Try individual symbols:")
            for symbol in failed_loads[:3]:  # Show first 3 failed symbols
                print(f"   python -c \"from app.data_sources import get_data_source; df = get_data_source().fetch_price_data('{symbol}', datetime(2025,1,1), datetime(2025,12,31)); print(f'{symbol}: {len(df) if df is not None else 0} records')\"")
        
        return len(successful_loads) > 0
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure all dependencies are installed")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def check_2025_data_status():
    """Check what 2025 data is currently available"""
    
    print("🔍 CHECKING 2025 DATA STATUS")
    print("=" * 40)
    
    try:
        from app.database import db
        
        # Check 2025 data in indicators_daily
        result = db.execute_query("""
            SELECT DISTINCT symbol, 
                   COUNT(*) as record_count,
                   MIN(date) as start_date,
                   MAX(date) as end_date
            FROM indicators_daily 
            WHERE date >= '2025-01-01' AND date <= '2025-12-31'
            GROUP BY symbol 
            ORDER BY symbol
        """)
        
        if not result:
            print("❌ No 2025 data found in indicators_daily table")
            return False
        
        print(f"✅ Found {len(result)} symbols with 2025 data:")
        print()
        print(f"{'Symbol':<8} {'Records':<8} {'Date Range':<22} {'Days':<6}")
        print("-" * 50)
        
        total_records = 0
        
        for row in result:
            symbol, count, start_date, end_date = row
            date_range = f"{start_date} to {end_date}"
            
            # Handle different date formats and types
            try:
                if isinstance(start_date, str):
                    if len(start_date) == 10:  # YYYY-MM-DD
                        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                    elif len(start_date) == 19:  # YYYY-MM-DD HH:MM:SS
                        start_dt = datetime.strptime(start_date, '%Y-%m-%d %H:%M:%S')
                    else:
                        start_dt = datetime.strptime(start_date[:10], '%Y-%m-%d')
                else:
                    start_dt = start_date
                
                if isinstance(end_date, str):
                    if len(end_date) == 10:  # YYYY-MM-DD
                        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                    elif len(end_date) == 19:  # YYYY-MM-DD HH:MM:SS
                        end_dt = datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S')
                    else:
                        end_dt = datetime.strptime(end_date[:10], '%Y-%m-%d')
                else:
                    end_dt = end_date
                
                days = (end_dt - start_dt).days + 1
            except Exception as e:
                print(f"   ⚠️  Date parsing error for {symbol}: {e}")
                days = 1
            
            print(f"{symbol:<8} {count:<8} {date_range:<22} {days:<6}")
            total_records += count
        
        print("-" * 50)
        print(f"{'TOTAL':<8} {total_records:<8} {'':<22} {'':<6}")
        print()
        
        # Check for your specific symbols
        target_symbols = ['SOFI', 'NVDA', 'AVGO', 'MU', 'GOOGL', 'APLD', 'IREN', 'ZETA', 'NBIS', 'CRWV', 'QQQ', 'SMH']
        available_symbols = [row[0] for row in result]
        
        print("🎯 TARGET SYMBOLS 2025 STATUS:")
        print("-" * 30)
        
        available_targets = []
        missing_targets = []
        
        for symbol in target_symbols:
            if symbol in available_symbols:
                available_targets.append(symbol)
                print(f"✅ {symbol}")
            else:
                missing_targets.append(symbol)
                print(f"❌ {symbol}")
        
        print()
        
        if available_targets:
            print(f"✅ {len(available_targets)} target symbols have 2025 data")
            print("🚀 You can test swing engines with these symbols:")
            print(f"   python test_swing_engines_multiple_symbols.py")
        
        if missing_targets:
            print(f"❌ {len(missing_targets)} target symbols missing 2025 data")
            print("🔧 Load missing 2025 data:")
            print(f"   python load_2025_data_direct.py")
        
        return len(available_targets) > 0
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False

def main():
    """Main function"""
    
    # Check current 2025 data status first
    if not check_2025_data_status():
        print()
        print("🔧 2025 DATA SETUP REQUIRED:")
        print("1. Load 2025 historical data:")
        print("   python load_2025_data_direct.py")
        print()
        return False
    
    print()
    
    # Load 2025 data
    success = load_2025_data_direct()
    
    return success

if __name__ == "__main__":
    success = main()
    
    if success:
        print("\n🎉 2025 HISTORICAL DATA LOADING COMPLETED SUCCESSFULLY!")
        print("You can now test the swing engines with full 2025 data.")
    else:
        print("\n❌ 2025 HISTORICAL DATA LOADING FAILED!")
        print("Check the errors above and troubleshoot accordingly.")
