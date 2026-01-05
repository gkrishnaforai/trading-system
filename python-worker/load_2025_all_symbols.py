#!/usr/bin/env python3
"""
Load 2025 Historical Data for All Specified Symbols
Based on the working TQQQ data loading script
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def load_2025_data_for_all_symbols():
    """Load 2025 historical data for all specified symbols using working TQQQ pattern"""
    
    print("🚀 LOADING 2025 HISTORICAL DATA FOR ALL SYMBOLS")
    print("=" * 60)
    
    # All your specified symbols
    symbols = ["SOFI", "NVDA", "AVGO", "MU", "GOOGL", "APLD", "IREN", "ZETA", "NBIS", "CRWV", "QQQ", "SMH"]
    
    print(f"📊 Loading 2025 data for {len(symbols)} symbols")
    print(f"🔤 Symbols: {', '.join(symbols)}")
    print(f"📅 Target: Full 2025 year (like TQQQ)")
    print()
    
    try:
        from app.data_management.refresh_manager import DataRefreshManager, DataType, RefreshMode
        
        print("✅ DataRefreshManager imported successfully")
        
        # Create refresh manager (same as working TQQQ script)
        refresh_manager = DataRefreshManager()
        print("✅ DataRefreshManager initialized")
        
        results = {}
        
        for i, symbol in enumerate(symbols, 1):
            print(f"🔄 [{i}/{len(symbols)}] Loading {symbol}...")
            
            try:
                # Use the exact same pattern as working TQQQ script
                result = refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_HISTORICAL, DataType.INDICATORS],
                    mode=RefreshMode.ON_DEMAND,
                    force=True,
                )
                
                results[symbol] = result
                
                if result.total_failed == 0:
                    print(f"   ✅ {symbol}: Successfully loaded {result.total_successful} records")
                else:
                    print(f"   ⚠️  {symbol}: {result.total_failed} operations failed")
                    if result.total_successful > 0:
                        print(f"      But {result.total_successful} succeeded")
                
                # Show operation details if available
                if hasattr(result, 'results') and result.results:
                    for operation in result.results:
                        if operation.success:
                            print(f"      ✓ {operation.operation}: {operation.records_processed} records")
                        else:
                            print(f"      ✗ {operation.operation}: {operation.error}")
                
            except Exception as e:
                print(f"   ❌ {symbol}: Failed to load data - {str(e)}")
                results[symbol] = None
        
        # Summary
        print(f"\n📋 2025 DATA LOADING SUMMARY")
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
        
        # Check if we have enough symbols for swing testing
        if len(successful_symbols) >= 3:  # At least 3 symbols for meaningful testing
            print(f"\n✅ Swing trading ready with {len(successful_symbols)} symbols")
            
            if len(successful_symbols) == len(symbols):
                print("🎉 All symbols loaded successfully!")
            else:
                print(f"⚠️  {len(successful_symbols)}/{len(symbols)} symbols available")
        else:
            print(f"\n❌ Not enough symbols for swing testing (need at least 3)")
        
        return successful_symbols, failed_symbols
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure all dependencies are installed")
        return [], []
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return [], []

def verify_2025_data_loaded():
    """Verify that 2025 data was loaded successfully"""
    
    print("\n🔍 VERIFYING 2025 DATA LOADING")
    print("=" * 40)
    
    try:
        import psycopg2
        import os
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Check 2025 data for all target symbols
        target_symbols = ["SOFI", "NVDA", "AVGO", "MU", "GOOGL", "APLD", "IREN", "ZETA", "NBIS", "CRWV", "QQQ", "SMH"]
        
        cursor.execute("""
            SELECT DISTINCT symbol, 
                   COUNT(*) as record_count,
                   MIN(date) as start_date,
                   MAX(date) as end_date
            FROM indicators_daily 
            WHERE date >= '2025-01-01' AND date <= '2025-12-31'
            AND symbol = ANY(%s)
            GROUP BY symbol 
            ORDER BY symbol
        """, (target_symbols,))
        
        results = cursor.fetchall()
        
        if not results:
            print("❌ No 2025 data found for target symbols")
            return False
        
        print(f"✅ Found 2025 data for {len(results)} symbols:")
        print()
        print(f"{'Symbol':<8} {'Records':<8} {'Date Range':<22} {'Days':<6}")
        print("-" * 50)
        
        total_records = 0
        symbols_with_full_year = []
        
        for row in results:
            symbol, count, start_date, end_date = row
            date_range = f"{start_date} to {end_date}"
            
            # Calculate days
            try:
                if isinstance(start_date, str) and isinstance(end_date, str):
                    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                    days = (end_dt - start_dt).days + 1
                else:
                    days = 1
            except:
                days = 1
            
            print(f"{symbol:<8} {count:<8} {date_range:<22} {days:<6}")
            total_records += count
            
            # Check if we have substantial data (at least 200 records = ~200 trading days)
            if count >= 200:
                symbols_with_full_year.append(symbol)
        
        print("-" * 50)
        print(f"{'TOTAL':<8} {total_records:<8} {'':<22} {'':<6}")
        print()
        
        print(f"📊 SUMMARY:")
        print(f"   Symbols with 2025 data: {len(results)}/{len(target_symbols)}")
        print(f"   Symbols with full year data: {len(symbols_with_full_year)}")
        print(f"   Total 2025 records: {total_records:,}")
        
        if symbols_with_full_year:
            print(f"   ✅ Full year data: {', '.join(symbols_with_full_year)}")
        
        missing_symbols = [s for s in target_symbols if s not in [r[0] for r in results]]
        if missing_symbols:
            print(f"   ❌ Missing data: {', '.join(missing_symbols)}")
        
        conn.close()
        
        return len(symbols_with_full_year) > 0
        
    except Exception as e:
        print(f"❌ Error verifying data: {e}")
        return False

def main():
    """Main function"""
    
    print("🎯 2025 HISTORICAL DATA LOADER")
    print("=" * 60)
    print("Based on working TQQQ data loading script")
    print("Loads full 2025 year data for all specified symbols")
    print()
    
    # Load 2025 data
    successful, failed = load_2025_data_for_all_symbols()
    
    # Verify loading
    has_full_year_data = verify_2025_data_loaded()
    
    # Final summary
    print(f"\n📊 FINAL SUMMARY")
    print("=" * 30)
    print(f"✅ Successful: {len(successful)}/{len(successful + failed)} symbols")
    print(f"❌ Failed: {len(failed)}/{len(successful + failed)} symbols")
    print(f"📅 Full year data: {'✅' if has_full_year_data else '❌'}")
    print()
    
    if successful and has_full_year_data:
        print("🎉 2025 HISTORICAL DATA LOADING COMPLETED!")
        print("You can now test swing engines with full year data.")
        print()
        print("🚀 Next steps:")
        print("1. Test swing engines with 2025 data:")
        print("   python test_swing_engines_multiple_symbols.py")
        print("2. Analyze signal generation:")
        print("   python simple_data_loader.py")
        print("3. Compare engine performance:")
        print("   python comprehensive_signal_analysis.py")
    else:
        print("❌ 2025 HISTORICAL DATA LOADING INCOMPLETE!")
        print("Some symbols may not have full year data.")
        print("Check the errors above and troubleshoot accordingly.")
    
    return len(successful) > 0

if __name__ == "__main__":
    success = main()
