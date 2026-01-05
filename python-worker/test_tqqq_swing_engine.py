#!/usr/bin/env python3
"""
Test Real TQQQ Swing Engine
Test the actual TQQQ swing trading engine with BUY/SELL/HOLD signals
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime

# Import TQQQ swing engine
from app.signal_engines.tqqq_swing_engine import TQQQSwingEngine
from app.signal_engines.base import MarketContext, MarketRegime

def test_tqqq_swing_engine():
    """Test the real TQQQ swing trading engine"""
    
    print("🔍 TESTING REAL TQQQ SWING ENGINE")
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
        print(f"📅 Date range: {df['date'].min()} to {df['date'].max()}")
        print()
        
        # Initialize TQQQ swing engine
        engine = TQQQSwingEngine()
        
        # Create market context (required for TQQQ engine)
        context = MarketContext(
            regime=MarketRegime.BULL,
            regime_confidence=0.7,
            vix=20.0,
            nasdaq_trend="bullish",
            breadth=0.6,
            timestamp=datetime.now()
        )
        
        # Test on sample days
        sample_days = df.iloc[10:30]  # Test 20 days
        
        print(f"🎯 Testing TQQQ Swing Engine on Sample Days:")
        print("-" * 50)
        
        buy_count = 0
        sell_count = 0
        hold_count = 0
        
        for idx, row in sample_days.iterrows():
            date = row['date']
            rsi = row['rsi']
            
            print(f"🔍 {date.strftime('%Y-%m-%d')}: RSI {rsi:.1f}, Price ${row['close']:.2f}")
            
            try:
                # Generate signal using TQQQ swing engine
                signal_result = engine.generate_signal("TQQQ", df, context)
                
                if signal_result:
                    # Count signals
                    if signal_result.signal.value == "BUY":
                        buy_count += 1
                        signal_icon = "🟢"
                    elif signal_result.signal.value == "SELL":
                        sell_count += 1
                        signal_icon = "🔴"
                    else:
                        hold_count += 1
                        signal_icon = "⚪"
                    
                    print(f"   {signal_icon} SIGNAL: {signal_result.signal.value.upper()} (confidence: {signal_result.confidence:.2f})")
                    print(f"   Reasoning: {signal_result.reasoning[0] if signal_result.reasoning else 'No reasoning'}")
                    
                    # Show metadata if available
                    if hasattr(signal_result, 'metadata') and signal_result.metadata:
                        regime = signal_result.metadata.get('regime', 'Unknown')
                        print(f"   Regime: {regime}")
                else:
                    print(f"   ❌ No signal generated")
                
            except Exception as e:
                print(f"   🚨 Error: {e}")
            
            print()
        
        print(f"📊 TQQQ SWING ENGINE SUMMARY:")
        print("-" * 40)
        print(f"  BUY Signals: {buy_count}")
        print(f"  SELL Signals: {sell_count}")
        print(f"  HOLD Signals: {hold_count}")
        print(f"  Total Tested: {buy_count + sell_count + hold_count}")
        
        if buy_count + sell_count + hold_count > 0:
            buy_rate = (buy_count / (buy_count + sell_count + hold_count)) * 100
            sell_rate = (sell_count / (buy_count + sell_count + hold_count)) * 100
            hold_rate = (hold_count / (buy_count + sell_count + hold_count)) * 100
            print(f"  BUY Rate: {buy_rate:.1f}%")
            print(f"  SELL Rate: {sell_rate:.1f}%")
            print(f"  HOLD Rate: {hold_rate:.1f}%")
        
        print()
        
        # Test on more days to get better statistics
        print(f"🎯 TESTING ON LARGER SAMPLE (100 days):")
        print("-" * 40)
        
        larger_sample = df.iloc[10:110]  # Test 100 days
        
        buy_count = 0
        sell_count = 0
        hold_count = 0
        error_count = 0
        
        for idx, row in larger_sample.iterrows():
            try:
                signal_result = engine.generate_signal("TQQQ", df, context)
                
                if signal_result:
                    if signal_result.signal.value == "BUY":
                        buy_count += 1
                    elif signal_result.signal.value == "SELL":
                        sell_count += 1
                    else:
                        hold_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                error_count += 1
                continue
        
        total = buy_count + sell_count + hold_count
        print(f"  Total BUY: {buy_count}")
        print(f"  Total SELL: {sell_count}")
        print(f"  Total HOLD: {hold_count}")
        print(f"  Errors/No Signal: {error_count}")
        print(f"  Total Valid Signals: {total}")
        
        if total > 0:
            buy_rate = (buy_count / total) * 100
            sell_rate = (sell_count / total) * 100
            hold_rate = (hold_count / total) * 100
            print(f"  BUY Rate: {buy_rate:.1f}%")
            print(f"  SELL Rate: {sell_rate:.1f}%")
            print(f"  HOLD Rate: {hold_rate:.1f}%")
        
        print()
        print(f"🎯 ANALYSIS:")
        print("-" * 20)
        
        if total > 0:
            if buy_rate >= 30 and buy_rate <= 40:
                print(f"  ✅ BUY rate ({buy_rate:.1f}%) is within target range (30-40%)")
            elif buy_rate < 30:
                print(f"  ⚠️  BUY rate ({buy_rate:.1f}%) is below target (30-40%)")
            else:
                print(f"  ⚠️  BUY rate ({buy_rate:.1f}%) is above target (30-40%)")
            
            if sell_count > 0:
                print(f"  ✅ Engine generates SELL signals (good for completeness)")
            else:
                print(f"  ⚠️  No SELL signals generated (might be too conservative)")
            
            if hold_count > 0:
                print(f"  ✅ Engine generates HOLD signals (good for risk management)")
            else:
                print(f"  ⚠️  No HOLD signals generated (might be too aggressive)")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_tqqq_swing_engine()
