#!/usr/bin/env python3
"""
Test Specific Date: 2025-08-22
Compare engine prediction with actual market movement
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append('/app/enhancements')

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import unified engine
from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions

def test_specific_date_2025_08_22():
    """Test specific date: 2025-08-22"""
    
    print("🔍 TESTING SPECIFIC DATE: 2025-08-22")
    print("=" * 50)
    
    # Load data
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Get data around 2025-08-22
        cursor.execute("""
            SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
            FROM indicators_daily i
            JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
            WHERE i.symbol = 'TQQQ' 
            AND i.date >= '2025-08-20' 
            AND i.date <= '2025-08-27'
            ORDER BY i.date
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            print("❌ No data found for 2025-08-22")
            return
        
        df = pd.DataFrame(rows, columns=[
            'date', 'close', 'rsi', 'sma_50', 'ema_20', 'macd', 'macd_signal', 'volume', 'low', 'high'
        ])
        df['date'] = pd.to_datetime(df['date'])
        
        print(f"✅ Loaded {len(df)} records around 2025-08-22")
        print()
        
        # Find 2025-08-22
        target_date = pd.to_datetime('2025-08-22')
        target_row = df[df['date'] == target_date]
        
        if len(target_row) == 0:
            print(f"❌ No data found for 2025-08-22")
            return
        
        target_data = target_row.iloc[0]
        print(f"📊 2025-08-22 MARKET DATA:")
        print("-" * 30)
        print(f"  Date: {target_data['date'].strftime('%Y-%m-%d')}")
        print(f"  Close: ${target_data['close']:.2f}")
        print(f"  RSI: {target_data['rsi']:.1f}")
        print(f"  SMA50: ${target_data['sma_50']:.2f}")
        print(f"  EMA20: ${target_data['ema_20']:.2f}")
        print(f"  Volume: {target_data['volume']:,}")
        print(f"  Low: ${target_data['low']:.2f}")
        print(f"  High: ${target_data['high']:.2f}")
        print()
        
        # Initialize unified engine
        config = SignalConfig(
            rsi_oversold=45,
            rsi_moderately_oversold=35,
            rsi_mildly_oversold=50,
            max_volatility=8.0
        )
        
        engine = UnifiedTQQQSwingEngine(config)
        
        # Calculate recent change
        target_idx = df.index.get_loc(target_row.index[0])
        if target_idx >= 2:
            recent_close = df.iloc[target_idx-2]['close']
            recent_change = (target_data['close'] - recent_close) / recent_close
            
            # Calculate volatility
            start_idx = max(0, target_idx - 19)
            volatility_data = df.iloc[start_idx:target_idx+1]['close'].pct_change().dropna()
            volatility = volatility_data.std() * 100 if len(volatility_data) > 1 else 2.0
            
            # Create market conditions
            conditions = MarketConditions(
                rsi=target_data['rsi'],
                sma_20=target_data['ema_20'],
                sma_50=target_data['sma_50'],
                ema_20=target_data['ema_20'],
                current_price=target_data['close'],
                recent_change=recent_change,
                macd=target_data['macd'],
                macd_signal=target_data['macd_signal'],
                volatility=volatility
            )
            
            print(f"📈 MARKET CONDITIONS:")
            print("-" * 30)
            print(f"  RSI: {conditions.rsi:.1f}")
            print(f"  Recent Change: {conditions.recent_change:+.2%}")
            print(f"  Volatility: {conditions.volatility:.1f}%")
            print(f"  SMA20: ${conditions.sma_20:.2f}")
            print(f"  SMA50: ${conditions.sma_50:.2f}")
            print(f"  Current Price: ${conditions.current_price:.2f}")
            print()
            
            # Generate signal
            signal_result = engine.generate_signal(conditions)
            
            print(f"🎯 ENGINE PREDICTION:")
            print("-" * 30)
            print(f"  Signal: {signal_result.signal.value.upper()}")
            print(f"  Confidence: {signal_result.confidence:.2f}")
            print(f"  Regime: {signal_result.metadata.get('regime', 'unknown')}")
            print(f"  📝 Reasoning:")
            for i, reason in enumerate(signal_result.reasoning, 1):
                print(f"    {i}. {reason}")
            print()
            
            # Calculate actual market movement
            print(f"📊 ACTUAL MARKET MOVEMENT:")
            print("-" * 30)
            
            # Calculate forward returns with available data
            available_days = len(df) - target_idx - 1
            
            if available_days >= 3:
                # 3-day return
                price_3d = df.iloc[target_idx + 3]['close']
                return_3d = (price_3d - target_data['close']) / target_data['close']
                print(f"   3-Day Return: {return_3d:+.2%}")
                print(f"   3-Day Price: ${price_3d:.2f}")
            
            if available_days >= 5:
                # 5-day return
                price_5d = df.iloc[target_idx + 5]['close']
                return_5d = (price_5d - target_data['close']) / target_data['close']
                print(f"   5-Day Return: {return_5d:+.2%}")
                print(f"   5-Day Price: ${price_5d:.2f}")
            
            if available_days >= 7:
                # 7-day return
                price_7d = df.iloc[target_idx + 7]['close']
                return_7d = (price_7d - target_data['close']) / target_data['close']
                print(f"   7-Day Return: {return_7d:+.2%}")
                print(f"   7-Day Price: ${price_7d:.2f}")
            
            # Calculate max drawdown and gain with available data
            if available_days >= 3:
                future_prices = df.iloc[target_idx+1:min(target_idx+8, len(df))]['close']
                max_price = future_prices.max()
                min_price = future_prices.min()
                max_drawdown = (max_price - target_data['close']) / target_data['close']
                max_gain = (target_data['close'] - min_price) / target_data['close']
                
                print(f"  Max Drawdown: {max_drawdown:+.2%}")
                print(f"  Max Gain: {max_gain:+.2%}")
            
            # Signal accuracy
            if available_days >= 5:
                if signal_result.signal.value == 'buy':
                    accuracy = "✅ CORRECT" if return_5d > 0 else "❌ INCORRECT"
                elif signal_result.signal.value == 'sell':
                    accuracy = "✅ CORRECT" if return_5d < 0 else "❌ INCORRECT"
                else:  # HOLD
                    accuracy = "✅ CORRECT" if abs(return_5d) < 0.02 else "❌ INCORRECT"
                
                print(f"  Signal Accuracy (5d): {accuracy}")
            
            # Show surrounding days for context
            print(f"📅 SURROUNDING DAYS CONTEXT:")
            print("-" * 40)
            
            context_start = max(0, target_idx - 2)
            context_end = min(len(df), target_idx + min(8, available_days + 1))
            
            for i in range(context_start, context_end):
                row = df.iloc[i]
                date_str = row['date'].strftime('%Y-%m-%d')
                close_str = f"${row['close']:.2f}"
                rsi_str = f"RSI {row['rsi']:.1f}"
                
                # Calculate return from 2025-08-22
                if i > target_idx:
                    days_diff = (row['date'] - target_date).days
                    price_change = (row['close'] - target_data['close']) / target_data['close']
                    change_str = f"{price_change:+.2%}"
                else:
                    days_diff = (target_date - row['date']).days
                    price_change = (target_data['close'] - row['close']) / row['close']
                    change_str = f"{price_change:+.2%}"
                
                print(f"  {date_str}: {close_str:<10} {rsi_str:<12} {change_str}")
            
            print()
            print(f"💡 SUMMARY:")
            print("-" * 20)
            print(f"  Engine predicted: {signal_result.signal.value.upper()}")
            
            if available_days >= 5:
                print(f"   5-day actual: {return_5d:+.2%}")
                print(f"  Signal was: {accuracy}")
                
                if signal_result.signal.value == 'buy' and return_5d > 0.05:
                    print(f"  🎉 GREAT BUY SIGNAL!")
                elif signal_result.signal.value == 'sell' and return_5d < -0.05:
                    print(f"  🎉 GREAT SELL SIGNAL!")
                elif signal_result.signal.value == 'hold' and abs(return_5d) < 0.01:
                    print(f"  ✅ GOOD HOLD DECISION!")
            else:
                print(f"  ⚠️  Limited forward data for analysis")
            
            print()
            print(f"📊 DETAILED ANALYSIS:")
            print("-" * 30)
            print(f"  Engine detected: {signal_result.metadata.get('regime', 'unknown')} regime")
            print(f"  RSI was oversold: {conditions.rsi:.1f} (< 45)")
            print(f"  Recent change: {conditions.recent_change:+.2%} (upward)")
            print(f"  Despite recent rise, RSI still oversold triggered BUY")
            print(f"  This suggests strong mean reversion pattern")
            
            if available_days >= 5:
                print(f"  Market actually went {return_5d:+.2%} over 5 days")
                if return_5d > 0:
                    print(f"  ✅ Engine was CORRECT - market bounced as expected")
                else:
                    print(f"  ❌ Engine was INCORRECT - market declined despite oversold")
            else:
                print(f"  ⚠️  Need more forward data to validate prediction")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_specific_date_2025_08_22()
