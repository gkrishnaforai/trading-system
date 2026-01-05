#!/usr/bin/env python3
"""
Diagnose Data Loading Issues
Check API keys, data sources, and test individual symbol loading
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def diagnose_data_loading():
    """Diagnose data loading infrastructure"""
    
    print("🔍 DIAGNOSING DATA LOADING INFRASTRUCTURE")
    print("=" * 50)
    
    # Check 1: Environment variables
    print("📋 CHECKING ENVIRONMENT VARIABLES:")
    print("-" * 30)
    
    env_vars = {
        'DATABASE_URL': os.getenv('DATABASE_URL', 'NOT_SET'),
        'ALPHA_VANTAGE_API_KEY': os.getenv('ALPHA_VANTAGE_API_KEY', 'NOT_SET'),
        'MASSIVE_API_KEY': os.getenv('MASSIVE_API_KEY', 'NOT_SET'),
        'PYTHON_API_HOST': os.getenv('PYTHON_API_HOST', '127.0.0.1'),
        'PYTHON_API_PORT': os.getenv('PYTHON_API_PORT', '8001')
    }
    
    for var, value in env_vars.items():
        status = "✅" if value != 'NOT_SET' else "❌"
        display_value = value if var != 'ALPHA_VANTAGE_API_KEY' and var != 'MASSIVE_API_KEY' else ("SET" if value != 'NOT_SET' else "NOT_SET")
        print(f"   {status} {var}: {display_value}")
    
    print()
    
    # Check 2: Database connection
    print("🗄️  CHECKING DATABASE CONNECTION:")
    print("-" * 30)
    
    try:
        import psycopg2
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM raw_market_data_daily")
        price_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM indicators_daily")
        indicator_count = cursor.fetchone()[0]
        
        print(f"   ✅ Database connected")
        print(f"   📊 Price records: {price_count:,}")
        print(f"   📈 Indicator records: {indicator_count:,}")
        
        conn.close()
        
    except Exception as e:
        print(f"   ❌ Database connection failed: {e}")
        return False
    
    print()
    
    # Check 3: Data sources
    print("📡 CHECKING DATA SOURCES:")
    print("-" * 30)
    
    try:
        from app.data_sources import get_data_source
        data_source = get_data_source()
        
        print(f"   ✅ Data source initialized: {type(data_source).__name__}")
        
        # Test data source availability
        test_symbols = ['AAPL', 'TQQQ', 'QQQ']
        
        for symbol in test_symbols[:2]:  # Test first 2 symbols
            try:
                print(f"   📊 Testing {symbol}...")
                
                # Try to get recent data
                data = data_source.get_daily_data(symbol, days=5)
                
                if data is not None and not data.empty:
                    print(f"      ✅ {symbol}: {len(data)} records available")
                else:
                    print(f"      ❌ {symbol}: No data available")
                    
            except Exception as e:
                print(f"      ❌ {symbol}: Error - {e}")
        
    except Exception as e:
        print(f"   ❌ Data source initialization failed: {e}")
        return False
    
    print()
    
    # Check 4: Data refresh manager
    print("🔄 CHECKING DATA REFRESH MANAGER:")
    print("-" * 30)
    
    try:
        from app.data_management.refresh_manager import DataRefreshManager, DataType, RefreshMode
        
        refresh_manager = DataRefreshManager()
        print(f"   ✅ DataRefreshManager initialized")
        
        # Test with a known symbol (TQQQ should work)
        print(f"   📊 Testing TQQQ refresh...")
        
        result = refresh_manager.refresh_data(
            symbol='TQQQ',
            data_types=[DataType.PRICE_HISTORICAL],
            mode=RefreshMode.ON_DEMAND,
            force=True,
            start_date='2025-01-01',
            end_date='2025-01-05'  # Small date range for testing
        )
        
        if result.total_successful > 0:
            print(f"      ✅ TQQQ: {result.total_successful} operations successful")
        else:
            print(f"      ❌ TQQQ: {result.total_failed} operations failed")
            
            # Show error details
            if hasattr(result, 'results') and result.results:
                for operation in result.results:
                    if not operation.success:
                        print(f"         ✗ {operation.operation}: {operation.error}")
        
    except Exception as e:
        print(f"   ❌ DataRefreshManager failed: {e}")
        return False
    
    print()
    
    # Check 5: Test individual symbol loading
    print("🎯 TESTING INDIVIDUAL SYMBOL LOADING:")
    print("-" * 30)
    
    # Test a few target symbols
    test_symbols = ['NVDA', 'GOOGL', 'QQQ']
    
    for symbol in test_symbols:
        try:
            print(f"   📈 Testing {symbol} 2025 data...")
            
            # Try to load data for just this symbol
            from app.data_management.refresh_manager import DataRefreshManager, DataType, RefreshMode
            
            refresh_manager = DataRefreshManager()
            
            result = refresh_manager.refresh_data(
                symbol=symbol,
                data_types=[DataType.PRICE_HISTORICAL, DataType.INDICATORS],
                mode=RefreshMode.ON_DEMAND,
                force=True,
                start_date='2025-01-01',
                end_date='2025-01-31'  # One month for testing
            )
            
            if result.total_successful > 0:
                print(f"      ✅ {symbol}: {result.total_successful} operations successful")
            else:
                print(f"      ❌ {symbol}: {result.total_failed} operations failed")
                
                # Show error details
                if hasattr(result, 'results') and result.results:
                    for operation in result.results:
                        if not operation.success:
                            print(f"         ✗ {operation.operation}: {operation.error}")
            
        except Exception as e:
            print(f"      ❌ {symbol}: Error - {e}")
    
    print()
    
    # Recommendations
    print("💡 RECOMMENDATIONS:")
    print("-" * 20)
    
    alpha_vantage_key = os.getenv('ALPHA_VANTAGE_API_KEY', 'NOT_SET')
    massive_key = os.getenv('MASSIVE_API_KEY', 'NOT_SET')
    
    if alpha_vantage_key == 'NOT_SET':
        print("   🔧 Set ALPHA_VANTAGE_API_KEY in .env file")
        print("   Get key from: https://www.alphavantage.co/support/#api-key")
    
    if massive_key == 'NOT_SET':
        print("   🔧 Set MASSIVE_API_KEY in .env file (if available)")
    
    print("   🔧 Test with symbols that have good data availability:")
    print("      - TQQQ (should work)")
    print("      - AAPL (usually works)")
    print("      - QQQ (should work)")
    print("   🔧 Try smaller date ranges first")
    print("   🔧 Check data source documentation")
    
    return True

def test_simple_symbol_loading():
    """Test loading a simple symbol with minimal requirements"""
    
    print("\n🧪 TESTING SIMPLE SYMBOL LOADING")
    print("=" * 40)
    
    try:
        from app.data_management.refresh_manager import DataRefreshManager, DataType, RefreshMode
        
        refresh_manager = DataRefreshManager()
        
        # Test with TQQQ (should have data)
        print("📈 Testing TQQQ (known working symbol)...")
        
        result = refresh_manager.refresh_data(
            symbol='TQQQ',
            data_types=[DataType.PRICE_HISTORICAL],
            mode=RefreshMode.ON_DEMAND,
            force=True,
            start_date='2025-01-01',
            end_date='2025-01-10'  # 10 days
        )
        
        print(f"   Result: {result.total_successful} successful, {result.total_failed} failed")
        
        if result.total_successful > 0:
            print("   ✅ Basic data loading works")
            return True
        else:
            print("   ❌ Basic data loading failed")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def main():
    """Main diagnostic function"""
    
    print("🚀 DATA LOADING DIAGNOSTIC TOOL")
    print("=" * 50)
    print("This tool helps identify why 2025 data loading is failing")
    print()
    
    # Run diagnostics
    basic_works = diagnose_data_loading()
    
    if basic_works:
        test_simple_symbol_loading()
    
    print("\n🎯 NEXT STEPS:")
    print("1. Fix any issues identified above")
    print("2. Run: python load_2025_historical_data.py")
    print("3. Test with: python test_swing_engines_multiple_symbols.py")

if __name__ == "__main__":
    main()
