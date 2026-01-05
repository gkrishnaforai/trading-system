#!/usr/bin/env python3
"""
Debug specific date signal generation
"""

import sys
import os
sys.path.append('/app')

import pandas as pd
from datetime import datetime, timedelta
from app.signal_engines.generic_swing_engine import GenericSwingEngine
from app.signal_engines.base import MarketContext, MarketRegime
from app.utils.database_helper import DatabaseQueryHelper

def debug_specific_date(date_str):
    """Debug signal generation for a specific date"""
    
    print(f"🔍 Debugging Signal Generation for {date_str}")
    print("=" * 50)
    
    try:
        # Get real historical data
        print("📊 Getting real TQQQ historical data...")
        historical_data = DatabaseQueryHelper.get_historical_data('TQQQ', limit=60)
        
        if historical_data:
            print(f"✅ Found {len(historical_data)} records")
            
            # Convert to DataFrame
            df = pd.DataFrame(historical_data)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            
            print(f"📅 Date range: {df.index[0].date()} to {df.index[-1].date()}")
            print(f"💰 Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
            
            # Filter data up to the test date
            test_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            filtered_df = df[df.index.date <= test_date]
            
            print(f"🔍 Data up to {test_date}: {len(filtered_df)} records")
            
            if len(filtered_df) < 50:
                print(f"⚠️ Warning: Only {len(filtered_df)} records (need 50+)")
            
            # Add technical indicators
            print("📈 Adding technical indicators...")
            filtered_df['sma_20'] = filtered_df['close'].rolling(window=20).mean()
            filtered_df['sma_50'] = filtered_df['close'].rolling(window=50).mean()
            filtered_df['sma_200'] = filtered_df['close'].rolling(window=min(200, len(filtered_df))).mean()
            filtered_df['ema_20'] = filtered_df['close'].ewm(span=20).mean()
            
            # Calculate RSI
            delta = filtered_df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            filtered_df['rsi'] = 100 - (100 / (1 + rs))
            
            # Calculate MACD
            exp1 = filtered_df['close'].ewm(span=12).mean()
            exp2 = filtered_df['close'].ewm(span=26).mean()
            filtered_df['macd'] = exp1 - exp2
            filtered_df['macd_signal'] = filtered_df['macd'].ewm(span=9).mean()
            
            # Calculate ATR
            high_low = filtered_df['high'] - filtered_df['low']
            high_close = abs(filtered_df['high'] - filtered_df['close'].shift())
            low_close = abs(filtered_df['low'] - filtered_df['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            filtered_df['atr'] = true_range.rolling(window=14).mean()
            
            # Fill NaN values
            filtered_df = filtered_df.fillna(method='bfill').fillna(method='ffill')
            
            # Get the latest data point
            latest_data = filtered_df.iloc[-1]
            print(f"📊 Latest indicators for {test_date}:")
            print(f"  Price: ${latest_data['close']:.2f}")
            print(f"  SMA20: ${latest_data['sma_20']:.2f}")
            print(f"  SMA50: ${latest_data['sma_50']:.2f}")
            print(f"  RSI: {latest_data['rsi']:.1f}")
            print(f"  MACD: {latest_data['macd']:.4f}")
            print(f"  MACD Signal: {latest_data['macd_signal']:.4f}")
            
            # Generate signal
            print("🚀 Generating signal...")
            engine = GenericSwingEngine()
            
            context = MarketContext(
                regime=MarketRegime.NO_TRADE,
                regime_confidence=0.5,
                vix=20.0,
                nasdaq_trend="neutral"
            )
            
            signal_result = engine.generate_signal("TQQQ", filtered_df, context)
            
            print(f"📊 Signal Result:")
            print(f"  Signal: {signal_result.signal}")
            print(f"  Confidence: {signal_result.confidence:.1%}")
            print(f"  Reasoning: {signal_result.reasoning}")
            print(f"  Position Size: {signal_result.position_size_pct:.1%}")
            
            # Analyze trend
            is_uptrend = latest_data['sma_20'] > latest_data['sma_50']
            is_downtrend = latest_data['sma_20'] < latest_data['sma_50']
            is_oversold = latest_data['rsi'] < 30
            is_overbought = latest_data['rsi'] > 70
            
            print(f"\n📈 Trend Analysis:")
            print(f"  Uptrend: {is_uptrend}")
            print(f"  Downtrend: {is_downtrend}")
            print(f"  Oversold: {is_oversold}")
            print(f"  Overbought: {is_overbought}")
            
        else:
            print("❌ No historical data found")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Test a few different dates
    dates = ["2025-11-03", "2025-12-26", "2025-11-25"]
    for date in dates:
        debug_specific_date(date)
        print("\n" + "="*80 + "\n")
