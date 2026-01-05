#!/usr/bin/env python3
"""
Generic Historical Data Loader
Reuses the working TQQQ data loading pattern for any symbol
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_generic_historical_data(symbols: list):
    """Load historical data for any symbols using the working TQQQ pattern"""
    
    print("🚀 GENERIC HISTORICAL DATA LOADER")
    print("=" * 50)
    
    print(f"📊 Loading data for {len(symbols)} symbols:")
    print(f"🔤 Symbols: {', '.join(symbols)}")
    print()
    
    try:
        from app.data_management.refresh_manager import DataRefreshManager, DataType, RefreshMode
        
        print("✅ DataRefreshManager imported successfully")
        
        # Create refresh manager (same as TQQQ loader)
        refresh_manager = DataRefreshManager()
        print("✅ DataRefreshManager initialized")
        
        results = {}
        
        for i, symbol in enumerate(symbols, 1):
            print(f"🔄 [{i}/{len(symbols)}] Loading {symbol}...")
            
            try:
                # Use the exact same pattern as TQQQ loader
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
        print(f"\n📋 DATA LOADING SUMMARY")
        print("=" * 30)
        
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
        
        return successful_symbols, failed_symbols
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure all dependencies are installed")
        return [], []
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return [], []

def main():
    """Main function - load data for your specified symbols"""
    
    print("🎯 GENERIC HISTORICAL DATA LOADER")
    print("=" * 50)
    print("Reuses the working TQQQ data loading pattern for any symbol")
    print()
    
    # Your specified symbols
    stocks = ['SOFI', 'NVDA', 'AVGO', 'MU', 'GOOGL', 'APLD', 'RIEN', 'ZETA', 'NBIS', 'CRWV']
    etfs = ['QQQ', 'SMH']
    all_symbols = stocks + etfs
    
    print(f"📊 Target symbols: {len(stocks)} stocks, {len(etfs)} ETFs")
    print(f"🔤 Total: {len(all_symbols)} symbols")
    print()
    
    # Load data
    successful, failed = load_generic_historical_data(all_symbols)
    
    # Final summary
    print(f"\n📊 FINAL SUMMARY")
    print("=" * 30)
    print(f"✅ Successful: {len(successful)}/{len(all_symbols)} symbols")
    print(f"❌ Failed: {len(failed)}/{len(all_symbols)} symbols")
    print()
    
    if successful:
        print("✅ Successfully loaded data for:")
        for symbol in successful:
            print(f"   • {symbol}")
        print()
        print("🚀 Next steps:")
        print("1. Test swing engines with loaded data:")
        print("   python test_swing_engines_multiple_symbols.py")
        print("2. Analyze signal generation:")
        print("   python simple_data_loader.py")
        print("3. Use in Streamlit dashboard:")
        print("   streamlit run streamlit_trading_dashboard.py")
    
    if failed:
        print("❌ Failed to load data for:")
        for symbol in failed:
            print(f"   • {symbol}")
        print()
        print("🔧 Troubleshooting:")
        print("1. Check API keys in .env file")
        print("2. Verify symbol validity")
        print("3. Try individual symbols:")
        for symbol in failed[:3]:  # Show first 3 failed symbols
            print(f"   python -c \"from load_generic_historical_data import load_generic_historical_data; load_generic_historical_data(['{symbol}'])\"")
    
    return len(successful) > 0

if __name__ == "__main__":
    success = main()
    
    if success:
        print("\n🎉 GENERIC HISTORICAL DATA LOADING COMPLETED!")
        print("You can now test swing engines with your specified symbols.")
    else:
        print("\n❌ GENERIC HISTORICAL DATA LOADING FAILED!")
        print("Check the errors above and troubleshoot accordingly.")
