#!/usr/bin/env python3
"""
Debug TQQQ engine specifically
"""

import sys
import os
sys.path.append('/app')

import pandas as pd
from datetime import datetime
from app.signal_engines.tqqq_swing_engine import TQQQSwingEngine
from app.signal_engines.base import MarketContext, MarketRegime

def debug_tqqq_engine():
    """Debug TQQQ engine specifically"""
    
    print("🔍 Debugging TQQQ Engine")
    print("=" * 50)
    
    try:
        # Create TQQQ engine
        engine = TQQQSwingEngine()
        print(f"✅ TQQQ Engine created: {engine.name} v{engine.version}")
        
        # Test data from our debug earlier
        indicators = {
            'sma_50': 48.21481000076867,
            'sma_200': 37.6235755943423,
            'ema_20': 47.82294843647125,
            'rsi_14': 41.42857142857143,
            'macd': -0.02669175809708789,
            'macd_signal': 0.09782394737858953,
            'price': 48.21481000076867
        }
        
        print(f"📊 Using indicators: {indicators}")
        
        # Create price data
        price_data = pd.DataFrame({
            'close': [indicators['price']],
            'high': [indicators['price'] * 1.02],
            'low': [indicators['price'] * 0.98],
            'volume': [1000000],
            'sma_20': [indicators['ema_20']],
            'sma_50': [indicators['sma_50']],
            'sma_200': [indicators['sma_200']],
            'ema_20': [indicators['ema_20']],
            'rsi': [indicators['rsi_14']],
            'macd': [indicators['macd']],
            'macd_signal': [indicators['macd_signal']],
            'atr': [indicators['price'] * 0.02]
        })
        
        print(f"📈 Price data shape: {price_data.shape}")
        
        # Create market context
        context = MarketContext(
            regime=MarketRegime.UNKNOWN,
            regime_confidence=0.5,
            vix=20.0,
            nasdaq_trend="neutral"
        )
        
        print(f"🌍 Market context: {context}")
        
        # Generate signal
        print("🚀 Generating signal...")
        signal_result = engine.generate_signal("TQQQ", price_data, context)
        
        print(f"📊 Signal Result:")
        print(f"  Signal: {signal_result.signal}")
        print(f"  Confidence: {signal_result.confidence}")
        print(f"  Reasoning: {signal_result.reasoning}")
        print(f"  Metadata: {signal_result.metadata}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_tqqq_engine()
