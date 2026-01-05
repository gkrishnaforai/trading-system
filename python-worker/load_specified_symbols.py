#!/usr/bin/env python3
"""
Load Historical Data for Specified Symbols
Uses existing data loading infrastructure to load data for SOFI, NVDA, AVGO, MU, GOOGL, APLD, IREN, ZETA, NBIS, CRWV, QQQ, SMH
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def load_symbols_data():
    """Load historical data for specified symbols"""
    
    print("🚀 LOADING HISTORICAL DATA FOR SPECIFIED SYMBOLS")
    print("=" * 60)
    
    # Symbols to load
    stocks = ['SOFI', 'NVDA', 'AVGO', 'MU', 'GOOGL', 'APLD', 'IREN', 'ZETA', 'NBIS', 'CRWV']
    etfs = ['QQQ', 'SMH']
    all_symbols = stocks + etfs
    
    print(f"📊 Loading data for {len(stocks)} stocks and {len(etfs)} ETFs")
    print(f"🔤 Symbols: {', '.join(all_symbols)}")
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
            print(f"📈 [{i}/{len(all_symbols)}] Loading {symbol}...")
            
            try:
                # Load price data and indicators
                result = refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_HISTORICAL, DataType.INDICATORS],
                    mode=RefreshMode.ON_DEMAND,
                    force=True,
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
        print("📋 LOADING SUMMARY")
        print("=" * 40)
        print(f"✅ Successful: {len(successful_loads)}/{len(all_symbols)} symbols")
        print(f"❌ Failed: {len(failed_loads)}/{len(all_symbols)} symbols")
        print()
        
        if successful_loads:
            print("✅ Successfully loaded:")
            for symbol in successful_loads:
                print(f"   • {symbol}")
        
        if failed_loads:
            print()
            print("❌ Failed to load:")
            for symbol in failed_loads:
                print(f"   • {symbol}")
        
        # Next steps
        if successful_loads:
            print()
            print("🎉 DATA LOADING COMPLETE!")
            print()
            print("🚀 Next steps:")
            print("1. Test the swing engines:")
            print(f"   python simple_data_loader.py")
            print("2. Test swing trading signals:")
            print(f"   python test_swing_engines_multiple_symbols.py")
            print("3. Use in Streamlit dashboard:")
            print(f"   streamlit run streamlit_trading_dashboard.py")
        
        if failed_loads:
            print()
            print("🔧 TROUBLESHOOTING:")
            print("1. Check API keys in .env file")
            print("2. Verify database connection")
            print("3. Check symbol validity")
            print("4. Try individual symbols:")
            for symbol in failed_loads[:3]:  # Show first 3 failed symbols
                print(f"   python -c \"from app.data_management.refresh_manager import DataRefreshManager; DataRefreshManager().refresh_data('{symbol}')\"")
        
        return len(successful_loads) > 0
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure all dependencies are installed")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def check_database_status():
    """Check if database is accessible"""
    
    print("🔍 CHECKING DATABASE STATUS")
    print("=" * 40)
    
    try:
        import psycopg2
        import os
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Check if tables exist
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('raw_market_data_daily', 'indicators_daily')
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        
        if len(tables) == 2:
            print("✅ Database tables exist")
            
            # Check record counts
            cursor.execute("SELECT COUNT(*) FROM raw_market_data_daily")
            price_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM indicators_daily")
            indicator_count = cursor.fetchone()[0]
            
            print(f"📊 Price records: {price_count:,}")
            print(f"📈 Indicator records: {indicator_count:,}")
            
            if price_count > 0 and indicator_count > 0:
                print("✅ Database contains data")
                return True
            else:
                print("⚠️  Database tables exist but no data")
                return False
        else:
            print("❌ Required tables not found")
            print(f"   Found tables: {[t[0] for t in tables]}")
            return False
            
        conn.close()
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def main():
    """Main function"""
    
    # Check database status first
    if not check_database_status():
        print()
        print("🔧 DATABASE SETUP REQUIRED:")
        print("1. Ensure PostgreSQL is running")
        print("2. Run database migrations")
        print("3. Check .env file for DATABASE_URL")
        print()
        return False
    
    print()
    
    # Load data
    success = load_symbols_data()
    
    return success

if __name__ == "__main__":
    success = main()
    
    if success:
        print("\n🎉 HISTORICAL DATA LOADING COMPLETED SUCCESSFULLY!")
        print("You can now test the swing engines with your specified symbols.")
    else:
        print("\n❌ HISTORICAL DATA LOADING FAILED!")
        print("Check the errors above and troubleshoot accordingly.")
