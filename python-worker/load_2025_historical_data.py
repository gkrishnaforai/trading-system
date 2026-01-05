#!/usr/bin/env python3
"""
Load 2025 Historical Data for Specified Symbols
Loads full year 2025 data for swing trading engine testing
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def load_2025_historical_data():
    """Load 2025 historical data for specified symbols"""
    
    print("🚀 LOADING 2025 HISTORICAL DATA FOR SWING TRADING")
    print("=" * 60)
    
    # Symbols to load
    stocks = ['SOFI', 'NVDA', 'AVGO', 'MU', 'GOOGL', 'APLD', 'IREN', 'ZETA', 'NBIS', 'CRWV']
    etfs = ['QQQ', 'SMH']
    all_symbols = stocks + etfs
    
    print(f"📊 Loading 2025 data for {len(stocks)} stocks and {len(etfs)} ETFs")
    print(f"🔤 Symbols: {', '.join(all_symbols)}")
    print(f"📅 Date Range: 2025-01-01 to 2025-12-31")
    print()
    
    try:
        # Import data loading components
        from app.data_management.refresh_manager import DataRefreshManager, DataType, RefreshMode
        
        print("✅ DataRefreshManager imported successfully")
        
        # Create refresh manager
        refresh_manager = DataRefreshManager()
        print("✅ DataRefreshManager initialized")
        print()
        
        # Load data for each symbol
        successful_loads = []
        failed_loads = []
        
        for i, symbol in enumerate(all_symbols, 1):
            print(f"📈 [{i}/{len(all_symbols)}] Loading 2025 data for {symbol}...")
            
            try:
                # Load 2025 price data and indicators
                result = refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_HISTORICAL, DataType.INDICATORS],
                    mode=RefreshMode.ON_DEMAND,
                    force=True
                )
                
                if result.total_successful > 0 and result.total_failed == 0:
                    print(f"   ✅ SUCCESS: {result.total_successful} operations completed")
                    successful_loads.append(symbol)
                else:
                    print(f"   ⚠️  PARTIAL: {result.total_successful} successful, {result.total_failed} failed")
                    if result.total_successful > 0:
                        successful_loads.append(symbol)
                    else:
                        failed_loads.append(symbol)
                
                # Show details if available
                if hasattr(result, 'results') and result.results:
                    for operation in result.results:
                        if operation.success:
                            print(f"      ✓ {operation.operation}: {operation.records_processed} records")
                        else:
                            print(f"      ✗ {operation.operation}: {operation.error}")
                
            except Exception as e:
                print(f"   ❌ FAILED: {e}")
                failed_loads.append(symbol)
            
            print()
        
        # Summary
        print("📋 2025 DATA LOADING SUMMARY")
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
            print("1. Check API keys in .env file")
            print("2. Verify symbol validity")
            print("3. Check data source availability")
            print("4. Try individual symbols:")
            for symbol in failed_loads[:3]:  # Show first 3 failed symbols
                print(f"   python -c \"from app.data_management.refresh_manager import DataRefreshManager, DataType, RefreshMode; DataRefreshManager().refresh_data('{symbol}', start_date='2025-01-01', end_date='2025-12-31')\"")
        
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
        import psycopg2
        import os
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Check 2025 data in indicators_daily
        cursor.execute("""
            SELECT DISTINCT symbol, 
                   COUNT(*) as record_count,
                   MIN(date) as start_date,
                   MAX(date) as end_date
            FROM indicators_daily 
            WHERE date >= '2025-01-01' AND date <= '2025-12-31'
            GROUP BY symbol 
            ORDER BY symbol
        """)
        
        symbols = cursor.fetchall()
        
        if not symbols:
            print("❌ No 2025 data found in indicators_daily table")
            print()
            print("🔧 SOLUTION:")
            print("1. Load 2025 historical data:")
            print("   python load_2025_historical_data.py")
            return False
        
        print(f"✅ Found {len(symbols)} symbols with 2025 data:")
        print()
        print(f"{'Symbol':<8} {'Records':<8} {'Date Range':<22} {'Days':<6}")
        print("-" * 50)
        
        total_records = 0
        
        for symbol, count, start_date, end_date in symbols:
            date_range = f"{start_date} to {end_date}"
            days = (end_date - start_date).days + 1 if start_date and end_date else 0
            print(f"{symbol:<8} {count:<8} {date_range:<22} {days:<6}")
            total_records += count
        
        print("-" * 50)
        print(f"{'TOTAL':<8} {total_records:<8} {'':<22} {'':<6}")
        print()
        
        # Check for your specific symbols
        target_symbols = ['SOFI', 'NVDA', 'AVGO', 'MU', 'GOOGL', 'APLD', 'IREN', 'ZETA', 'NBIS', 'CRWV', 'QQQ', 'SMH']
        available_symbols = [s[0] for s in symbols]
        
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
            print(f"   python load_2025_historical_data.py")
        
        conn.close()
        
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
        print("   python load_2025_historical_data.py")
        print("2. Check API keys and data source availability")
        print()
        return False
    
    print()
    
    # Load 2025 data
    success = load_2025_historical_data()
    
    return success

if __name__ == "__main__":
    success = main()
    
    if success:
        print("\n🎉 2025 HISTORICAL DATA LOADING COMPLETED SUCCESSFULLY!")
        print("You can now test the swing engines with full 2025 data.")
    else:
        print("\n❌ 2025 HISTORICAL DATA LOADING FAILED!")
        print("Check the errors above and troubleshoot accordingly.")
