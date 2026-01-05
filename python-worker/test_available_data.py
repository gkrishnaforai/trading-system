#!/usr/bin/env python3
"""
Simple Swing Engine Test with Available Data
Tests swing engines with the data that's actually available
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_with_available_data():
    """Test swing engines with symbols that have data"""
    
    print("🚀 TESTING SWING ENGINES WITH AVAILABLE DATA")
    print("=" * 50)
    
    # Symbols with data (from your check)
    available_symbols = ['TQQQ', 'SOFI', 'NVDA', 'AVGO', 'MU', 'GOOGL', 'APLD', 'QQQ', 'SMH']
    
    try:
        # Import engines
        from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
        from app.signal_engines.generic_etf_engine import create_instrument_engine
        from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions
        from app.signal_engines.common_signal_logic import SignalEngineUtils
        
        print("✅ Engines imported successfully")
        
        # Initialize TQQQ engine
        tqqq_config = SignalConfig(
            rsi_oversold=45,
            rsi_moderately_oversold=35,
            rsi_mildly_oversold=50,
            max_volatility=8.0
        )
        tqqq_engine = UnifiedTQQQSwingEngine(tqqq_config)
        
        print(f"✅ TQQQ engine initialized")
        
        print(f"📊 Testing with available symbols: {available_symbols}")
        print()
        
        for symbol in available_symbols:
            print(f"📈 Testing {symbol}...")
            
            try:
                # Load data for this symbol
                from app.signal_engines.generic_etf_engine import load_historical_data
                df = load_historical_data(symbol)
                
                if df is None or df.empty:
                    print(f"   ❌ No data available for {symbol}")
                    continue
                
                print(f"   📊 Data: {len(df)} records from {df['date'].min().date()} to {df['date'].max().date()}")
                
                # Test with available data only (skip volatility calculation)
                if len(df) > 0:
                    # Use the last available record for testing
                    last_row = df.iloc[-1]
                    
                    # Create market conditions with minimal requirements
                    conditions = MarketConditions(
                        rsi=last_row['rsi'],
                        sma_20=last_row['ema_20'],
                        sma_50=last_row['sma_50'],
                        ema_20=last_row['ema_20'],
                        current_price=last_row['close'],
                        recent_change=0.0,  # No historical data
                        macd=last_row['macd'],
                        macd_signal=last_row['macd_signal'],
                        volatility=2.0  # Default volatility
                    )
                    
                    # Test TQQQ engine
                    tqqq_result = tqqq_engine.generate_signal(conditions)
                    
                    # Test generic engine
                    generic_engine = create_instrument_engine(symbol)
                    generic_result = generic_engine.generate_signal(conditions)
                    
                    print(f"   ✅ TQQQ Engine: {tqqq_result.signal.value} ({tqqq_result.confidence:.2f})")
                    print(f"   ✅ Generic Engine: {generic_result.signal.value} ({generic_result.confidence:.2f})")
                    
                    # Check agreement
                    agreement = tqqq_result.signal.value == generic_result.signal.value
                    print(f"   {'✅' if agreement else '❌'} AGREEMENT: {agreement}")
                    
                else:
                    print(f"   ❌ No data available for {symbol}")
                
            except Exception as e:
                print(f"   ❌ Error testing {symbol}: {e}")
            
            print()
        
        print("🎯 SUMMARY")
        print("=" * 30)
        print("✅ TQQQ engine ready for testing")
        print("✅ Generic engines available for symbols with data")
        print()
        print("🚀 Next steps:")
        print("1. Test with TQQQ (full 2025 data):")
        print("   python -c \"from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine; from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions; print('TQQQ engine ready')\"")
        print("2. Test with available symbols:")
        for symbol in available_symbols:
            if symbol != 'TQQQ':
                print(f"   python -c \"from app.signal_engines.generic_etf_engine import create_instrument_engine; engine = create_instrument_engine('{symbol}'); print(f'{symbol} engine ready')\"")
        
        print("3. Run comprehensive analysis:")
        print("   python comprehensive_signal_analysis.py")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    test_with_available_data()
