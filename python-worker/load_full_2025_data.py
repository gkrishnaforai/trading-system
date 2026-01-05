#!/usr/bin/env python3
"""
Load Full 2025 Historical Data - Exact TQQQ Pattern
Uses the exact same approach as the working TQQQ data loader
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def load_full_2025_data():
    """Load full 2025 data using exact TQQQ pattern"""
    
    print("🚀 LOADING FULL 2025 HISTORICAL DATA")
    print("=" * 50)
    print("Using exact same pattern as working TQQQ loader")
    print()
    
    # All your specified symbols
    symbols = ["SOFI", "NVDA", "AVGO", "MU", "GOOGL", "APLD", "IREN", "ZETA", "NBIS", "CRWV", "QQQ", "SMH"]
    
    print(f"📊 Loading full 2025 data for {len(symbols)} symbols")
    print(f"🔤 Symbols: {', '.join(symbols)}")
    print()
    
    try:
        # Use exact same imports as TQQQ script
        from app.data_management.refresh_manager import DataRefreshManager, DataType, RefreshMode
        
        print("✅ DataRefreshManager imported successfully")
        
        # Create refresh manager (exact same as TQQQ script)
        refresh_manager = DataRefreshManager()
        print("✅ DataRefreshManager initialized")
        
        results = {}
        
        for i, symbol in enumerate(symbols, 1):
            print(f"🔄 [{i}/{len(symbols)}] Loading {symbol}...")
            
            try:
                # Use exact same call as TQQQ script
                result = refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_HISTORICAL, DataType.INDICATORS],
                    mode=RefreshMode.ON_DEMAND,
                    force=True,
                )
                
                results[symbol] = result
                
                # Use exact same success logic as TQQQ script
                if result.total_failed == 0:
                    print(f"✅ {symbol}: Successfully loaded {result.total_successful} records")
                else:
                    print(f"⚠️  {symbol}: {result.total_failed} operations failed")
                    if result.total_successful > 0:
                        print(f"   But {result.total_successful} succeeded")
                
                # Show detailed operation results
                if hasattr(result, 'results') and result.results:
                    for data_type, operation_result in result.results.items():
                        if hasattr(operation_result, 'status') and operation_result.status.value == 'success':
                            print(f"   ✓ {data_type}: {operation_result.message}")
                        else:
                            print(f"   ✗ {data_type}: {operation_result.error if hasattr(operation_result, 'error') else 'Unknown error'}")
                
            except Exception as e:
                print(f"❌ {symbol}: Failed to load data - {str(e)}")
                results[symbol] = None
        
        # Summary (exact same as TQQQ script)
        print(f"\n📋 FULL 2025 DATA LOADING SUMMARY")
        print("=" * 40)
        
        successful_symbols = []
        failed_symbols = []
        
        for symbol, result in results.items():
            if result and result.total_failed == 0:
                successful_symbols.append(symbol)
                print(f"✅ {symbol}: READY")
            else:
                failed_symbols.append(symbol)
                print(f"❌ {symbol}: FAILED")
        
        if successful_symbols:
            print(f"\n🎉 Ready for swing trading: {', '.join(successful_symbols)}")
        
        if failed_symbols:
            print(f"\n⚠️  Need attention: {', '.join(failed_symbols)}")
            print("   Check API keys or database connection")
        
        # Check if we have enough symbols (exact same logic as TQQQ script)
        if len(successful_symbols) >= 1:
            print(f"\n✅ Swing trading possible with {len(successful_symbols)} symbols")
            
            if len(successful_symbols) == len(symbols):
                print("🎉 All symbols loaded successfully!")
            else:
                print(f"⚠️  {len(successful_symbols)}/{len(symbols)} symbols available")
        else:
            print(f"\n❌ No symbols loaded successfully")
        
        return successful_symbols, failed_symbols
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure all dependencies are installed")
        return [], []
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return [], []

def check_data_availability():
    """Check what data is actually available in database"""
    
    print("\n🔍 CHECKING ACTUAL DATA AVAILABILITY")
    print("=" * 50)
    
    try:
        import psycopg2
        import os
        from datetime import datetime
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Check all data for target symbols
        target_symbols = ["SOFI", "NVDA", "AVGO", "MU", "GOOGL", "APLD", "IREN", "ZETA", "NBIS", "CRWV", "QQQ", "SMH"]
        
        cursor.execute("""
            SELECT DISTINCT symbol, 
                   COUNT(*) as record_count,
                   MIN(date) as start_date,
                   MAX(date) as end_date
            FROM indicators_daily 
            WHERE symbol = ANY(%s)
            GROUP BY symbol 
            ORDER BY symbol
        """, (target_symbols,))
        
        results = cursor.fetchall()
        
        if not results:
            print("❌ No data found for target symbols")
            return False
        
        print(f"✅ Found data for {len(results)} symbols:")
        print()
        print(f"{'Symbol':<8} {'Records':<8} {'Date Range':<22} {'Type':<10}")
        print("-" * 60)
        
        symbols_with_2025 = []
        symbols_with_recent = []
        
        for row in results:
            symbol, count, start_date, end_date = row
            date_range = f"{start_date} to {end_date}"
            
            # Determine data type
            if start_date and end_date:
                try:
                    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                    days = (end_dt - start_dt).days + 1
                    
                    if start_dt.year == 2025 and end_dt.year == 2025 and days >= 200:
                        data_type = "2025 Full"
                        symbols_with_2025.append(symbol)
                    elif start_dt.year == 2025:
                        data_type = "2025 Partial"
                    else:
                        data_type = "Recent"
                        symbols_with_recent.append(symbol)
                except:
                    data_type = "Unknown"
            else:
                data_type = "Recent"
                symbols_with_recent.append(symbol)
            
            print(f"{symbol:<8} {count:<8} {date_range:<22} {data_type:<10}")
        
        print("-" * 60)
        print()
        
        print(f"📊 SUMMARY:")
        print(f"   Symbols with 2025 data: {len(symbols_with_2025)}")
        print(f"   Symbols with recent data: {len(symbols_with_recent)}")
        print(f"   Total symbols with data: {len(results)}")
        
        if symbols_with_2025:
            print(f"   ✅ Full 2025 data: {', '.join(symbols_with_2025)}")
        
        if symbols_with_recent:
            print(f"   ⚠️  Recent data only: {', '.join(symbols_with_recent)}")
        
        conn.close()
        
        return len(symbols_with_2025) > 0
        
    except Exception as e:
        print(f"❌ Error checking data: {e}")
        return False

def main():
    """Main function"""
    
    print("🎯 FULL 2025 HISTORICAL DATA LOADER")
    print("=" * 50)
    print("Exact same pattern as working TQQQ loader")
    print()
    
    # Load data
    successful, failed = load_full_2025_data()
    
    # Check actual data availability
    has_2025_data = check_data_availability()
    
    # Final summary
    print(f"\n📊 FINAL SUMMARY")
    print("=" * 30)
    print(f"✅ Successful: {len(successful)}/{len(successful + failed)} symbols")
    print(f"❌ Failed: {len(failed)}/{len(successful + failed)} symbols")
    print(f"📅 2025 Data: {'✅' if has_2025_data else '❌'}")
    print()
    
    if successful:
        print("🎉 DATA LOADING COMPLETED!")
        print("Now you can test swing engines.")
        print()
        print("🚀 Next steps:")
        print("1. Test swing engines:")
        print("   python test_swing_engines_multiple_symbols.py")
        print("2. Analyze signals:")
        print("   python simple_data_loader.py")
        
        if not has_2025_data:
            print("⚠️  Note: Some symbols may only have recent data")
            print("   Consider loading more historical data if needed")
    else:
        print("❌ DATA LOADING FAILED!")
        print("Check the errors above and troubleshoot.")
    
    return len(successful) > 0

if __name__ == "__main__":
    success = main()
