#!/usr/bin/env python3
"""
Debug Unified Engine - Check Regime Detection
Debug why we're only getting mean_reversion regime
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime

# Import unified engine
from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions

def debug_regime_detection():
    """Debug regime detection logic"""
    
    print("🔍 DEBUGGING REGIME DETECTION")
    print("=" * 50)
    
    # Load data
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
            FROM indicators_daily i
            JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
            WHERE i.symbol = 'TQQQ' 
            AND i.date >= '2025-01-01' 
            AND i.date <= '2025-12-31'
            ORDER BY i.date
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            print("❌ No 2025 data found")
            return
        
        df = pd.DataFrame(rows, columns=[
            'date', 'close', 'rsi', 'sma_50', 'ema_20', 'macd', 'macd_signal', 'volume', 'low', 'high'
        ])
        df['date'] = pd.to_datetime(df['date'])
        
        print(f"✅ Loaded {len(df)} records from 2025")
        print()
        
        # Initialize unified engine
        config = SignalConfig(
            rsi_oversold=45,
            rsi_moderately_oversold=35,
            rsi_mildly_oversold=50,
            max_volatility=8.0
        )
        
        engine = UnifiedTQQQSwingEngine(config)
        
        # Test on first 10 days with detailed debugging
        sample_days = df.iloc[10:20]
        
        print(f"🎯 DETAILED REGIME ANALYSIS:")
        print("-" * 50)
        
        for idx, row in sample_days.iterrows():
            date = row['date']
            rsi = row['rsi']
            
            print(f"🔍 {date.strftime('%Y-%m-%d')}: RSI {rsi:.1f}, Price ${row['close']:.2f}")
            
            try:
                # Create market conditions
                pos = df.index.get_loc(idx)
                if pos >= 2:
                    recent_close = df.iloc[pos-2]['close']
                    recent_change = (row['close'] - recent_close) / recent_close
                    
                    start_idx = max(0, pos - 19)
                    volatility_data = df.iloc[start_idx:pos+1]['close'].pct_change().dropna()
                    volatility = volatility_data.std() * 100 if len(volatility_data) > 1 else 2.0
                    
                    conditions = MarketConditions(
                        rsi=row['rsi'],
                        sma_20=row['ema_20'],
                        sma_50=row['sma_50'],
                        ema_20=row['ema_20'],
                        current_price=row['close'],
                        recent_change=recent_change,
                        macd=row['macd'],
                        macd_signal=row['macd_signal'],
                        volatility=volatility
                    )
                    
                    # Debug regime detection
                    print(f"   📊 Market Conditions:")
                    print(f"      RSI: {conditions.rsi:.1f}")
                    print(f"      Recent Change: {conditions.recent_change:+.2%}")
                    print(f"      Volatility: {conditions.volatility:.1f}%")
                    print(f"      SMA20: ${conditions.sma_20:.2f}")
                    print(f"      SMA50: ${conditions.sma_50:.2f}")
                    print(f"      Current Price: ${conditions.current_price:.2f}")
                    
                    # Calculate trend conditions
                    is_uptrend = (
                        conditions.sma_20 > conditions.sma_50 and
                        conditions.current_price > conditions.sma_20
                    )
                    
                    is_downtrend = (
                        conditions.sma_20 < conditions.sma_50 and
                        conditions.current_price < conditions.sma_20
                    )
                    
                    print(f"   🎯 Regime Logic:")
                    print(f"      Is Uptrend: {is_uptrend}")
                    print(f"      Is Downtrend: {is_downtrend}")
                    print(f"      Volatility > {config.max_volatility}%: {conditions.volatility > config.max_volatility}")
                    print(f"      Recent Change > 3%: {conditions.recent_change > 0.03}")
                    print(f"      RSI > 60: {conditions.rsi > 60}")
                    print(f"      Price > SMA20: {conditions.current_price > conditions.sma_20}")
                    
                    # Check each regime condition
                    print(f"   🔍 Regime Checks:")
                    
                    # Volatility Expansion
                    if conditions.volatility > config.max_volatility:
                        print(f"      ✅ VOLATILITY_EXPANSION: Volatility {conditions.volatility:.1f}% > {config.max_volatility}%")
                    else:
                        print(f"      ❌ VOLATILITY_EXPANSION: Volatility {conditions.volatility:.1f}% <= {config.max_volatility}%")
                    
                    # Breakout
                    if (conditions.recent_change > 0.03 and 
                        conditions.rsi > 60 and 
                        conditions.current_price > conditions.sma_20):
                        print(f"      ✅ BREAKOUT: All conditions met")
                    else:
                        print(f"      ❌ BREAKOUT: Change={conditions.recent_change:.2%}, RSI={conditions.rsi:.1f}, Price>SMA20={conditions.current_price > conditions.sma_20}")
                    
                    # Trend Continuation
                    if is_uptrend:
                        print(f"      ✅ TREND_CONTINUATION: Uptrend detected")
                    else:
                        print(f"      ❌ TREND_CONTINUATION: Not uptrend")
                    
                    # Mean Reversion (default)
                    print(f"      📋 MEAN_REVERSION: Default regime")
                    
                    # Get actual regime
                    regime = engine.detect_market_regime(conditions)
                    print(f"   🎯 FINAL REGIME: {regime.value}")
                    
                    # Generate signal
                    signal_result = engine.generate_signal(conditions)
                    print(f"   📡 SIGNAL: {signal_result.signal.value.upper()} (confidence: {signal_result.confidence:.2f})")
                    print(f"   💭 Reasoning: {signal_result.reasoning[0] if signal_result.reasoning else 'No reasoning'}")
                
            except Exception as e:
                print(f"   🚨 Error: {e}")
            
            print()
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_regime_detection()
