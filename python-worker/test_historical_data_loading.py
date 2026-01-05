#!/usr/bin/env python3
"""
Load Historical Data for Specified Symbols
Based on the working TQQQ data loading pattern
"""

import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def load_historical_data_for_symbols():
    """Load historical data for specified symbols using TQQQ pattern"""
    
    print("🎯 LOADING HISTORICAL DATA FOR SPECIFIED SYMBOLS")
    print("=" * 60)
    print("Based on working TQQQ data loading pattern")
    print()
    
    # Your specified symbols (same pattern as TQQQ script)
    symbols = ["SOFI", "NVDA", "AVGO", "MU", "GOOGL", "APLD", "IREN", "ZETA", "NBIS", "CRWV", "QQQ", "SMH"]
    
    print(f"📊 Loading historical data for {len(symbols)} symbols")
    print(f"🔤 Symbols: {', '.join(symbols)}")
    print()
    
    try:
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
                
                # Show detailed operation results (fixed version)
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
        print(f"\n📋 HISTORICAL DATA LOADING SUMMARY")
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

def verify_data_loaded():
    """Verify that data was loaded successfully"""
    
    print("\n🔍 VERIFYING DATA LOADING")
    print("=" * 40)
    
    try:
        import psycopg2
        import os
        from datetime import datetime
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Check data for all target symbols
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
        print(f"{'Symbol':<8} {'Records':<8} {'Date Range':<22} {'Status':<10}")
        print("-" * 60)
        
        symbols_with_substantial_data = []
        
        for row in results:
            symbol, count, start_date, end_date = row
            date_range = f"{start_date} to {end_date}"
            
            # Determine status
            if count >= 200:
                status = "Full Year"
                symbols_with_substantial_data.append(symbol)
            elif count >= 50:
                status = "Partial"
            else:
                status = "Limited"
            
            print(f"{symbol:<8} {count:<8} {date_range:<22} {status:<10}")
        
        print("-" * 60)
        print()
        
        print(f"📊 SUMMARY:")
        print(f"   Symbols with data: {len(results)}/{len(target_symbols)}")
        print(f"   Symbols with substantial data: {len(symbols_with_substantial_data)}")
        
        if symbols_with_substantial_data:
            print(f"   ✅ Substantial data: {', '.join(symbols_with_substantial_data)}")
        
        missing_symbols = [s for s in target_symbols if s not in [r[0] for r in results]]
        if missing_symbols:
            print(f"   ❌ Missing data: {', '.join(missing_symbols)}")
        
        conn.close()
        
        return len(symbols_with_substantial_data) > 0
        
    except Exception as e:
        print(f"❌ Error verifying data: {e}")
        return False

def main():
    """Main function - exact same structure as TQQQ script"""
    
    print("🚀 HISTORICAL DATA LOADER")
    print("=" * 60)
    print("Based on working TQQQ data loading pattern")
    print("Loads historical data for specified symbols")
    print()
    
    # Load data
    successful, failed = load_historical_data_for_symbols()
    
    # Verify data
    has_substantial_data = verify_data_loaded()
    
    # Final summary
    print(f"\n📊 FINAL SUMMARY")
    print("=" * 30)
    print(f"✅ Successful: {len(successful)}/{len(successful + failed)} symbols")
    print(f"❌ Failed: {len(failed)}/{len(successful + failed)} symbols")
    print(f"📅 Substantial data: {'✅' if has_substantial_data else '❌'}")
    print()
    
    if successful:
        print("🎉 HISTORICAL DATA LOADING COMPLETED!")
        print("You can now test swing engines with loaded data.")
        print()
        print("🚀 Next steps:")
        print("1. Test swing engines:")
        print("   python test_swing_engines_multiple_symbols.py")
        print("2. Analyze signals:")
        print("   python simple_data_loader.py")
        print("3. Compare engines:")
        print("   python comprehensive_signal_analysis.py")
        
        if not has_substantial_data:
            print("⚠️  Note: Some symbols may have limited historical data")
            print("   Consider loading more data if needed for comprehensive testing")
    else:
        print("❌ HISTORICAL DATA LOADING FAILED!")
        print("Check the errors above and troubleshoot accordingly.")
    
    return len(successful) > 0

if __name__ == "__main__":
    success = main()
    
    if success:
        print("\n🎉 HISTORICAL DATA LOADING COMPLETED SUCCESSFULLY!")
        print("You can now test swing engines with your specified symbols.")
    else:
        print("\n❌ HISTORICAL DATA LOADING FAILED!")
        print("Check the errors above and troubleshoot accordingly.")
