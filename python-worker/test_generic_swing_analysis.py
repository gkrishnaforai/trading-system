"""
Generic Swing Trading Analysis
Use the Generic Swing Engine for any stock or ETF analysis
"""

import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.signal_engines.generic_swing_engine import GenericSwingEngine
from app.signal_engines.tqqq_swing_engine import TQQQSwingEngine
from app.utils.technical_indicators import TechnicalIndicators
from app.utils.database_helper import DatabaseQueryHelper
from app.observability.logging import get_logger

logger = get_logger(__name__)

def analyze_symbol_with_generic_engine(symbol: str, days_back: int = 100):
    """Analyze any symbol using the Generic Swing Engine"""
    
    print(f"🔍 Analyzing {symbol} with Generic Swing Engine")
    print("=" * 50)
    
    try:
        # Initialize the generic swing engine
        engine = GenericSwingEngine()
        print(f"✅ Engine initialized: {engine.get_metadata()['display_name']}")
        
        # Load historical data
        db = DatabaseQueryHelper()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        print(f"📊 Loading {days_back} days of data for {symbol}...")
        market_data = db.get_historical_data(symbol, start_date, end_date)
        
        if market_data is None or market_data.empty:
            print(f"❌ No data found for {symbol}")
            return None
        
        print(f"✅ Loaded {len(market_data)} days of data")
        print(f"   Price range: ${market_data['close'].min():.2f} - ${market_data['close'].max():.2f}")
        print(f"   Latest price: ${market_data['close'].iloc[-1]:.2f}")
        
        # Create market context
        from app.signal_engines.base import MarketContext, MarketRegime
        market_context = MarketContext(
            regime=MarketRegime.BULL,
            regime_confidence=0.7,
            vix=20.0,
            nasdaq_trend="bullish",
            sector_rotation={},
            breadth=0.6,
            yield_curve_spread=0.02
        )
        
        # Generate signal
        print(f"🎯 Generating swing trading signal...")
        signal_result = engine.generate_signal(symbol, market_data, market_context)
        
        # Display results
        print(f"\n📊 Swing Trading Analysis for {symbol}")
        print("=" * 40)
        print(f"🎯 Signal: {signal_result.signal.value}")
        print(f"📈 Confidence: {signal_result.confidence:.1%}")
        print(f"💰 Position Size: {signal_result.position_size_pct:.1%}")
        print(f"⏱️  Timeframe: {signal_result.timeframe}")
        
        if signal_result.entry_price_range:
            print(f"📍 Entry Range: ${signal_result.entry_price_range[0]:.2f} - ${signal_result.entry_price_range[1]:.2f}")
        
        if signal_result.stop_loss:
            print(f"🛑 Stop Loss: ${signal_result.stop_loss:.2f}")
        
        if signal_result.take_profit:
            print(f"🎯 Take Profit: ${signal_result.take_profit[0]:.2f}")
        
        print(f"\n💡 Engine Reasoning:")
        for reason in signal_result.reasoning:
            print(f"   • {reason}")
        
        print(f"\n📋 Metadata:")
        for key, value in signal_result.metadata.items():
            print(f"   {key}: {value}")
        
        return signal_result
        
    except Exception as e:
        print(f"❌ Error analyzing {symbol}: {e}")
        return None

def compare_engines_for_symbol(symbol: str):
    """Compare both engines for a symbol (for educational purposes)"""
    
    print(f"🔄 Comparing Engines for {symbol}")
    print("=" * 40)
    
    try:
        # Load data
        db = DatabaseQueryHelper()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=100)
        
        market_data = db.get_historical_data(symbol, start_date, end_date)
        
        if market_data is None or market_data.empty:
            print(f"❌ No data found for {symbol}")
            return
        
        # Create market context
        from app.signal_engines.base import MarketContext, MarketRegime
        market_context = MarketContext(
            regime=MarketRegime.BULL,
            regime_confidence=0.7,
            vix=20.0,
            nasdaq_trend="bullish",
            sector_rotation={},
            breadth=0.6,
            yield_curve_spread=0.02
        )
        
        # Test Generic Swing Engine
        print(f"\n📊 Generic Swing Engine Results:")
        generic_engine = GenericSwingEngine()
        generic_signal = generic_engine.generate_signal(symbol, market_data, market_context)
        
        print(f"   Signal: {generic_signal.signal.value}")
        print(f"   Confidence: {generic_signal.confidence:.1%}")
        print(f"   Position Size: {generic_signal.position_size_pct:.1%}")
        
        # Test TQQQ Engine (only if symbol is TQQQ)
        if symbol.upper() == "TQQQ":
            print(f"\n📊 TQQQ Swing Engine Results:")
            tqqq_engine = TQQQSwingEngine()
            tqqq_signal = tqqq_engine.generate_signal(symbol, market_data, market_context)
            
            print(f"   Signal: {tqqq_signal.signal.value}")
            print(f"   Confidence: {tqqq_signal.confidence:.1%}")
            print(f"   Position Size: {tqqq_signal.position_size_pct:.1%}")
            
            # Compare
            print(f"\n🔄 Comparison:")
            if generic_signal.signal != tqqq_signal.signal:
                print(f"   ⚠️  Different signals: Generic={generic_signal.signal.value}, TQQQ={tqqq_signal.signal.value}")
            else:
                print(f"   ✅ Same signal: {generic_signal.signal.value}")
        else:
            print(f"\n⚠️  TQQQ Engine not suitable for {symbol} (only for TQQQ)")
        
    except Exception as e:
        print(f"❌ Error comparing engines: {e}")

def recommend_engine_for_symbol(symbol: str):
    """Recommend the best engine for a given symbol"""
    
    print(f"🎯 Engine Recommendation for {symbol}")
    print("=" * 40)
    
    symbol_upper = symbol.upper()
    
    # Check if it's a leveraged ETF
    leveraged_patterns = ['TQQQ', 'QQQ', 'SPY', 'SOXL', 'TECL', 'FNGU', 'LABU', 'NUGT']
    
    if symbol_upper in leveraged_patterns:
        if symbol_upper == 'TQQQ':
            print(f"🎯 Recommended: TQQQ Swing Engine")
            print(f"   Reason: Specifically designed for TQQQ with leverage decay awareness")
            print(f"   Features: VIX monitoring, QQQ correlation, shorter holding periods")
        else:
            print(f"⚠️  Caution: {symbol_upper} is a leveraged ETF")
            print(f"   Recommended: Generic Swing Engine (with caution)")
            print(f"   Reason: TQQQ engine is highly specialized for TQQQ only")
            print(f"   Advice: Consider higher volatility and potential leverage decay")
    else:
        print(f"🎯 Recommended: Generic Swing Engine")
        print(f"   Reason: Standard stock/ETF with normal volatility patterns")
        print(f"   Features: Standard technical analysis, 2-10 day holding periods")
        print(f"   Risk: Moderate risk management suitable for regular instruments")
    
    print(f"\n📋 Engine Suitability:")
    print(f"   ✅ Generic Swing Engine: Suitable for most stocks and ETFs")
    print(f"   ⚠️  TQQQ Swing Engine: Only for TQQQ (highly specialized)")

def main():
    """Main function to demonstrate swing trading analysis"""
    
    print("🎯 Swing Trading Engine Analysis")
    print("=" * 40)
    
    # Test symbols
    test_symbols = ["AAPL", "MSFT", "SPY", "TQQQ"]
    
    for symbol in test_symbols:
        print(f"\n{'='*60}")
        recommend_engine_for_symbol(symbol)
        
        if symbol == "TQQQ":
            # Use TQQQ engine for TQQQ
            analyze_symbol_with_generic_engine(symbol)
            compare_engines_for_symbol(symbol)
        else:
            # Use generic engine for other symbols
            analyze_symbol_with_generic_engine(symbol)
        
        print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
