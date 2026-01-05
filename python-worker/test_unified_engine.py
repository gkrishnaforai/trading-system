#!/usr/bin/env python3
"""
Test Unified TQQQ Swing Engine
Test the new unified signal architecture
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

def test_unified_engine():
    """Test the unified TQQQ swing engine"""
    
    print("🚀 TESTING UNIFIED TQQQ SWING ENGINE")
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
        
        # Initialize unified engine with configuration
        config = SignalConfig(
            rsi_oversold=45,
            rsi_moderately_oversold=35,
            rsi_mildly_oversold=50,
            max_volatility=8.0
        )
        
        engine = UnifiedTQQQSwingEngine(config)
        
        # Test on sample days
        sample_days = df.iloc[10:30]  # Test 20 days
        
        print(f"🎯 Testing Unified Engine on Sample Days:")
        print("-" * 50)
        
        buy_count = 0
        sell_count = 0
        hold_count = 0
        
        regime_counts = {
            "mean_reversion": 0,
            "trend_continuation": 0,
            "breakout": 0,
            "volatility_expansion": 0
        }
        
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
                    
                    # Generate signal
                    signal_result = engine.generate_signal(conditions)
                    
                    # Count signals
                    signal_value = signal_result.signal.value
                    if signal_value == "buy":
                        buy_count += 1
                        signal_icon = "🟢"
                    elif signal_value == "sell":
                        sell_count += 1
                        signal_icon = "🔴"
                    else:
                        hold_count += 1
                        signal_icon = "⚪"
                    
                    # Count regimes
                    regime = signal_result.metadata.get('regime', 'unknown')
                    if regime in regime_counts:
                        regime_counts[regime] += 1
                    
                    print(f"   {signal_icon} {signal_result.signal.value.upper()} (confidence: {signal_result.confidence:.2f})")
                    print(f"   Regime: {regime}")
                    print(f"   Reasoning: {signal_result.reasoning[0] if signal_result.reasoning else 'No reasoning'}")
                else:
                    print(f"   ❌ Insufficient data")
                
            except Exception as e:
                print(f"   🚨 Error: {e}")
            
            print()
        
        print(f"📊 UNIFIED ENGINE SUMMARY:")
        print("-" * 40)
        print(f"  BUY Signals: {buy_count}")
        print(f"  SELL Signals: {sell_count}")
        print(f"  HOLD Signals: {hold_count}")
        print(f"  Total Tested: {buy_count + sell_count + hold_count}")
        
        total = buy_count + sell_count + hold_count
        if total > 0:
            buy_rate = (buy_count / total) * 100
            sell_rate = (sell_count / total) * 100
            hold_rate = (hold_count / total) * 100
            print(f"  BUY Rate: {buy_rate:.1f}%")
            print(f"  SELL Rate: {sell_rate:.1f}%")
            print(f"  HOLD Rate: {hold_rate:.1f}%")
        
        print()
        print(f"📊 REGIME DISTRIBUTION:")
        print("-" * 30)
        for regime, count in regime_counts.items():
            if total > 0:
                pct = (count / total) * 100
                print(f"  {regime}: {count} ({pct:.1f}%)")
        
        print()
        print(f"🎯 ANALYSIS:")
        print("-" * 20)
        
        if total > 0:
            if buy_rate >= 30 and buy_rate <= 40:
                print(f"  ✅ BUY rate ({buy_rate:.1f}%) is within target (30-40%)")
            elif buy_rate < 30:
                print(f"  ⚠️  BUY rate ({buy_rate:.1f}%) is below target (30-40%)")
            else:
                print(f"  ⚠️  BUY rate ({buy_rate:.1f}%) is above target (30-40%)")
            
            if sell_count > 0:
                print(f"  ✅ Engine generates SELL signals (complete)")
            else:
                print(f"  ⚠️  No SELL signals (might be too conservative)")
            
            if hold_count > 0:
                print(f"  ✅ Engine generates HOLD signals (risk management)")
            else:
                print(f"  ⚠️  No HOLD signals (might be too aggressive)")
            
            # Check regime diversity
            active_regimes = sum(1 for count in regime_counts.values() if count > 0)
            if active_regimes >= 3:
                print(f"  ✅ Good regime diversity ({active_regimes}/4 active)")
            else:
                print(f"  ⚠️  Limited regime diversity ({active_regimes}/4 active)")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_unified_engine()
